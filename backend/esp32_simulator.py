# ============================================================================
#  esp32_simulator.py – Giả lập vi điều khiển ESP32 và cảm biến HC-SR04
#  Dùng cho Bước 3: Kiểm thử MQTT, Mosquitto và Backend mà không cần phần cứng
# ============================================================================
import json, time, os, sys, random, signal
from datetime import datetime
from dotenv import load_dotenv

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Tải cấu hình từ .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

try:
    # pyrefly: ignore[missing-import]
    import paho.mqtt.client as mqtt_lib
except ImportError:
    print("[LỖI] Chưa cài đặt thư viện paho-mqtt! Hãy chạy: pip install paho-mqtt")
    sys.exit(1)

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER", "esp32")
MQTT_PASS = os.getenv("MQTT_PASS", "esp32pass")
P         = os.getenv("MQTT_TOPIC_PREFIX", "iot-ao-demo-123")

# Trạng thái ESP32 giả lập
state = {
    "level": 45.5,          # Mực nước (%)
    "dist": 56.7,           # Khoảng cách cảm biến (cm)
    "pump_in": 0,           # Bơm cấp (0=Tắt, 1=Bật)
    "pump_out": 0,          # Bơm thoát (0=Tắt, 1=Bật)
    "auto_mode": 1,         # 1=AUTO, 0=MANUAL
    "sensor_err": 0,
    "fault_code": "none",
    "rssi": -55,
    "uptime": 0,
    "d_empty": 100.0,
    "d_full": 10.0,
    "in_on": 30.0,
    "in_off": 50.0,
    "out_on": 90.0,
    "out_off": 80.0,
    "limit_high": 95.0,
    "limit_low": 5.0,
}

running = True
client = None

def signal_handler(sig, frame):
    global running
    print("\n[ESP32 SIM] Đang dừng giả lập...")
    running = False
    if client:
        client.publish(f"{P}/status", "offline", qos=1, retain=True)
        client.disconnect()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def on_connect(c, userdata, flags, rc, *args):
    if rc == 0:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [MQTT] Đã kết nối Broker {MQTT_HOST}:{MQTT_PORT}")
        c.publish(f"{P}/status", "online", qos=1, retain=True)
        # Đăng ký nhận lệnh điều khiển
        c.subscribe(f"{P}/cmd/#")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [MQTT] Đã đăng ký lắng nghe lệnh: {P}/cmd/#")
        send_cfg()
    else:
        print(f"[MQTT] Lỗi kết nối, mã lỗi rc={rc}")

