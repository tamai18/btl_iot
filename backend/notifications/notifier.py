# ============================================================================
#  notifications/notifier.py – Quản lý vòng đời sự cố và xếp hàng gửi email
# ============================================================================
import os
import logging
from datetime import datetime, timedelta
import db
from .notify_rules import evaluate_all_rules, evaluate_recovery
from .mailer import render_alert_email

logger = logging.getLogger(__name__)

# Cấu hình chống spam mặc định
REMIND_DANGER_MIN = int(os.getenv("NOTIFY_REMIND_DANGER_MIN", "30"))
REMIND_WARNING_MIN = int(os.getenv("NOTIFY_REMIND_WARNING_MIN", "120"))
MAX_REMINDERS = int(os.getenv("NOTIFY_MAX_REMINDERS", "3"))

def get_system_config_dict() -> dict:
    """Đọc cấu hình hệ thống từ DB."""
    try:
        rows = db.execute("SELECT config_key, config_value FROM system_config", fetch="all")
        return {r["config_key"]: r["config_value"] for r in (rows or [])}
    except Exception as e:
        logger.error(f"[Notifier] Không thể đọc system_config: {e}")
        return {}

def is_notification_enabled() -> bool:
    """Kiểm tra xem hệ thống có cho phép gửi email hay không."""
    cfg = get_system_config_dict()
    val = cfg.get("mail_enabled", os.getenv("MAIL_ENABLED", "1"))
    return str(val).lower() in ("1", "true", "yes")

def get_active_recipients() -> list[dict]:
    """Lấy danh sách tất cả người nhận đang bật nhận email."""
    try:
        rows = db.execute(
            "SELECT id, email, name FROM notification_recipients WHERE enabled = 1",
            fetch="all"
        )
        return rows or []
    except Exception as e:
        logger.error(f"[Notifier] Lỗi lấy danh sách người nhận: {e}")
        return []

def enqueue_notification(incident_id: int | None, subject: str, body_html: str):
    """Thêm email vào bảng notification_outbox cho tất cả người nhận đang kích hoạt."""
    recipients = get_active_recipients()
    if not recipients:
        logger.info("[Notifier] Không có người nhận nào kích hoạt trong danh bạ. Bỏ qua xếp hàng.")
        return 0

    queued_count = 0
    for r in recipients:
        try:
            db.execute(
                """INSERT INTO notification_outbox 
                   (incident_id, recipient_id, recipient_email, subject, body_html, status, scheduled_at, attempt_count)
                   VALUES (%s, %s, %s, %s, %s, 'PENDING', NOW(), 0)""",
                (incident_id, r["id"], r["email"], subject, body_html)
            )
            queued_count += 1
        except Exception as e:
            logger.error(f"[Notifier] Lỗi thêm vào outbox cho {r['email']}: {e}")
            
    logger.info(f"[Notifier] Đã xếp hàng {queued_count} email thông báo (Tiêu đề: {subject})")
    return queued_count

