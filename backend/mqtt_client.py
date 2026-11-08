# ============================================================================
#  mqtt_client.py – Kết nối MQTT, nhận dữ liệu từ ESP32, lưu vào MySQL
# ============================================================================
import json, os, logging, threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Tải cấu hình từ .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# pyrefly: ignore[missing-import]
import paho.mqtt.client as mqtt_lib
import db

logger = logging.getLogger(__name__)

# Topic prefix
P = os.getenv("MQTT_TOPIC_PREFIX", "iot")

# Dữ liệu mới nhất (shared state, thread-safe read)
_latest: dict = {}
_lock = threading.Lock()
_client: mqtt_lib.Client | None = None
_recovery_since: dict[str, datetime] = {}


def get_latest() -> dict:
    with _lock:
        return dict(_latest)


def is_connected() -> bool:
    if _client:
        try:
            return _client.is_connected()
        except Exception:
            pass
    with _lock:
        return _latest.get("mqtt_connected", False)


def _map_severity(code: str, msg: str) -> str:
    code_lower = str(code).lower()
    if any(k in code_lower for k in ("high_level", "low_level", "overrun", "fault", "no_flow")):
        return "DANGER"
    if any(k in code_lower for k in ("sensor", "trend", "pump")):
        return "WARNING"
    return "INFO"


def _active_alert_exists(code: str) -> bool:
    code_lower = str(code).lower()
    row = db.execute(
        "SELECT id FROM alerts WHERE (LOWER(alert_code)=%s) AND status='UNRESOLVED' "
        "ORDER BY created_at DESC LIMIT 1",
        (code_lower,),
        fetch="one",
    )
    return bool(row)


def _resolve_alerts_from_sensor(data: dict) -> None:
    """Tự đóng cảnh báo sau khi điều kiện khôi phục ổn định đủ lâu (dùng mã chữ thường)."""
    now = datetime.now()
    try:
        level = float(data.get("level"))
        sensor_valid = not bool(data.get("err", 0))
        fault = str(data.get("fault", "none")).lower()
    except (TypeError, ValueError):
        return

    # Danh mục mã cảnh báo dạng chữ thường thống nhất với firmware và nhóm
    checks = [
        ("high_level", level < 88, timedelta(minutes=2)),
        ("low_level", level > 32, timedelta(minutes=2)),
        ("sensor_error", sensor_valid, timedelta(minutes=1)),
        ("sensor", sensor_valid, timedelta(minutes=1)),
        ("pump_in_off", sensor_valid and "pump_in" not in fault, timedelta(minutes=1)),
        ("pump_out_off", sensor_valid and "pump_out" not in fault, timedelta(minutes=1)),
        ("high_trend", sensor_valid, timedelta(minutes=3)),
        ("mode", sensor_valid, timedelta(0)),
        ("pump_overrun", not fault.startswith("pump_overrun"), timedelta(minutes=1)),
        ("no_flow_in", not fault.startswith("no_flow"), timedelta(minutes=1)),
        ("no_flow_out", not fault.startswith("no_flow"), timedelta(minutes=1)),
    ]
    for code, recovered, stable_for in checks:
        if not recovered:
            _recovery_since.pop(code, None)
            continue
        if code not in _recovery_since:
            _recovery_since[code] = now
        if now - _recovery_since[code] < stable_for:
            continue
        result = db.execute(
            """UPDATE alerts
               SET status='RESOLVED', resolved_at=%s, resolved_by='SYSTEM',
                   note=%s, updated_at=%s
               WHERE (LOWER(alert_code)=%s) AND status='UNRESOLVED'""",
            (
                now,
                "Hệ thống tự động xác nhận điều kiện cảnh báo đã kết thúc",
                now,
                code.lower(),
            ),
        )
        if result:
            db.execute(
                "INSERT INTO system_logs "
                "(log_level,component,event_type,message) VALUES (%s,%s,%s,%s)",
                (
                    "INFO", "alerts", "auto_resolved",
                    f"Tự động xử lý cảnh báo {code} sau khi điều kiện ổn định",
                ),
            )
        _recovery_since.pop(code, None)


# ── Callbacks ────────────────────────────────────────────────────────────────

def _on_connect(client, userdata, flags, rc, props=None):
    if rc == 0:
        logger.info("[MQTT] Connected to broker")
        with _lock:
            _latest["mqtt_connected"] = True
        client.subscribe(f"{P}/data")
        client.subscribe(f"{P}/alert")
        client.subscribe(f"{P}/status")
        client.subscribe(f"{P}/ack")
        client.subscribe(f"{P}/cfg")
        db.execute(
            "INSERT INTO system_logs (log_level,component,event_type,message) VALUES (%s,%s,%s,%s)",
            ("INFO", "mqtt", "connected", "Kết nối MQTT Broker thành công"),
        )
    else:
        logger.error(f"[MQTT] Connect failed rc={rc}")
        with _lock:
            _latest["mqtt_connected"] = False


