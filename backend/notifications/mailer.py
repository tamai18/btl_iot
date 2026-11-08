# ============================================================================
#  notifications/mailer.py – Gửi Email qua SMTP (Gmail / Custom SMTP)
# ============================================================================
import os
import smtplib
import logging
import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from datetime import datetime

logger = logging.getLogger(__name__)

def get_mailer_config():
    """Lấy cấu hình mail từ biến môi trường (không bao giờ lộ mật khẩu ra log)."""
    return {
        "host": os.getenv("MAIL_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("MAIL_PORT", "587")),
        "user": os.getenv("MAIL_USER", ""),
        "pass": os.getenv("MAIL_PASS", ""),
        "from_name": os.getenv("MAIL_FROM_NAME", "Hệ thống IoT Ao Nuôi"),
        "enabled": os.getenv("MAIL_ENABLED", "true").lower() in ("true", "1", "yes"),
    }

def send_smtp_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str | None]:
    """
    Gửi email trực tiếp qua SMTP với STARTTLS.
    Trả về (True, None) nếu thành công hoặc (False, error_str) nếu thất bại.
    """
    cfg = get_mailer_config()
    
    if not cfg["enabled"]:
        logger.info(f"[Mailer] Chức năng gửi email đang bị tắt (MAIL_ENABLED=false). Bỏ qua gửi tới {to_email}")
        return False, "Chức năng gửi mail bị vô hiệu hóa trong cấu hình hệ thống"

    if not cfg["user"] or not cfg["pass"]:
        err_msg = "Chưa cấu hình tài khoản gửi mail (MAIL_USER hoặc MAIL_PASS trống)"
        logger.warning(f"[Mailer] {err_msg}")
        return False, err_msg

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((str(Header(cfg["from_name"], "utf-8")), cfg["user"]))
        msg["To"] = to_email
        msg["Subject"] = Header(subject, "utf-8").encode()
        
        part = MIMEText(html_body, "html", "utf-8")
        msg.attach(part)

        logger.info(f"[Mailer] Bắt đầu kết nối tới {cfg['host']}:{cfg['port']} để gửi email tới {to_email}...")
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["user"], cfg["pass"])
            server.sendmail(cfg["user"], [to_email], msg.as_string())
            
        logger.info(f"[Mailer] Gửi email thành công tới {to_email} (Tiêu đề: {subject})")
        return True, None
    except Exception as e:
        err = str(e)
        # Đảm bảo không để lộ mật khẩu trong chuỗi lỗi
        if cfg["pass"] and cfg["pass"] in err:
            err = err.replace(cfg["pass"], "******")
        logger.error(f"[Mailer] Lỗi khi gửi email tới {to_email}: {err}")
        return False, err