def on_message(c, userdata, msg):
    topic = msg.topic
    cmd = topic.replace(f"{P}/cmd/", "")
    try:
        payload = msg.payload.decode("utf-8").strip()
    except Exception:
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] [LỆNH NHẬN] {cmd} => '{payload}'")

    if cmd == "mode":
        if payload.upper() == "AUTO":
            state["auto_mode"] = 1
            ack("ok:mode=AUTO")
        elif payload.upper() == "MANUAL":
            state["auto_mode"] = 0
            ack("ok:mode=MANUAL")
        send_alert("MODE", f"Chế độ {payload.upper()} được kích hoạt", "INFO")

    elif cmd == "pump_in":
        # Điều khiển bơm IN -> tự động chuyển sang MANUAL
        state["auto_mode"] = 0
        if payload.upper() == "ON":
            state["pump_in"] = 1
            state["pump_out"] = 0  # Khoá chéo 2 bơm
            ack("ok:pump_in=ON")
            send_alert("PUMP_IN", "Máy bơm cấp nước đã bật", "INFO")
        else:
            state["pump_in"] = 0
            ack("ok:pump_in=OFF")
            send_alert("PUMP_IN_OFF", "Máy bơm cấp nước đã tắt", "WARNING")

    elif cmd == "pump_out":
        # Điều khiển bơm OUT -> tự động chuyển sang MANUAL
        state["auto_mode"] = 0
        if payload.upper() == "ON":
            state["pump_out"] = 1
            state["pump_in"] = 0  # Khoá chéo 2 bơm
            ack("ok:pump_out=ON")
            send_alert("PUMP_OUT", "Máy bơm thoát nước đã bật", "INFO")
        else:
            state["pump_out"] = 0
            ack("ok:pump_out=OFF")
            send_alert("PUMP_OUT_OFF", "Máy bơm thoát nước đã tắt", "WARNING")

    elif cmd == "threshold":
        # inOn,inOff,outOn,outOff
        parts = [p.strip() for p in payload.split(",")]
        if len(parts) >= 4:
            state["in_on"] = float(parts[0])
            state["in_off"] = float(parts[1])
            state["out_on"] = float(parts[2])
            state["out_off"] = float(parts[3])
            ack("ok:threshold")
            send_cfg()

    elif cmd == "calib":
        # dEmpty,dFull
        parts = [p.strip() for p in payload.split(",")]
        if len(parts) >= 2:
            state["d_empty"] = float(parts[0])
            state["d_full"] = float(parts[1])
            ack("ok:calib")
            send_cfg()

    elif cmd == "calib_empty":
        val = float(payload) if payload else state["dist"]
        state["d_empty"] = val
        ack("ok:calib_empty")
        send_cfg()

    elif cmd == "calib_full":
        val = float(payload) if payload else state["dist"]
        state["d_full"] = val
        ack("ok:calib_full")
        send_cfg()

    elif cmd == "reset":
        state["fault_code"] = "none"
        state["sensor_err"] = 0
        ack("ok:reset")
        send_alert("RESET", "Đã xóa lỗi chốt hệ thống", "INFO")

    elif cmd == "get":
        send_cfg()
        ack("ok:cfg_sent")

    elif cmd == "restart":
        ack("ok:restarting")
        state["uptime"] = 0
        send_alert("RESTART", "ESP32 đã khởi động lại", "INFO")

def ack(msg):
    if client:
        client.publish(f"{P}/ack", msg, qos=1)