def _on_disconnect(client, userdata, *args, **kwargs):
    # Hỗ trợ cả paho v1 và v2 signatures
    rc = args[0] if args else kwargs.get("reason_code", 0)
    logger.warning(f"[MQTT] Disconnected rc={rc}")
    with _lock:
        _latest["mqtt_connected"] = False
    try:
        db.execute(
            "INSERT INTO system_logs (log_level,component,event_type,message) VALUES (%s,%s,%s,%s)",
            ("WARNING", "mqtt", "disconnected", f"Mất kết nối MQTT (rc={rc})"),
        )
    except Exception:
        pass


def _on_message(client, userdata, msg):
    topic = msg.topic
    try:
        payload = msg.payload.decode("utf-8").strip()
    except Exception:
        return

    logger.debug(f"[MQTT] {topic}: {payload[:120]}")

    # ── /data ────────────────────────────────────────────────────────────────
    if topic == f"{P}/data":
        try:
            d = json.loads(payload)
        except json.JSONDecodeError:
            return

        with _lock:
            _latest.update(d)
            _latest["ts"] = datetime.now().isoformat(timespec="seconds")
            _latest["mqtt_connected"] = True

        try:
            db.execute(
                """INSERT INTO sensor_data
                   (water_level, distance_cm, pump_in, pump_out, auto_mode,
                    sensor_err, fault_code, rssi, uptime_sec, esp32_id, topic)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    float(d.get("level", 0)),
                    float(d.get("dist", 0)),
                    int(bool(d.get("in", 0))),
                    int(bool(d.get("out", 0))),
                    int(bool(d.get("auto", 1))),
                    int(bool(d.get("err", 0))),
                    str(d.get("fault", "none"))[:32],
                    int(d.get("rssi", 0)),
                    int(d.get("up", 0)),
                    _extract_esp32_id(d),
                    topic,
                ),
            )
        except Exception as e:
            logger.error(f"[DB] sensor_data insert error: {e}")

        _resolve_alerts_from_sensor(d)
        # Bỏ ghi log rác data_received mỗi 2s để tránh làm ngập database

        # Chuyển tiếp tới bộ quy tắc thông báo email
        try:
            from notifications.notifier import on_telemetry_received
            status_dict = {
                "water_level": float(d.get("level", 0)),
                "distance_cm": float(d.get("dist", 0)),
                "pump_in": int(bool(d.get("in", 0))),
                "pump_out": int(bool(d.get("out", 0))),
                "auto_mode": int(bool(d.get("auto", 1))),
                "sensor_err": int(bool(d.get("err", 0))),
                "fault_code": str(d.get("fault", "none")),
                "esp32_id": _extract_esp32_id(d),
                "esp32_status": "online",
            }
            on_telemetry_received(status_dict)
        except Exception as _ne:
            logger.debug(f"[MQTT->Notifier] on_telemetry_received error: {_ne}")

    # ── /alert ───────────────────────────────────────────────────────────────
    elif topic == f"{P}/alert":
        try:
            d = json.loads(payload)
            # Chuẩn hóa mã cảnh báo sang chữ thường (lowercase) theo thống nhất của nhóm
            code = str(d.get("code", "unknown")).lower()
            msg_txt = str(d.get("msg", ""))
            sev = _map_severity(code, msg_txt)
            latest = get_latest()
            if not _active_alert_exists(code):
                db.execute(
                    """INSERT INTO alerts (alert_code, message, severity, water_level, status)
                       VALUES (%s,%s,%s,%s,'UNRESOLVED')""",
                    (code, msg_txt, sev, latest.get("level", None)),
                )
                logger.info(f"[ALERT] {sev} {code}: {msg_txt}")
            else:
                logger.info(f"[ALERT] Bỏ qua cảnh báo lặp {code} trong cùng đợt sự cố")

            # Kích hoạt thông báo email nếu là cảnh báo từ thiết bị
            try:
                from notifications.notifier import on_esp32_alert
                on_esp32_alert(d)
            except Exception as _ne:
                logger.debug(f"[MQTT->Notifier] on_esp32_alert error: {_ne}")
        except Exception as e:
            logger.error(f"[DB] alert insert error: {e}")

    # ── /ack ─────────────────────────────────────────────────────────────────
    elif topic == f"{P}/ack":
        try:
            is_ok = payload.startswith("ok:")
            cmd_filter = ""
            if "mode" in payload:
                cmd_filter = "AND command='mode'"
            elif "pump_in" in payload:
                cmd_filter = "AND command='pump_in'"
            elif "pump_out" in payload:
                cmd_filter = "AND command='pump_out'"
            elif "pump" in payload:
                cmd_filter = "AND command IN ('pump_in', 'pump_out')"
            elif "threshold" in payload:
                cmd_filter = "AND command='threshold'"
            elif "calib" in payload:
                cmd_filter = "AND command LIKE 'calib%'"
            elif "reset" in payload:
                cmd_filter = "AND command='reset'"
            elif "restart" in payload:
                cmd_filter = "AND command='restart'"
            elif "get" in payload:
                cmd_filter = "AND command='get'"

            sql = f"""UPDATE control_logs SET acked_at=NOW(3), ack_payload=%s,
                   status=%s WHERE status='SENT' {cmd_filter} ORDER BY sent_at DESC LIMIT 1"""
            db.execute(
                sql,
                (payload[:255], "ACK_OK" if is_ok else "ACK_ERR"),
            )
            db.execute(
                "INSERT INTO system_logs (log_level,component,event_type,message) VALUES (%s,%s,%s,%s)",
                ("INFO", "mqtt", "ack_received", f"ACK nhận: {payload[:100]}"),
            )
        except Exception as e:
            logger.error(f"[DB] ack update error: {e}")

    # ── /status ──────────────────────────────────────────────────────────────
    elif topic == f"{P}/status":
        with _lock:
            _latest["esp32_status"] = payload
        try:
            db.execute(
                "INSERT INTO system_logs (log_level,component,event_type,message) VALUES (%s,%s,%s,%s)",
                ("INFO", "esp32", "status_change", f"ESP32 status: {payload}"),
            )
        except Exception:
            pass

    # ── /cfg ─────────────────────────────────────────────────────────────────
    elif topic == f"{P}/cfg":
        try:
            cfg_obj = json.loads(payload)
            with _lock:
                _latest["reported_cfg"] = cfg_obj
                _latest["cfg_updated_at"] = datetime.now().isoformat()
            logger.info(f"[MQTT] Đã nhận cấu hình từ ESP32: {payload}")
        except Exception as e:
            logger.error(f"[MQTT] Lỗi parse /cfg: {e}")


def _extract_esp32_id(d: dict) -> str:
    return d.get("id", "esp32-ao-demo")


# ── Gửi lệnh ─────────────────────────────────────────────────────────────────

def publish_command(command: str, payload: str, client_ip: str = "web") -> int:
    """Gửi lệnh đến ESP32 qua MQTT. Trả về log_id."""
    topic = f"{P}/cmd/{command}"
    if _client and _client.is_connected():
        _client.publish(topic, payload, qos=1)
    log_id = db.execute(
        """INSERT INTO control_logs (command, payload, topic, status, initiated_by, client_ip)
           VALUES (%s,%s,%s,'SENT',%s,%s)""",
        (command, payload, topic, "web", client_ip),
    )
    db.execute(
        "INSERT INTO system_logs (log_level,component,event_type,message) VALUES (%s,%s,%s,%s)",
        ("INFO", "flask", "cmd_sent", f"Gửi lệnh {command}={payload} đến ESP32"),
    )
    return log_id


# ── Khởi động ────────────────────────────────────────────────────────────────

def start():
    global _client
    if _client is not None:
        return
    # Tương thích cả paho-mqtt v1.x (như 1.6.1) và v2.x
    client_kwargs = {"client_id": "flask-ao-backend"}
    if hasattr(mqtt_lib, "CallbackAPIVersion"):
        client_kwargs["callback_api_version"] = getattr(mqtt_lib, "CallbackAPIVersion").VERSION2

    _client = mqtt_lib.Client(**client_kwargs)
    _client.username_pw_set(
        os.getenv("MQTT_USER", "esp32"),
        os.getenv("MQTT_PASS", "esp32pass"),
    )
    _client.on_connect    = _on_connect
    _client.on_disconnect = _on_disconnect
    _client.on_message    = _on_message

    # LWT – nếu backend tắt đột ngột
    _client.will_set(f"{P}/backend/status", "offline", retain=True)

    host = os.getenv("MQTT_HOST", "127.0.0.1")
    port = int(os.getenv("MQTT_PORT", 1883))
    logger.info(f"[MQTT] Connecting to {host}:{port}")

    try:
        _client.connect_async(host, port, keepalive=60)
        _client.loop_start()
    except Exception as e:
        logger.error(f"[MQTT] Cannot connect: {e}")
        with _lock:
            _latest["mqtt_connected"] = False


def stop():
    global _client
    if _client:
        try:
            _client.loop_stop()
            _client.disconnect()
        except Exception:
            pass
        _client = None
