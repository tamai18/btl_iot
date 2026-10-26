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

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

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
#  API: /api/status  – Trạng thái tổng quan hệ thống
# ============================================================================
@app.route("/api/status")
def api_status():
    latest = mqtt_client.get_latest()
    row = db.execute(
        "SELECT * FROM sensor_data ORDER BY recorded_at DESC LIMIT 1", fetch="one"
    )
    cfg_rows = db.execute("SELECT config_key, config_value FROM system_config", fetch="all")
    cfg = {r["config_key"]: r["config_value"] for r in (cfg_rows or [])}

    count = db.execute(
        "SELECT COUNT(*) AS cnt FROM sensor_data", fetch="one"
    )

    return jsonify({
        "ok": True,
        "latest": latest,
        "last_record": _serialize(row),
        "config": cfg,
        "total_records": count["cnt"] if count else 0,
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "mqtt_connected": mqtt_client.is_connected(),
        "esp32_status": latest.get("esp32_status", "unknown"),
        "db_info": db.get_db_info(),
    })


# ============================================================================
#  API: /api/sensor  – Dữ liệu cảm biến (biểu đồ / lịch sử)
# ============================================================================
@app.route("/api/sensor")
def api_sensor():
    minutes   = int(request.args.get("minutes", 30))
    date_from = request.args.get("from")   # YYYY-MM-DD
    date_to   = request.args.get("to")
    limit     = min(int(request.args.get("limit", 500)), 2000)
    page      = max(int(request.args.get("page", 1)), 1)
    offset    = (page - 1) * limit

    if date_from and date_to:
        sql = """SELECT * FROM sensor_data
                 WHERE recorded_at BETWEEN %s AND %s
                 ORDER BY recorded_at DESC LIMIT %s OFFSET %s"""
        rows = db.execute(sql, (f"{date_from} 00:00:00", f"{date_to} 23:59:59", limit, offset), fetch="all")
        cnt  = db.execute(
            "SELECT COUNT(*) AS c FROM sensor_data WHERE recorded_at BETWEEN %s AND %s",
            (f"{date_from} 00:00:00", f"{date_to} 23:59:59"), fetch="one"
        )
    else:
        now = datetime.now()
        since = now - timedelta(minutes=minutes)
        latest = request.args.get("latest", "0") == "1"
        order = "DESC" if latest else "ASC"
        sql   = f"""SELECT * FROM sensor_data
                   WHERE recorded_at >= %s AND recorded_at <= %s
                   ORDER BY recorded_at {order} LIMIT %s"""
        rows  = db.execute(sql, (since, now, limit), fetch="all")
        if latest and rows:
            rows.reverse()
        cnt   = {"c": len(rows) if rows else 0}

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
    limit     = min(int(request.args.get("limit", 20)), 200)
    page      = max(int(request.args.get("page", 1)), 1)
    offset    = (page - 1) * limit

    # Danh sách và các thẻ thống kê phải dùng cùng một cửa sổ 24 giờ.
    stats_since = datetime.now() - timedelta(hours=24)
    where, params = ["created_at >= %s"], [stats_since]
    if severity:
        where.append("severity = %s"); params.append(severity)
    if status:
        where.append("status = %s"); params.append(status)
    if date_from:
        where.append("created_at >= %s"); params.append(f"{date_from} 00:00:00")
    if date_to:
        where.append("created_at <= %s"); params.append(f"{date_to} 23:59:59")

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
    data    = request.get_json(silent=True) or {}
    command = data.get("command", "").strip()
    payload = str(data.get("payload", "")).strip()
    client_ip = request.remote_addr or "unknown"

    ALLOWED = {"mode", "pump_in", "pump_out", "threshold", "calib",
               "calib_empty", "calib_full", "reset", "get", "restart"}
    if command not in ALLOWED:
        return jsonify({"ok": False, "error": f"Lệnh không hợp lệ: {command}"}), 400
    if not payload:
        return jsonify({"ok": False, "error": "Thiếu payload"}), 400

    alert_code = None
    if command in {"pump_in", "pump_out"}:
        pump_name = "bơm cấp (IN)" if command == "pump_in" else "bơm thoát (OUT)"
        suffix = "ON" if payload.upper() in {"ON", "1", "BẬT"} else "OFF"
        alert_code = f"{command.upper()}_{suffix}"
        if command == "pump_in" and suffix == "ON":
            alert_code = "PUMP_IN"
        if command == "pump_out" and suffix == "ON":
            alert_code = "PUMP_OUT"

    log_id = mqtt_client.publish_command(command, payload, client_ip)
    active_alert = None
    if alert_code:
        active_alert = db.execute(
            """SELECT id, alert_code, created_at, message
               FROM alerts
               WHERE alert_code=%s AND status='UNRESOLVED'
               ORDER BY created_at DESC LIMIT 1""",
            (alert_code,),
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
        return jsonify({"ok": True, "config": cfg})

    # POST: cập nhật và gửi xuống ESP32
    data = request.get_json(silent=True) or {}
    updated = []
    for key, val in data.items():
        db.execute(
            "INSERT INTO system_config (config_key,config_value) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE config_value=%s, updated_at=NOW(3)",
            (key, str(val), str(val)),
        )
        updated.append(key)

    # Nếu thay đổi ngưỡng bơm -> gửi xuống ESP32
    threshold_keys = {"in_on_pct", "in_off_pct", "out_on_pct", "out_off_pct"}
    if threshold_keys & set(updated):
        rows = db.execute("SELECT config_key,config_value FROM system_config WHERE config_key IN (%s,%s,%s,%s)",
                          ("in_on_pct", "in_off_pct", "out_on_pct", "out_off_pct"), fetch="all")
        cfg = {r["config_key"]: r["config_value"] for r in (rows or [])}
        thr = f"{cfg.get('in_on_pct',30)},{cfg.get('in_off_pct',50)},{cfg.get('out_on_pct',90)},{cfg.get('out_off_pct',80)}"
        mqtt_client.publish_command("threshold", thr, request.remote_addr or "web")

    if {"d_empty", "d_full"} & set(updated):
        rows = db.execute("SELECT config_key,config_value FROM system_config WHERE config_key IN (%s,%s)",
                          ("d_empty", "d_full"), fetch="all")
        cfg = {r["config_key"]: r["config_value"] for r in (rows or [])}
        calib = f"{cfg.get('d_empty',100)},{cfg.get('d_full',10)}"
        mqtt_client.publish_command("calib", calib, request.remote_addr or "web")

    return jsonify({"ok": True, "updated": updated})


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

    where, params = [], []
    if component:
        where.append("component = %s"); params.append(component)
    if level:
        where.append("log_level = %s"); params.append(level)
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
    limit  = min(int(request.args.get("limit", 20)), 200)
    page   = max(int(request.args.get("page", 1)), 1)
    offset = (page - 1) * limit
    rows   = db.execute(
        "SELECT * FROM control_logs ORDER BY sent_at DESC LIMIT %s OFFSET %s",
        (limit, offset), fetch="all"
    )
    cnt = db.execute("SELECT COUNT(*) AS c FROM control_logs", fetch="one")

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
#  API: /api/chart  – Dữ liệu biểu đồ (tổng hợp theo giờ)
# ============================================================================
@app.route("/api/chart")
def api_chart():
    period = request.args.get("period", "day")  # hour | day | week | month
    interval_map = {"hour": "30 MINUTE", "day": "24 HOUR", "week": "7 DAY", "month": "30 DAY"}
    interval = interval_map.get(period, "24 HOUR")

    rows = db.execute(
        f"""SELECT
              DATE_FORMAT(recorded_at, '%Y-%m-%d %H:%i') AS ts,
              AVG(water_level) AS avg_level,
              MAX(water_level) AS max_level,
              MIN(water_level) AS min_level
            FROM sensor_data
            WHERE recorded_at >= NOW() - INTERVAL {interval}
            GROUP BY DATE_FORMAT(recorded_at, '%Y-%m-%d %H:%i')
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
    mqtt_client.start()
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", 5000)),
        debug=os.getenv("FLASK_DEBUG", "true").lower() == "true",
        use_reloader=False,   # tắt reloader để MQTT không bị start 2 lần
    )
