# ============================================================================
#  app.py – Flask Backend chính
#  Cung cấp REST API cho website 7 trang
#  Nhận MQTT từ ESP32, lưu MySQL, phục vụ frontend
# ============================================================================
import os, logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import db
import mqtt_client
from firmware_config import load_firmware_defaults

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if os.getenv("FLASK_DEBUG", "true").lower() == "true" else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

from chat import chat_bp
app.register_blueprint(chat_bp)

from notifications.notify_api import notify_bp
app.register_blueprint(notify_bp)

from water_analysis import build_dashboard_insights

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# ── Hàm khởi động MQTT ────────────────────────────────────────────────────────
def start_mqtt():
    try:
        mqtt_client.start()
    except Exception as _e:
        logger.warning(f"[App] mqtt_client.start error: {_e}")

# ── Global JSON Error Handler ─────────────────────────────────────────────────
@app.errorhandler(Exception)
def handle_global_exception(e):
    logger.error(f"[Server Error] {e}", exc_info=True)
    return jsonify({"ok": False, "error": str(e)}), 500

# ============================================================================
#  SERVE FRONTEND
# ============================================================================
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# ============================================================================
#  API: /api/dashboard/insights  – Phân tích xu hướng & Dự báo mực nước (v2)
# ============================================================================
@app.route("/api/dashboard/insights")
def api_dashboard_insights():
    try:
        demo = request.args.get("demo", "0") == "1" or os.getenv("DEMO_INSIGHTS", "false").lower() == "true"
        data = build_dashboard_insights(demo_mode=demo)
        return jsonify(data)
    except Exception as e:
        logger.error(f"[Insights Error] {e}", exc_info=True)
        return jsonify({"ok": False, "error": "INTERNAL_ERROR"}), 500


# ============================================================================
#  API: /api/status  – Trạng thái tổng quan hệ thống
# ============================================================================
@app.route("/api/status")
def api_status():
    latest = mqtt_client.get_latest()
    device_online = (
        latest.get("esp32_status") == "online"
        and latest.get("ts") is not None
    )
    row = db.execute(
        "SELECT * FROM sensor_data ORDER BY recorded_at DESC LIMIT 1", fetch="one"
    )
    cfg_rows = db.execute("SELECT config_key, config_value FROM system_config", fetch="all")
    cfg = {r["config_key"]: r["config_value"] for r in (cfg_rows or [])}
    runtime_config = {
        "mqtt_broker": os.getenv("MQTT_DEVICE_HOST", "192.168.1.100"),
        "mqtt_port": os.getenv("MQTT_PORT", "1883"),
        "topic_prefix": os.getenv("MQTT_TOPIC_PREFIX", "iot"),
    }

    # Bổ sung cấu hình thực tế nhận từ ESP32 nếu có
    if "reported_cfg" in latest:
        cfg["esp32_reported"] = latest["reported_cfg"]

    count = db.execute(
        "SELECT COUNT(*) AS cnt FROM sensor_data", fetch="one"
    )

    return jsonify({
        "ok": True,
        "latest": latest,
        "last_record": _serialize(row),
        "config": cfg,
        "runtime_config": runtime_config,
        "total_records": count["cnt"] if count else 0,
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "mqtt_connected": mqtt_client.is_connected(),
        "esp32_status": latest.get("esp32_status", "unknown"),
        "device_online": device_online,
        "db_info": db.get_db_info(),
    })