def process_active_incidents(current_status: dict, cfg: dict):
    """
    Kiểm tra các sự cố đang ACTIVE:
    - Nếu đã an toàn -> Đánh dấu RECOVERED và gửi email phục hồi.
    - Nếu chưa an toàn -> Xét lịch nhắc lại chống spam.
    """
    try:
        active_incidents = db.execute(
            "SELECT * FROM incidents WHERE status = 'ACTIVE'",
            fetch="all"
        ) or []
    except Exception as e:
        logger.error(f"[Notifier] Lỗi truy vấn sự cố đang hoạt động: {e}")
        return

    now = datetime.now()

    for inc in active_incidents:
        inc_id = inc["id"]
        event_key = inc["event_key"]
        severity = inc["severity"]

        # 1. Kiểm tra điều kiện phục hồi
        if evaluate_recovery(inc, current_status, cfg):
            try:
                db.execute(
                    "UPDATE incidents SET status = 'RECOVERED', recovered_at = NOW() WHERE id = %s",
                    (inc_id,)
                )
                logger.info(f"[Notifier] Sự cố #{inc_id} ({event_key}) đã PHỤC HỒI an toàn!")

                # Gửi email báo phục hồi
                recov_subj, recov_html = render_alert_email(
                    event_key=event_key,
                    severity=severity,
                    title=f"Đã phục hồi: {event_key}",
                    message=f"Các thông số cảm biến và vận hành của sự cố '{event_key}' đã trở lại trạng thái an toàn bình thường.",
                    water_level=current_status.get("water_level"),
                    pump_in=current_status.get("pump_in", 0),
                    pump_out=current_status.get("pump_out", 0),
                    auto_mode=current_status.get("auto_mode", 1),
                    recommendation="Hệ thống tiếp tục theo dõi tự động.",
                    is_recovery=True,
                )
                enqueue_notification(inc_id, recov_subj, recov_html)
            except Exception as e:
                logger.error(f"[Notifier] Lỗi xử lý phục hồi sự cố #{inc_id}: {e}")
            continue

        # 2. Xử lý nhắc lại (remind) nếu vẫn còn lỗi
        remind_count = int(inc.get("remind_count") or 0)
        if remind_count >= MAX_REMINDERS:
            continue

        last_notified_raw = inc.get("last_notified_at")
        if not last_notified_raw:
            continue

        if isinstance(last_notified_raw, str):
            try:
                last_notified = datetime.fromisoformat(last_notified_raw.replace("Z", ""))
            except ValueError:
                continue
        else:
            last_notified = last_notified_raw

        remind_interval = timedelta(minutes=REMIND_DANGER_MIN if severity == "DANGER" else REMIND_WARNING_MIN)
        if now - last_notified >= remind_interval:
            # Gửi nhắc lại
            new_count = remind_count + 1
            try:
                db.execute(
                    "UPDATE incidents SET last_notified_at = NOW(), remind_count = %s WHERE id = %s",
                    (new_count, inc_id)
                )
                remind_subj, remind_html = render_alert_email(
                    event_key=event_key,
                    severity=severity,
                    title=f"[NHẮC LẠI #{new_count}] Sự cố vẫn đang diễn ra: {event_key}",
                    message=f"Sự cố '{event_key}' ghi nhận từ trước vẫn chưa được khắc phục và đang tiếp tục đe dọa an toàn ao nuôi.",
                    water_level=current_status.get("water_level"),
                    pump_in=current_status.get("pump_in", 0),
                    pump_out=current_status.get("pump_out", 0),
                    auto_mode=current_status.get("auto_mode", 1),
                    recommendation="Vui lòng can thiệp xử lý ngay để tránh thiệt hại.",
                )
                enqueue_notification(inc_id, remind_subj, remind_html)
                logger.info(f"[Notifier] Đã gửi nhắc lại lần #{new_count} cho sự cố #{inc_id}")
            except Exception as e:
                logger.error(f"[Notifier] Lỗi gửi nhắc lại sự cố #{inc_id}: {e}")