def render_alert_email(
    event_key: str,
    severity: str,
    title: str,
    message: str,
    water_level: float | None = None,
    pump_in: int = 0,
    pump_out: int = 0,
    auto_mode: int = 1,
    detect_time: str | None = None,
    recommendation: str | None = None,
    is_recovery: bool = False,
) -> tuple[str, str]:
    """
    Tạo tiêu đề và nội dung HTML chuẩn cho email cảnh báo hoặc phục hồi.
    Mọi dữ liệu động đều được escape để bảo mật.
    """
    if not detect_time:
        detect_time = datetime.now().strftime("%H:%M:%S %d/%m/%Y")

    safe_title = html.escape(title)
    safe_message = html.escape(message)
    safe_time = html.escape(str(detect_time))
    safe_rec = html.escape(recommendation or "Vui lòng kiểm tra hiện trường ao nuôi và hệ thống thiết bị.")

    if is_recovery:
        badge_text = "ĐÃ KHÔI PHỤC"
        badge_bg = "#10b981"
        subject_prefix = "[PHỤC HỒI]"
        header_title = f"Hệ thống đã phục hồi bình thường: {safe_title}"
    elif severity == "DANGER":
        badge_text = "NGUY HIỂM"
        badge_bg = "#ef4444"
        subject_prefix = "[NGUY HIỂM]"
        header_title = f"Cảnh báo khẩn cấp: {safe_title}"
    else:
        badge_text = "CẢNH BÁO"
        badge_bg = "#f59e0b"
        subject_prefix = "[CẢNH BÁO]"
        header_title = f"Cảnh báo hệ thống: {safe_title}"

    subject = f"{subject_prefix} {title} - Ao nuôi cá IoT ({detect_time.split()[0] if ' ' in detect_time else detect_time})"

    lvl_str = f"{water_level:.1f}%" if water_level is not None else "--%"
    p_in_str = "ĐANG BẬT" if pump_in == 1 else "TẮT"
    p_out_str = "ĐANG BẬT" if pump_out == 1 else "TẮT"
    mode_str = "Tự động (AUTO)" if auto_mode == 1 else "Thủ công (MANUAL)"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
  .email-container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
  .header {{ background: #0f172a; padding: 24px; color: #ffffff; text-align: left; }}
  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; color: #ffffff; background-color: {badge_bg}; }}
  .header h2 {{ margin: 12px 0 4px 0; font-size: 18px; line-height: 1.4; color: #ffffff; }}
  .header p {{ margin: 0; font-size: 13px; color: #94a3b8; }}
  .body {{ padding: 24px; }}
  .alert-box {{ background: #f8fafc; border-left: 4px solid {badge_bg}; padding: 14px 16px; border-radius: 4px; margin-bottom: 20px; font-size: 14px; line-height: 1.5; }}
  .metrics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
  .metric-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; text-align: center; }}
  .metric-lbl {{ font-size: 11px; color: #64748b; text-transform: uppercase; margin-bottom: 4px; }}
  .metric-val {{ font-size: 16px; font-weight: bold; color: #0f172a; }}
  .rec-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 14px 16px; margin-bottom: 20px; }}
  .rec-title {{ font-size: 13px; font-weight: bold; color: #1d4ed8; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }}
  .rec-content {{ font-size: 13px; color: #1e3a8a; line-height: 1.5; }}
  .footer {{ background: #f8fafc; padding: 16px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
</style>
</head>
<body>
<div class="email-container">
  <div class="header">
    <span class="badge">{badge_text}</span>
    <h2>{header_title}</h2>
    <p>Thời gian ghi nhận: {safe_time}</p>
  </div>
  <div class="body">
    <div class="alert-box">
      <strong>Chi tiết sự cố:</strong><br>
      {safe_message}
    </div>
    
    <div style="font-weight: 600; font-size: 13px; margin-bottom: 10px; color: #334155;">Thông số ao nuôi tại thời điểm phát hiện:</div>
    <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse: collapse; margin-bottom: 20px; font-size: 13px; border: 1px solid #e2e8f0; border-radius: 6px;">
      <tr style="background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
        <td style="color: #64748b; width: 45%;">Mực nước hiện tại:</td>
        <td style="font-weight: bold; color: #0f172a;">{lvl_str}</td>
      </tr>
      <tr style="border-bottom: 1px solid #e2e8f0;">
        <td style="color: #64748b;">Bơm cấp nước (IN):</td>
        <td style="font-weight: bold; color: {'#16a34a' if pump_in == 1 else '#64748b'};">{p_in_str}</td>
      </tr>
      <tr style="border-bottom: 1px solid #e2e8f0;">
        <td style="color: #64748b;">Bơm thoát nước (OUT):</td>
        <td style="font-weight: bold; color: {'#16a34a' if pump_out == 1 else '#64748b'};">{p_out_str}</td>
      </tr>
      <tr>
        <td style="color: #64748b;">Chế độ hoạt động:</td>
        <td style="font-weight: bold; color: #0f172a;">{mode_str}</td>
      </tr>
    </table>

    <div class="rec-box">
      <div class="rec-title">💡 Hướng dẫn xử lý đề xuất:</div>
      <div class="rec-content">{safe_rec}</div>
    </div>
  </div>
  <div class="footer">
    Hệ thống Giám sát & Điều khiển Mực nước Ao nuôi Cá Thông minh<br>
    Tin nhắn tự động được gửi từ máy chủ IoT. Vui lòng không trả lời trực tiếp email này.
  </div>
</div>
</body>
</html>"""
    return subject, html_content

def render_test_email(to_email: str) -> tuple[str, str]:
    """Tạo email thử nghiệm để người dùng kiểm tra kết nối SMTP."""
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    safe_to = html.escape(to_email)
    subject = f"[KIỂM TRA] Thử nghiệm gửi email cảnh báo ao nuôi cá ({now_str})"
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
  .email-container {{ max-width: 550px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
  .header {{ background: #2563eb; padding: 24px; color: #ffffff; text-align: center; }}
  .header h2 {{ margin: 0 0 6px 0; font-size: 18px; }}
  .body {{ padding: 24px; font-size: 14px; line-height: 1.6; }}
  .success-box {{ background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 14px 16px; margin: 16px 0; color: #065f46; }}
  .footer {{ background: #f8fafc; padding: 16px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
</style>
</head>
<body>
<div class="email-container">
  <div class="header">
    <h2>✉️ Thử nghiệm Cảnh báo Email</h2>
    <p style="margin: 0; font-size: 13px; opacity: 0.9;">Hệ thống IoT Giám sát Ao Nuôi Cá</p>
  </div>
  <div class="body">
    <p>Xin chào bạn,</p>
    <div class="success-box">
      <strong>🎉 Kết nối gửi mail thành công!</strong><br>
      Địa chỉ email <strong>{safe_to}</strong> đã được xác nhận sẵn sàng nhận các thông báo cảnh báo nguy hiểm và sự cố bất thường từ ao nuôi cá.
    </div>
    <p>Khi có các sự cố như mực nước quá cao (nguy cơ tràn), mực nước quá thấp, bơm không hiệu quả hoặc mất kết nối thiết bị, hệ thống sẽ tự động gửi email thông báo kèm hướng dẫn xử lý.</p>
    <p style="color: #64748b; font-size: 13px;">Thời gian gửi thử: {now_str}</p>
  </div>
  <div class="footer">
    Hệ thống Giám sát & Điều khiển Mực nước Ao nuôi Cá Thông minh
  </div>
</div>
</body>
</html>"""
    return subject, html_content