# ============================================================================
#  API: /api/sensor  – Dữ liệu cảm biến (biểu đồ / lịch sử)
# ============================================================================
@app.route("/api/sensor")
def api_sensor():
    try:
        minutes = int(request.args.get("minutes", 30))
    except (TypeError, ValueError):
        minutes = 30
    date_from = request.args.get("from")   # YYYY-MM-DD
    date_to   = request.args.get("to")
    all_data  = request.args.get("all", "0") == "1"
    try:
        limit = min(int(request.args.get("limit", 500)), 2000)
    except (TypeError, ValueError):
        limit = 500
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    offset = (page - 1) * limit

    if all_data:
        rows = db.execute(
            """SELECT * FROM sensor_data
               ORDER BY recorded_at DESC LIMIT %s OFFSET %s""",
            (limit, offset),
            fetch="all",
        )
        cnt = db.execute(
            "SELECT COUNT(*) AS c FROM sensor_data",
            fetch="one",
        )
    elif date_from and date_to:
        date_to_exclusive = (
            datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        sql = """SELECT * FROM sensor_data
                 WHERE recorded_at >= %s AND recorded_at < %s
                 ORDER BY recorded_at DESC LIMIT %s OFFSET %s"""
        rows = db.execute(
            sql,
            (f"{date_from} 00:00:00", f"{date_to_exclusive} 00:00:00", limit, offset),
            fetch="all",
        )
        cnt  = db.execute(
            "SELECT COUNT(*) AS c FROM sensor_data WHERE recorded_at >= %s AND recorded_at < %s",
            (f"{date_from} 00:00:00", f"{date_to_exclusive} 00:00:00"),
            fetch="one",
        )
    else:
        now = datetime.now()
        since = now - timedelta(minutes=minutes)
        # Luôn lấy các bản ghi mới nhất trong khung thời gian, rồi đảo ngược lại để vẽ theo thời gian tăng dần
        sql   = """SELECT * FROM sensor_data
                 WHERE recorded_at >= %s AND recorded_at <= %s
                 ORDER BY recorded_at DESC LIMIT %s"""
        rows  = db.execute(sql, (since, now, limit), fetch="all") or []
        rows.reverse()
        cnt   = db.execute(
            """SELECT COUNT(*) AS c FROM sensor_data
               WHERE recorded_at >= %s AND recorded_at <= %s""",
            (since, now),
            fetch="one",
        )

    return jsonify({
        "ok": True,
        "data": [_serialize(r) for r in (rows or [])],
        "total": cnt["c"] if cnt else 0,
        "page": page,
        "limit": limit,
    })

    return jsonify({
        "ok": True,
        "data": [_serialize(r) for r in (rows or [])],
        "total": cnt["c"] if cnt else 0,
        "page": page,
        "limit": limit,
    })


# ============================================================================
#  API: /api/alerts  – Danh sách cảnh báo
# ============================================================================
@app.route("/api/alerts")
def api_alerts():
    severity  = request.args.get("severity", "")
    status    = request.args.get("status", "")
    date_from = request.args.get("from")
    date_to   = request.args.get("to")
    recent_hours = request.args.get("recent_hours")
    limit     = min(int(request.args.get("limit", 20)), 200)
    page      = max(int(request.args.get("page", 1)), 1)
    offset    = (page - 1) * limit

    # Các thẻ thống kê vẫn dùng cửa sổ 24 giờ; danh sách hiển thị toàn bộ
    # lịch sử nếu người dùng chưa chọn bộ lọc ngày.
    stats_since = datetime.now() - timedelta(hours=24)
    where, params = [], []
    if severity:
        where.append("severity = %s"); params.append(severity)
    if status:
        where.append("status = %s"); params.append(status)
    if date_from:
        where.append("created_at >= %s"); params.append(f"{date_from} 00:00:00")
    if date_to:
        where.append("created_at <= %s"); params.append(f"{date_to} 23:59:59")
    if recent_hours:
        try:
            recent_since = datetime.now() - timedelta(hours=float(recent_hours))
        except ValueError:
            return jsonify({"ok": False, "error": "recent_hours không hợp lệ"}), 400
        where.append("created_at >= %s"); params.append(recent_since)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.execute(
        f"SELECT * FROM alerts {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        params + [limit, offset], fetch="all"
    )
    cnt = db.execute(
        f"SELECT COUNT(*) AS c FROM alerts {where_sql}", params, fetch="one"
    )

    # Dùng cùng mốc giờ local của backend để không phụ thuộc timezone của MySQL.
    stats = db.execute(
        """SELECT severity, COUNT(*) AS cnt FROM alerts
           WHERE created_at >= %s
           GROUP BY severity""",
        (stats_since,),
        fetch="all"
    )

    return jsonify({
        "ok": True,
        "data": [_serialize(r) for r in (rows or [])],
        "total": cnt["c"] if cnt else 0,
        "page": page,
        "limit": limit,
        "stats_24h": {r["severity"]: r["cnt"] for r in (stats or [])},
    })


# ============================================================================
#  API: /api/alerts/<id>/resolve  – Đánh dấu đã xử lý
# ============================================================================
@app.route("/api/alerts/<int:alert_id>/resolve", methods=["POST"])
def resolve_alert(alert_id):
    return jsonify({
        "ok": False,
        "error": "Cảnh báo được hệ thống tự động xử lý khi điều kiện khôi phục được xác nhận",
    }), 405


# ============================================================================
#  API: /api/control  – Gửi lệnh đến ESP32 qua MQTT
# ============================================================================
@app.route("/api/control", methods=["POST"])
def api_control():
    if not mqtt_client.is_connected():
        return jsonify({"ok": False, "error": "MQTT Broker chưa kết nối hoặc mất liên lạc với ESP32"}), 503
    latest = mqtt_client.get_latest()
    if latest.get("esp32_status") != "online" or latest.get("ts") is None:
        return jsonify({"ok": False, "error": "ESP32 chưa kết nối hoặc chưa gửi dữ liệu trạng thái"}), 503

    data    = request.get_json(silent=True) or {}
    command = data.get("command", "").strip()
    payload = str(data.get("payload", "")).strip()
    client_ip = request.remote_addr or "unknown"

    ALLOWED = {"mode", "pump_in", "pump_out", "threshold", "calib",
               "calib_empty", "calib_full", "reset", "get", "restart"}
    if command not in ALLOWED:
        return jsonify({"ok": False, "error": f"Lệnh không hợp lệ: {command}"}), 400

    if command not in {"calib_empty", "calib_full", "reset", "get", "restart"} and not payload:
        return jsonify({"ok": False, "error": "Thiếu nội dung lệnh (payload)"}), 400

    # Kiểm tra & chuẩn hóa payload theo từng loại lệnh
    if command == "mode":
        payload = payload.upper()
        if payload not in {"AUTO", "MANUAL"}:
            return jsonify({"ok": False, "error": "Chế độ chỉ được là AUTO hoặc MANUAL"}), 400

    elif command in {"pump_in", "pump_out"}:
        payload = payload.upper()
        if payload in {"1", "BẬT"}:
            payload = "ON"
        elif payload in {"0", "TẮT"}:
            payload = "OFF"
        if payload not in {"ON", "OFF"}:
            return jsonify({"ok": False, "error": "Trạng thái bơm chỉ được là ON hoặc OFF"}), 400

    elif command == "threshold":
        parts = [p.strip() for p in payload.split(",")]
        if len(parts) != 4:
            return jsonify({"ok": False, "error": "Ngưỡng cần đúng 4 giá trị: inOn,inOff,outOn,outOff"}), 400
        try:
            a, b, c, d = [float(x) for x in parts]
            if not (0 <= a < b and b < d and d < c <= 100):
                return jsonify({"ok": False, "error": "Cần thỏa mãn: 0 <= inOn < inOff < outOff < outOn <= 100"}), 400
        except ValueError:
            return jsonify({"ok": False, "error": "Giá trị ngưỡng phải là số thực hợp lệ"}), 400

    elif command == "calib":
        parts = [p.strip() for p in payload.split(",")]
        if len(parts) != 2:
            return jsonify({"ok": False, "error": "Cần đúng 2 giá trị dEmpty,dFull"}), 400
        try:
            e, f = [float(x) for x in parts]
            if e - f < 5 or f < 2 or e > 400:
                return jsonify({"ok": False, "error": "dEmpty phải lớn hơn dFull ít nhất 5cm (2..400cm)"}), 400
        except ValueError:
            return jsonify({"ok": False, "error": "Giá trị khoảng cách phải là số thực hợp lệ"}), 400

    elif command == "reset":
        payload = "RESET"

    elif command == "restart":
        payload = "RESTART"

    elif command == "get":
        payload = "GET"

    # Mã cảnh báo dạng chữ thường (thống nhất với nhóm)
    alert_code = None
    if command in {"pump_in", "pump_out"}:
        pump_name = "bơm cấp (IN)" if command == "pump_in" else "bơm thoát (OUT)"
        suffix = "on" if payload == "ON" else "off"
        alert_code = f"{command}_{suffix}"
        if command == "pump_in" and suffix == "on":
            alert_code = "pump_in"
        if command == "pump_out" and suffix == "on":
            alert_code = "pump_out"

    log_id = mqtt_client.publish_command(command, payload, client_ip)
    active_alert = None
    if alert_code:
        active_alert = db.execute(
            """SELECT id, alert_code, created_at, message
               FROM alerts
               WHERE (LOWER(alert_code)=%s) AND status='UNRESOLVED'
               ORDER BY created_at DESC LIMIT 1""",
            (alert_code.lower(),),
            fetch="one",
        )

    response = {
        "ok": True,
        "command": command,
        "payload": payload,
        "log_id": log_id,
    }
    if active_alert:
        response["active_alert"] = {
            "id": active_alert["id"],
            "code": active_alert["alert_code"],
            "created_at": _serialize(active_alert)["created_at"],
            "message": active_alert["message"],
        }
        response["warning"] = (
            f"Lệnh đã gửi tới {pump_name}, nhưng cảnh báo {alert_code} "
            "cùng loại vẫn đang được hệ thống xử lý nên chưa tạo cảnh báo mới."
        )
    return jsonify(response)


# ============================================================================
#  API: /api/config  – Đọc / cập nhật cấu hình hệ thống
# ============================================================================
@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        rows = db.execute("SELECT * FROM system_config ORDER BY config_key", fetch="all")
        cfg  = {r["config_key"]: r["config_value"] for r in (rows or [])}
        cfg["mqtt_broker"] = os.getenv("MQTT_DEVICE_HOST", "192.168.1.100")
        cfg["mqtt_port"] = os.getenv("MQTT_PORT", "1883")
        cfg["topic_prefix"] = os.getenv("MQTT_TOPIC_PREFIX", "iot")
        latest = mqtt_client.get_latest()
        resp = {"ok": True, "config": cfg}
        resp["firmware_defaults"] = load_firmware_defaults()
        if "reported_cfg" in latest:
            resp["esp32_reported"] = latest["reported_cfg"]
        response = jsonify(resp)
        response.headers["Cache-Control"] = "no-store"
        return response

    # POST: cập nhật và gửi xuống ESP32
    data = request.get_json(silent=True) or {}
    updated = []

    # Kiểm tra tính hợp lệ trước khi lưu
    if "in_on_pct" in data and "in_off_pct" in data:
        try:
            if float(data["in_on_pct"]) >= float(data["in_off_pct"]):
                return jsonify({"ok": False, "error": "inOn phải nhỏ hơn inOff"}), 400
        except ValueError:
            pass

    if "out_off_pct" in data and "out_on_pct" in data:
        try:
            if float(data["out_off_pct"]) >= float(data["out_on_pct"]):
                return jsonify({"ok": False, "error": "outOff phải nhỏ hơn outOn"}), 400
        except ValueError:
            pass

    if "d_empty" in data and "d_full" in data:
        try:
            if float(data["d_empty"]) - float(data["d_full"]) < 5:
                return jsonify({"ok": False, "error": "dEmpty phải lớn hơn dFull ít nhất 5cm"}), 400
        except ValueError:
            pass

    for key, val in data.items():
        db.execute(
            "INSERT INTO system_config (config_key,config_value) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE config_value=%s, updated_at=NOW(3)",
            (key, str(val), str(val)),
        )
        updated.append(key)

    mqtt_ok = mqtt_client.is_connected()
    warning_msg = None

    if not mqtt_ok:
        warning_msg = "Đã lưu cấu hình vào máy chủ nhưng chưa thể gửi tới ESP32 do mất kết nối MQTT Broker."

    # Nếu thay đổi ngưỡng bơm -> gửi xuống ESP32
    threshold_keys = {"in_on_pct", "in_off_pct", "out_on_pct", "out_off_pct"}
    if threshold_keys & set(updated):
        rows = db.execute("SELECT config_key,config_value FROM system_config WHERE config_key IN (%s,%s,%s,%s)",
                          ("in_on_pct", "in_off_pct", "out_on_pct", "out_off_pct"), fetch="all")
        cfg = {r["config_key"]: r["config_value"] for r in (rows or [])}
        thr = f"{cfg.get('in_on_pct',30)},{cfg.get('in_off_pct',70)},{cfg.get('out_on_pct',90)},{cfg.get('out_off_pct',80)}"
        mqtt_client.publish_command("threshold", thr, request.remote_addr or "web")

    if {"d_empty", "d_full"} & set(updated):
        rows = db.execute("SELECT config_key,config_value FROM system_config WHERE config_key IN (%s,%s)",
                          ("d_empty", "d_full"), fetch="all")
        cfg = {r["config_key"]: r["config_value"] for r in (rows or [])}
        calib = f"{cfg.get('d_empty',18)},{cfg.get('d_full',5)}"
        mqtt_client.publish_command("calib", calib, request.remote_addr or "web")

    res_data = {"ok": True, "updated": updated, "mqtt_sent": mqtt_ok}
    if warning_msg:
        res_data["warning"] = warning_msg
    return jsonify(res_data)


# ============================================================================
#  API: /api/logs  – Nhật ký hệ thống
# ============================================================================
@app.route("/api/logs")
def api_logs():
    limit     = min(int(request.args.get("limit", 50)), 500)
    page      = max(int(request.args.get("page", 1)), 1)
    offset    = (page - 1) * limit
    component = request.args.get("component", "")
    level     = request.args.get("level", "")
    date_from = request.args.get("from")
    date_to   = request.args.get("to")

    where, params = [], []
    if component:
        where.append("component = %s"); params.append(component)
    if level:
        where.append("log_level = %s"); params.append(level)
    if date_from:
        where.append("logged_at >= %s"); params.append(f"{date_from} 00:00:00")
    if date_to:
        date_to_exclusive = (
            datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        where.append("logged_at < %s"); params.append(f"{date_to_exclusive} 00:00:00")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = db.execute(
        f"SELECT * FROM system_logs {where_sql} ORDER BY logged_at DESC LIMIT %s OFFSET %s",
        params + [limit, offset], fetch="all"
    )
    cnt = db.execute(
        f"SELECT COUNT(*) AS c FROM system_logs {where_sql}", params, fetch="one"
    )
    return jsonify({
        "ok": True,
        "data": [_serialize(r) for r in (rows or [])],
        "total": cnt["c"] if cnt else 0,
    })


# ============================================================================
#  API: /api/control_logs  – Nhật ký điều khiển
# ============================================================================
@app.route("/api/control_logs")
def api_control_logs():
    try:
        limit = min(int(request.args.get("limit", 20)), 200)
    except (TypeError, ValueError):
        limit = 20
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    offset = (page - 1) * limit
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    device = request.args.get("device", "").strip()

    where, params = [], []
    if date_from:
        where.append("sent_at >= %s")
        params.append(f"{date_from} 00:00:00")
    if date_to:
        try:
            date_to_exclusive = (
                datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
        except ValueError:
            return jsonify({"ok": False, "error": "Ngày kết thúc không hợp lệ"}), 400
        where.append("sent_at < %s")
        params.append(f"{date_to_exclusive} 00:00:00")
    device_commands = {
        "Bơm cấp (IN)": "pump_in",
        "Bơm thoát (OUT)": "pump_out",
        "Chế độ": "mode",
    }
    if device in device_commands:
        where.append("command = %s")
        params.append(device_commands[device])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.execute(
        f"SELECT * FROM control_logs {where_sql} ORDER BY sent_at DESC LIMIT %s OFFSET %s",
        params + [limit, offset], fetch="all"
    )
    cnt = db.execute(
        f"SELECT COUNT(*) AS c FROM control_logs {where_sql}",
        params, fetch="one"
    )

    serialized = []
    for r in (rows or []):
        d = _serialize(r)
        cmd = d.get("command", "")
        pld = str(d.get("payload", ""))
        if cmd == "pump_in":
            d["device"] = "Bơm cấp (IN)"
            d["payload"] = "Bật" if pld.upper() in ["ON", "1", "BẬT"] else "Tắt"
        elif cmd == "pump_out":
            d["device"] = "Bơm thoát (OUT)"
            d["payload"] = "Bật" if pld.upper() in ["ON", "1", "BẬT"] else "Tắt"
        elif cmd == "mode":
            d["device"] = "Chế độ"
            d["payload"] = pld.upper()
        else:
            d["device"] = cmd
        serialized.append(d)

    return jsonify({
        "ok": True,
        "data": serialized,
        "total": cnt["c"] if cnt else 0,
    })


# ============================================================================
#  API: /api/chart  – Dữ liệu biểu đồ (tổng hợp theo giờ / ngày)
# ============================================================================
@app.route("/api/chart")
def api_chart():
    period = request.args.get("period", "day")  # hour | day | week | month
    interval_map = {
        "hour": ("30 MINUTE", "%Y-%m-%d %H:%i"),
        "day": ("24 HOUR", "%Y-%m-%d %H:00"),
        "week": ("7 DAY", "%Y-%m-%d %H:00"),
        "month": ("30 DAY", "%Y-%m-%d"),
    }
    interval, fmt = interval_map.get(period, ("24 HOUR", "%Y-%m-%d %H:00"))

    rows = db.execute(
        f"""SELECT
              DATE_FORMAT(recorded_at, '{fmt}') AS ts,
              AVG(water_level) AS avg_level,
              MAX(water_level) AS max_level,
              MIN(water_level) AS min_level
            FROM sensor_data
            WHERE recorded_at >= NOW() - INTERVAL {interval}
            GROUP BY DATE_FORMAT(recorded_at, '{fmt}')
            ORDER BY ts ASC
            LIMIT 500""",
        fetch="all",
    )
    return jsonify({
        "ok": True,
        "labels": [r["ts"] for r in (rows or [])],
        "avg":    [round(float(r["avg_level"]), 1) for r in (rows or [])],
        "max":    [round(float(r["max_level"]), 1) for r in (rows or [])],
        "min":    [round(float(r["min_level"]), 1) for r in (rows or [])],
    })


# ── Helpers ──────────────────────────────────────────────────────────────────

def _serialize(row):
    """Chuyển datetime → string để JSON serializable."""
    if row is None:
        return None
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat(timespec="seconds")
        elif isinstance(v, (bytes, bytearray)):
            out[k] = v.decode("utf-8", errors="replace")
        else:
            out[k] = v
    return out


# ── Khởi động ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_mqtt()
    try:
        from notifications.mail_worker import start_mail_worker
        from notifications.notify_watchdog import start_watchdog
        start_mail_worker()
        start_watchdog()
    except Exception as _e:
        logger.warning(f"[App] start notification services error: {_e}")
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", 5000)),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        use_reloader=False,   # tắt reloader để MQTT không bị start 2 lần
    )
