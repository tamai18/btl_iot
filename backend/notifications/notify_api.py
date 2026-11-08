# ============================================================================
#  notifications/notify_api.py – Flask REST API cho Cảnh báo Email
# ============================================================================
import re
import logging
from flask import Blueprint, jsonify, request
import db
from .mailer import get_mailer_config, send_smtp_email, render_test_email
from .notifier import is_notification_enabled, get_system_config_dict

logger = logging.getLogger(__name__)

notify_bp = Blueprint("notify", __name__, url_prefix="/api/notify")

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# ── 1. Danh sách người nhận email ──────────────────────────────────────────
@notify_bp.route("/recipients", methods=["GET"])
def get_recipients():
    try:
        rows = db.execute(
            "SELECT id, email, name, enabled, created_at, updated_at FROM notification_recipients ORDER BY id ASC",
            fetch="all"
        )
        return jsonify({"ok": True, "recipients": rows or []})
    except Exception as e:
        logger.error(f"[NotifyAPI] Lỗi lấy danh sách người nhận: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ── 2. Thêm người nhận email mới ───────────────────────────────────────────
@notify_bp.route("/recipients", methods=["POST"])
def add_recipient():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    name = str(data.get("name", "Người nuôi cá")).strip()
    enabled = 1 if data.get("enabled", True) else 0

    if not email or not EMAIL_REGEX.match(email):
        return jsonify({"ok": False, "error": "Địa chỉ email không đúng định dạng"}), 400

    try:
        # Kiểm tra trùng email
        existing = db.execute(
            "SELECT id FROM notification_recipients WHERE email = %s",
            (email,),
            fetch="one"
        )
        if existing:
            # Cập nhật lại trạng thái enabled nếu đã có
            db.execute(
                "UPDATE notification_recipients SET enabled = %s, name = %s WHERE id = %s",
                (enabled, name, existing["id"])
            )
            return jsonify({"ok": True, "id": existing["id"], "updated": True})

        new_id = db.execute(
            "INSERT INTO notification_recipients (email, name, enabled) VALUES (%s, %s, %s)",
            (email, name, enabled)
        )
        return jsonify({"ok": True, "id": new_id, "created": True})
    except Exception as e:
        logger.error(f"[NotifyAPI] Lỗi thêm người nhận {email}: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ── 3. Cập nhật người nhận (Bật / Tắt hoặc sửa tên) ────────────────────────
@notify_bp.route("/recipients/<int:recipient_id>", methods=["PUT"])
def update_recipient(recipient_id):
    data = request.get_json(silent=True) or {}
    fields, params = [], []

    if "enabled" in data:
        fields.append("enabled = %s")
        params.append(1 if data["enabled"] else 0)
    if "name" in data:
        fields.append("name = %s")
        params.append(str(data["name"]).strip())
    if "email" in data:
        email = str(data["email"]).strip().lower()
        if not EMAIL_REGEX.match(email):
            return jsonify({"ok": False, "error": "Địa chỉ email không hợp lệ"}), 400
        fields.append("email = %s")
        params.append(email)

    if not fields:
        return jsonify({"ok": False, "error": "Không có dữ liệu cần cập nhật"}), 400

    params.append(recipient_id)
    try:
        db.execute(
            f"UPDATE notification_recipients SET {', '.join(fields)} WHERE id = %s",
            params
        )
        return jsonify({"ok": True, "id": recipient_id})
    except Exception as e:
        logger.error(f"[NotifyAPI] Lỗi cập nhật người nhận #{recipient_id}: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ── 4. Xóa người nhận ───────────────────────────────────────────────────────
@notify_bp.route("/recipients/<int:recipient_id>", methods=["DELETE"])
def delete_recipient(recipient_id):
    try:
        db.execute("DELETE FROM notification_recipients WHERE id = %s", (recipient_id,))
        return jsonify({"ok": True, "id": recipient_id})
    except Exception as e:
        logger.error(f"[NotifyAPI] Lỗi xóa người nhận #{recipient_id}: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ── 5. Đọc / Ghi cấu hình Cảnh báo Email ───────────────────────────────────
@notify_bp.route("/settings", methods=["GET", "POST"])
def email_settings():
    if request.method == "GET":
        cfg = get_system_config_dict()
        smtp_cfg = get_mailer_config()

        # Lấy email mặc định từ recipients hoặc system_config
        first_recipient = db.execute(
            "SELECT email FROM notification_recipients WHERE enabled = 1 ORDER BY id ASC LIMIT 1",
            fetch="one"
        )
        default_email = first_recipient["email"] if first_recipient else cfg.get("mail_recipient_default", "nguoinuoi@example.com")

        return jsonify({
            "ok": True,
            "settings": {
                "mail_enabled": is_notification_enabled(),
                "recipient_default": default_email,
                "smtp_configured": bool(smtp_cfg["user"] and smtp_cfg["pass"]),
                "smtp_user": smtp_cfg["user"],
                "smtp_host": smtp_cfg["host"],
                "smtp_port": smtp_cfg["port"],
            }
        })

    # POST: Cập nhật cài đặt
    data = request.get_json(silent=True) or {}
    mail_enabled = data.get("mail_enabled")
    recipient_email = str(data.get("recipient_default") or data.get("email") or "").strip().lower()

    try:
        if mail_enabled is not None:
            val_str = "1" if mail_enabled else "0"
            db.execute(
                "INSERT INTO system_config (config_key, config_value, description) VALUES ('mail_enabled', %s, 'Bật/tắt gửi email cảnh báo tự động') "
                "ON DUPLICATE KEY UPDATE config_value=%s",
                (val_str, val_str)
            )

        if recipient_email and EMAIL_REGEX.match(recipient_email):
            db.execute(
                "INSERT INTO system_config (config_key, config_value, description) VALUES ('mail_recipient_default', %s, 'Email nhận cảnh báo chính') "
                "ON DUPLICATE KEY UPDATE config_value=%s",
                (recipient_email, recipient_email)
            )
            # Đồng bộ vào notification_recipients
            existing = db.execute(
                "SELECT id FROM notification_recipients WHERE email = %s",
                (recipient_email,),
                fetch="one"
            )
            if not existing:
                db.execute(
                    "INSERT INTO notification_recipients (email, name, enabled) VALUES (%s, 'Chủ ao nuôi cá', 1)",
                    (recipient_email,)
                )
            else:
                db.execute(
                    "UPDATE notification_recipients SET enabled = 1 WHERE id = %s",
                    (existing["id"],)
                )

        return jsonify({"ok": True, "message": "Đã lưu cài đặt cảnh báo email"})
    except Exception as e:
        logger.error(f"[NotifyAPI] Lỗi lưu cài đặt email: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ── 6. Gửi thử nghiệm email ────────────────────────────────────────────────
@notify_bp.route("/test", methods=["POST"])
def send_test():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()

    if not email:
        # Lấy email đầu tiên có sẵn
        rec = db.execute(
            "SELECT email FROM notification_recipients WHERE enabled = 1 ORDER BY id ASC LIMIT 1",
            fetch="one"
        )
        if rec:
            email = rec["email"]
        else:
            email = "nguoinuoi@example.com"

    if not EMAIL_REGEX.match(email):
        return jsonify({"ok": False, "error": f"Email '{email}' không hợp lệ"}), 400

    subject, html_body = render_test_email(email)
    success, err = send_smtp_email(email, subject, html_body)

    # Ghi nhận vào outbox để lưu nhật ký
    try:
        db.execute(
            """INSERT INTO notification_outbox 
               (recipient_email, subject, body_html, status, scheduled_at, sent_at, attempt_count, last_error)
               VALUES (%s, %s, %s, %s, NOW(), %s, 1, %s)""",
            (email, subject, html_body, "SENT" if success else "FAILED", datetime.now() if success else None, err)
        )
    except Exception:
        pass

    if success:
        return jsonify({"ok": True, "message": f"Đã gửi email thử nghiệm thành công tới {email}"})
    else:
        return jsonify({"ok": False, "error": f"Không thể gửi email: {err}"}), 502

# ── 7. Nhật ký gửi email (Outbox Logs) ──────────────────────────────────────
@notify_bp.route("/logs", methods=["GET"])
def get_logs():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        limit = min(int(request.args.get("limit", 20)), 100)
    except (TypeError, ValueError):
        page, limit = 1, 20
    offset = (page - 1) * limit

    try:
        rows = db.execute(
            """SELECT id, incident_id, recipient_email, subject, status, scheduled_at, sent_at, attempt_count, last_error, created_at
               FROM notification_outbox
               ORDER BY created_at DESC
               LIMIT %s OFFSET %s""",
            (limit, offset),
            fetch="all"
        )
        cnt = db.execute("SELECT COUNT(*) AS c FROM notification_outbox", fetch="one")
        return jsonify({
            "ok": True,
            "data": rows or [],
            "total": cnt["c"] if cnt else 0,
            "page": page,
            "limit": limit
        })
    except Exception as e:
        logger.error(f"[NotifyAPI] Lỗi lấy danh sách outbox: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ── 8. Danh sách sự cố (Incidents) ─────────────────────────────────────────
@notify_bp.route("/incidents", methods=["GET"])
def get_incidents():
    status = request.args.get("status", "")
    try:
        if status:
            rows = db.execute(
                "SELECT * FROM incidents WHERE status = %s ORDER BY started_at DESC LIMIT 50",
                (status,),
                fetch="all"
            )
        else:
            rows = db.execute(
                "SELECT * FROM incidents ORDER BY started_at DESC LIMIT 50",
                fetch="all"
            )
        return jsonify({"ok": True, "incidents": rows or []})
    except Exception as e:
        logger.error(f"[NotifyAPI] Lỗi lấy danh sách incidents: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

