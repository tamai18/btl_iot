# ============================================================================
#  notifications/mail_worker.py – Background Worker quét hàng đợi và gửi email
# ============================================================================
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import db
from .mailer import send_smtp_email

logger = logging.getLogger(__name__)

# Hạn mức số thư gửi tối đa mỗi giờ để tránh bị khóa tài khoản Gmail
HOURLY_LIMIT = int(os.getenv("NOTIFY_HOURLY_LIMIT", "10"))

# Thời gian chờ thử lại tương ứng với số lần thử (lần 1: 30s, lần 2: 2m, lần 3: 10m, lần 4: 30m, lần 5: 60m)
RETRY_BACKOFF_SECONDS = [30, 120, 600, 1800, 3600]
MAX_ATTEMPTS = 5

_worker_thread = None
_stop_event = threading.Event()
_worker_lock = threading.Lock()

def get_hourly_sent_count() -> int:
    """Đếm số lượng email đã gửi thành công trong vòng 1 giờ qua."""
    try:
        row = db.execute(
            """SELECT COUNT(*) AS cnt FROM notification_outbox 
               WHERE status = 'SENT' AND sent_at >= NOW() - INTERVAL 1 HOUR""",
            fetch="one"
        )
        return int(row["cnt"]) if row else 0
    except Exception as e:
        logger.error(f"[MailWorker] Lỗi kiểm tra hạn mức theo giờ: {e}")
        return 0

def process_pending_outbox():
    """Lấy danh sách các email đang chờ gửi và thực hiện gửi đi."""
    with _worker_lock:
        # 1. Kiểm tra hạn mức giờ
        sent_in_hour = get_hourly_sent_count()
        if sent_in_hour >= HOURLY_LIMIT:
            logger.warning(
                f"[MailWorker] Đã đạt hạn mức an toàn gửi email theo giờ ({sent_in_hour}/{HOURLY_LIMIT}). "
                "Tạm hoãn các email tiếp theo..."
            )
            return

        # 2. Truy vấn danh sách email PENDING đã đến giờ gửi
        try:
            pending_rows = db.execute(
                """SELECT id, recipient_email, subject, body_html, attempt_count
                   FROM notification_outbox
                   WHERE status = 'PENDING' AND scheduled_at <= NOW()
                   ORDER BY scheduled_at ASC
                   LIMIT 5""",
                fetch="all"
            ) or []
        except Exception as e:
            logger.error(f"[MailWorker] Lỗi truy vấn bảng outbox: {e}")
            return

        for item in pending_rows:
            mail_id = item["id"]
            to_email = item["recipient_email"]
            subject = item["subject"]
            body_html = item["body_html"]
            attempts = int(item.get("attempt_count") or 0)

            # Kiểm tra lại hạn mức trước từng email
            if sent_in_hour >= HOURLY_LIMIT:
                break

            logger.info(f"[MailWorker] Đang xử lý email #{mail_id} tới {to_email} (Lần thử {attempts + 1})...")
            success, err_msg = send_smtp_email(to_email, subject, body_html)

            new_attempts = attempts + 1
            if success:
                try:
                    db.execute(
                        """UPDATE notification_outbox 
                           SET status = 'SENT', sent_at = NOW(), attempt_count = %s, last_error = NULL
                           WHERE id = %s""",
                        (new_attempts, mail_id)
                    )
                    sent_in_hour += 1
                    logger.info(f"[MailWorker] Email #{mail_id} đã GỬI THÀNH CÔNG tới {to_email}")
                except Exception as e:
                    logger.error(f"[MailWorker] Lỗi cập nhật trạng thái SENT cho #{mail_id}: {e}")
            else:
                if new_attempts >= MAX_ATTEMPTS:
                    # Hết lượt thử lại, đánh dấu FAILED
                    try:
                        db.execute(
                            """UPDATE notification_outbox 
                               SET status = 'FAILED', attempt_count = %s, last_error = %s
                               WHERE id = %s""",
                            (new_attempts, err_msg or "Lỗi không xác định", mail_id)
                        )
                        logger.error(f"[MailWorker] Email #{mail_id} đã THẤT BẠI HOÀN TOÀN sau {new_attempts} lần thử: {err_msg}")
                    except Exception as e:
                        logger.error(f"[MailWorker] Lỗi cập nhật trạng thái FAILED cho #{mail_id}: {e}")
                else:
                    # Lên lịch thử lại
                    delay_sec = RETRY_BACKOFF_SECONDS[min(attempts, len(RETRY_BACKOFF_SECONDS) - 1)]
                    try:
                        db.execute(
                            """UPDATE notification_outbox 
                               SET attempt_count = %s, last_error = %s, 
                                   scheduled_at = datetime('now', '+' || %s || ' seconds')
                               WHERE id = %s""",
                            (new_attempts, err_msg or "Lỗi kết nối", str(delay_sec), mail_id)
                        )
                        logger.warning(
                            f"[MailWorker] Email #{mail_id} gửi không thành công. "
                            f"Lên lịch thử lại sau {delay_sec}s (Lỗi: {err_msg})"
                        )
                    except Exception:
                        # Fallback query for MySQL if datetime() failed
                        try:
                            db.execute(
                                """UPDATE notification_outbox 
                                   SET attempt_count = %s, last_error = %s, 
                                       scheduled_at = DATE_ADD(NOW(), INTERVAL %s SECOND)
                                   WHERE id = %s""",
                                (new_attempts, err_msg or "Lỗi kết nối", delay_sec, mail_id)
                            )
                        except Exception as ex:
                            logger.error(f"[MailWorker] Không thể lên lịch thử lại email #{mail_id}: {ex}")

def _worker_loop():
    logger.info("[MailWorker] Dịch vụ Mail Worker đã khởi động nền.")
    while not _stop_event.is_set():
        try:
            process_pending_outbox()
        except Exception as e:
            logger.error(f"[MailWorker] Lỗi ngoại lệ trong vòng lặp worker: {e}", exc_info=True)
        # Quét hàng đợi mỗi 10 giây
        _stop_event.wait(10)
    logger.info("[MailWorker] Dịch vụ Mail Worker đã dừng.")

def start_mail_worker():
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, name="MailWorkerThread", daemon=True)
    _worker_thread.start()

def stop_mail_worker():
    _stop_event.set()