def handle_triggered_incident(rule_res: dict, current_status: dict, device_id: str = "esp32-ao-01"):
    """
    Xử lý khi một quy tắc phát hiện sự cố:
    Kiểm tra chống trùng lặp, mở incident mới nếu chưa có, và xếp hàng email đầu tiên.
    """
    event_key = rule_res["event_key"]
    severity = rule_res["severity"]

    # Kiểm tra xem đã có incident ACTIVE cho event_key này chưa
    existing = db.execute(
        "SELECT id FROM incidents WHERE event_key = %s AND device_id = %s AND status = 'ACTIVE' LIMIT 1",
        (event_key, device_id),
        fetch="one"
    )

    if existing:
        # Đã có sự cố đang active, không tạo trùng lặp
        return existing["id"]

    # Tạo sự cố mới
    try:
        inc_id = db.execute(
            """INSERT INTO incidents 
               (event_key, severity, device_id, status, water_level_at_detect, pump_in_at_detect, pump_out_at_detect,
                started_at, last_notified_at, remind_count, source, notes)
               VALUES (%s, %s, %s, 'ACTIVE', %s, %s, %s, NOW(), NOW(), 0, %s, %s)""",
            (
                event_key,
                severity,
                device_id,
                current_status.get("water_level"),
                int(current_status.get("pump_in", 0) or 0),
                int(current_status.get("pump_out", 0) or 0),
                rule_res.get("source", "backend_rule"),
                rule_res.get("message", "")
            )
        )
        logger.warning(f"[Notifier] PHÁT HIỆN SỰ CỐ MỚI #{inc_id}: [{severity}] {event_key} - {rule_res.get('title')}")

        # Tạo và xếp hàng email thông báo ban đầu
        subject, body_html = render_alert_email(
            event_key=event_key,
            severity=severity,
            title=rule_res.get("title", event_key),
            message=rule_res.get("message", ""),
            water_level=current_status.get("water_level"),
            pump_in=int(current_status.get("pump_in", 0) or 0),
            pump_out=int(current_status.get("pump_out", 0) or 0),
            auto_mode=int(current_status.get("auto_mode", 1) or 1),
            recommendation=rule_res.get("recommendation"),
        )
        enqueue_notification(inc_id, subject, body_html)
        return inc_id
    except Exception as e:
        logger.error(f"[Notifier] Lỗi tạo sự cố {event_key}: {e}")
        return None

def on_telemetry_received(current_status: dict):
    """
    Điểm đón dữ liệu telemetry định kỳ từ MQTT (/data).
    Được gọi tự động mỗi khi có bản tin dữ liệu cảm biến mới.
    """
    if not is_notification_enabled():
        return

    cfg = get_system_config_dict()

    # Lấy 10 bản ghi gần nhất (trong khoảng 3 - 5 phút) để xét xu hướng và hiệu quả bơm
    try:
        recent = db.execute(
            "SELECT water_level, pump_in, pump_out, recorded_at FROM sensor_data ORDER BY recorded_at DESC LIMIT 10",
            fetch="all"
        ) or []
        recent.reverse() # Sắp xếp tăng dần theo thời gian
    except Exception:
        recent = []

    # 1. Đánh giá tất cả các quy tắc
    triggered_rules = evaluate_all_rules(current_status, cfg, recent)

    # 2. Xử lý các sự cố mới phát hiện
    device_id = current_status.get("esp32_id", "esp32-ao-01")
    for r in triggered_rules:
        handle_triggered_incident(r, current_status, device_id)

    # 3. Kiểm tra phục hồi hoặc nhắc lại các sự cố đang active
    process_active_incidents(current_status, cfg)

def on_esp32_alert(alert_payload: dict):
    """
    Điểm đón cảnh báo khẩn trực tiếp từ topic /alert của ESP32.
    """
    if not is_notification_enabled():
        return

    code = str(alert_payload.get("code") or alert_payload.get("alert_code", "")).lower()
    msg = alert_payload.get("msg") or alert_payload.get("message") or "Cảnh báo từ ESP32"
    device_id = alert_payload.get("esp32_id", "esp32-ao-01")
    level = alert_payload.get("level")

    severity = "WARNING"
    event_key = code.upper()

    if "high" in code or "danger" in code:
        severity = "DANGER"
        event_key = "HIGH_LEVEL"
    elif "low" in code:
        severity = "DANGER"
        event_key = "LOW_LEVEL"
    elif "sensor" in code:
        event_key = "SENSOR_ERROR"
    elif "overrun" in code:
        event_key = "PUMP_OVERRUN"

    rule_dict = {
        "event_key": event_key,
        "severity": severity,
        "title": f"Cảnh báo trực tiếp từ thiết bị: {code}",
        "message": msg,
        "recommendation": "Kiểm tra ngay trạng thái vật lý của thiết bị tại ao nuôi.",
        "source": "esp32",
    }

    dummy_status = {
        "water_level": level,
        "pump_in": alert_payload.get("pump_in", 0),
        "pump_out": alert_payload.get("pump_out", 0),
        "auto_mode": alert_payload.get("auto_mode", 1),
        "esp32_id": device_id,
    }

    handle_triggered_incident(rule_dict, dummy_status, device_id)

