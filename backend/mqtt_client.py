# ============================================================================
#  mqtt_client.py – Kết nối MQTT, nhận dữ liệu từ ESP32, lưu vào MySQL
# ============================================================================
import json, os, logging, threading
from datetime import datetime
from dotenv import load_dotenv

# Tải cấu hình từ .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# pyrefly: ignore[missing-import]
import paho.mqtt.client as mqtt_lib
import db

logger = logging.getLogger(__name__)

# Topic prefix
P = os.getenv("MQTT_TOPIC_PREFIX", "iot-ao-demo-123")

# Dữ liệu mới nhất (shared state, thread-safe read)
_latest: dict = {}
_lock = threading.Lock()
_client: mqtt_lib.Client | None = None


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
    code_upper = code.upper()
    if any(k in code_upper for k in ("HIGH_LEVEL", "LOW_LEVEL", "OVERRUN", "FAULT", "NO_FLOW")):
        return "DANGER"
    if any(k in code_upper for k in ("SENSOR", "HIGH_TREND", "TREND", "PUMP")):
        return "WARNING"
    return "INFO"


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


def _on_disconnect(client, userdata, rc, props=None, reason=None):
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

        # Ghi system_log nhẹ
        try:
            db.execute(
                "INSERT INTO system_logs (log_level,component,event_type,message) VALUES (%s,%s,%s,%s)",
                ("INFO", "mqtt", "data_received",
                 f"Nhận dữ liệu ESP32: level={d.get('level',0):.1f}% dist={d.get('dist',0):.1f}cm"),
            )
        except Exception:
            pass

    # ── /alert ───────────────────────────────────────────────────────────────
    elif topic == f"{P}/alert":
        try:
            d = json.loads(payload)
            code = str(d.get("code", "UNKNOWN"))
            msg_txt = str(d.get("msg", ""))
            sev = _map_severity(code, msg_txt)
            latest = get_latest()
            db.execute(
                """INSERT INTO alerts (alert_code, message, severity, water_level, status)
                   VALUES (%s,%s,%s,%s,'PENDING')""",
                (code, msg_txt, sev, latest.get("level", None)),
            )
            logger.info(f"[ALERT] {sev} {code}: {msg_txt}")
        except Exception as e:
            logger.error(f"[DB] alert insert error: {e}")

    # ── /ack ─────────────────────────────────────────────────────────────────
    elif topic == f"{P}/ack":
        try:
            is_ok = payload.startswith("ok:")
            db.execute(
                """UPDATE control_logs SET acked_at=NOW(3), ack_payload=%s,
                   status=%s WHERE status='SENT' ORDER BY sent_at DESC LIMIT 1""",
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
    try:
        _client = mqtt_lib.Client(
            mqtt_lib.CallbackAPIVersion.VERSION2,
            client_id="flask-ao-backend",
        )
    except (AttributeError, TypeError):
        _client = mqtt_lib.Client(client_id="flask-ao-backend")
    _client.username_pw_set(
        os.getenv("MQTT_USER", "esp32"),
        os.getenv("MQTT_PASS", "esp32pass"),
    )
    _client.on_connect    = _on_connect
    _client.on_disconnect = _on_disconnect
    _client.on_message    = _on_message

    # LWT – nếu backend tắt đột ngột
    _client.will_set(f"{P}/backend/status", "offline", retain=True)

    host = os.getenv("MQTT_HOST", "192.168.1.100")
    port = int(os.getenv("MQTT_PORT", 1883))
    logger.info(f"[MQTT] Connecting to {host}:{port}")

    try:
        _client.connect(host, port, keepalive=60)
        _client.loop_start()
    except Exception as e:
        logger.error(f"[MQTT] Cannot connect: {e}")
        with _lock:
            _latest["mqtt_connected"] = False


def stop():
    if _client:
        _client.loop_stop()
        _client.disconnect()