def send_alert(code, msg, severity="INFO"):
    if client:
        payload = json.dumps({
            "code": code,
            "msg": msg,
            "level": round(state["level"], 1),
            "severity": severity,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, ensure_ascii=False)
        client.publish(f"{P}/alert", payload, qos=1)

def send_cfg():
    if client:
        payload = json.dumps({
            "dEmpty": state["d_empty"],
            "dFull": state["d_full"],
            "inOn": state["in_on"],
            "inOff": state["in_off"],
            "outOn": state["out_on"],
            "outOff": state["out_off"],
            "limitHigh": state["limit_high"],
            "limitLow": state["limit_low"]
        })
        client.publish(f"{P}/cfg", payload, qos=1, retain=True)

def update_physics():
    """Mô phỏng mực nước và điều khiển bơm theo logic ao nuôi thực tế."""
    # 1. Nếu ở chế độ AUTO, tự động đóng cắt bơm
    if state["auto_mode"] == 1:
        if state["level"] <= state["in_on"] and not state["pump_in"]:
            state["pump_in"] = 1
            state["pump_out"] = 0
            send_alert("PUMP_IN", "Mực nước thấp, tự động BẬT bơm cấp nước (AUTO)", "INFO")
        elif state["level"] >= state["in_off"] and state["pump_in"]:
            state["pump_in"] = 0
            send_alert("PUMP_IN_OFF", "Mực nước đạt ngưỡng an toàn, tự động TẮT bơm cấp (AUTO)", "INFO")

        if state["level"] >= state["out_on"] and not state["pump_out"]:
            state["pump_out"] = 1
            state["pump_in"] = 0
            send_alert("PUMP_OUT", "Mực nước cao, tự động BẬT bơm thoát nước (AUTO)", "WARNING")
        elif state["level"] <= state["out_off"] and state["pump_out"]:
            state["pump_out"] = 0
            send_alert("PUMP_OUT_OFF", "Mực nước giảm về ngưỡng an toàn, tự động TẮT bơm thoát (AUTO)", "INFO")

    # 2. Thay đổi mực nước
    if state["pump_in"]:
        state["level"] += random.uniform(0.4, 0.8)
    elif state["pump_out"]:
        state["level"] -= random.uniform(0.4, 0.8)
    else:
        # Bốc hơi hoặc dao động sóng nhẹ
        state["level"] += random.uniform(-0.08, 0.05)

    # Giới hạn mực nước 0..100%
    state["level"] = max(0.0, min(100.0, state["level"]))

    # 3. Tính khoảng cách cảm biến siêu âm HC-SR04
    span = state["d_empty"] - state["d_full"]
    state["dist"] = round(state["d_empty"] - (state["level"] / 100.0) * span, 1)

    # 4. Cảnh báo an toàn ngưỡng giới hạn
    if state["level"] >= state["limit_high"] and state["pump_in"]:
        state["pump_in"] = 0  # Cắt khẩn cấp chống tràn
        state["fault_code"] = "LIMIT_HIGH"
        send_alert("HIGH_LEVEL", f"Mực nước đạt {state['level']:.1f}% (nguy cơ tràn ao)", "DANGER")

    if state["level"] <= state["limit_low"] and state["pump_out"]:
        state["pump_out"] = 0  # Cắt khẩn cấp chống cháy cạn
        state["fault_code"] = "LIMIT_LOW"
        send_alert("LOW_LEVEL", f"Mực nước đạt {state['level']:.1f}% (nguy cơ cạn ao)", "DANGER")

    state["uptime"] += 2
    state["rssi"] = -55 + random.randint(-3, 3)

def main():
    global client
    print("=" * 65)
    print("  BỘ GIẢ LẬP ESP32 + HC-SR04 + RELAY (BƯỚC 3: KIỂM THỬ MQTT)")
    print(f"  Broker: {MQTT_HOST}:{MQTT_PORT} | Prefix: {P}")
    print("=" * 65)

    try:
        client = mqtt_lib.Client(mqtt_lib.CallbackAPIVersion.VERSION2, client_id="esp32-sim-device")
    except (AttributeError, TypeError):
        client = mqtt_lib.Client(client_id="esp32-sim-device")

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message
    client.will_set(f"{P}/status", "offline", qos=1, retain=True)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"[LỖI] Không thể kết nối MQTT Broker tại {MQTT_HOST}:{MQTT_PORT}: {e}")
        print("  -> Vui lòng đảm bảo Mosquitto đang chạy hoặc kiểm tra MQTT_HOST trong .env")
        sys.exit(1)

    print("\n>>> Đang phát dữ liệu định kỳ mỗi 2 giây. Nhấn Ctrl+C để dừng.\n")

    while running:
        update_physics()
        payload = {
            "level": round(state["level"], 1),
            "dist": round(state["dist"], 1),
            "in": state["pump_in"],
            "out": state["pump_out"],
            "auto": state["auto_mode"],
            "err": state["sensor_err"],
            "fault": state["fault_code"],
            "rssi": state["rssi"],
            "up": state["uptime"]
        }

        client.publish(f"{P}/data", json.dumps(payload), qos=0)

        # In log dòng đẹp
        mode_str = "AUTO" if state["auto_mode"] else "MANUAL"
        in_str   = "BẬT" if state["pump_in"] else "Tắt"
        out_str  = "BẬT" if state["pump_out"] else "Tắt"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Mực nước: {payload['level']:5.1f}% | KC: {payload['dist']:5.1f}cm | Bơm IN: {in_str:3s} | Bơm OUT: {out_str:3s} | Chế độ: {mode_str}")

        time.sleep(2)

if __name__ == "__main__":
    main()
