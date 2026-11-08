# ============================================================================
#  notifications/notify_watchdog.py – Giám sát kết nối ESP32 và MQTT (Watchdog)
# ============================================================================
import os
import time
import logging
import threading
from datetime import datetime
import mqtt_client
from .notify_rules import check_device_offline
from .notifier import handle_triggered_incident, process_active_incidents, get_system_config_dict

logger = logging.getLogger(__name__)

OFFLINE_TIMEOUT_SEC = int(os.getenv("NOTIFY_ESP_OFFLINE_SECONDS", "120"))
STARTUP_GRACE_SEC = int(os.getenv("NOTIFY_STARTUP_GRACE_SECONDS", "60"))

_watchdog_thread = None
_stop_event = threading.Event()

def _watchdog_loop():
    logger.info(f"[Watchdog] Bắt đầu giám sát kết nối (Thời gian khởi động chờ: {STARTUP_GRACE_SEC}s)...")
    _stop_event.wait(STARTUP_GRACE_SEC)

    while not _stop_event.is_set():
        try:
            latest = mqtt_client.get_latest()
            cfg = get_system_config_dict()
            now = time.time()

            # 1. Kiểm tra thời điểm nhận bản tin gần nhất từ ESP32
            last_ts = latest.get("ts")
            device_id = latest.get("esp32_id", "esp32-ao-01")

            if last_ts is not None:
                diff_sec = now - float(last_ts)
                offline_rule = check_device_offline(diff_sec)
                if offline_rule:
                    handle_triggered_incident(offline_rule, latest, device_id)
            else:
                # Nếu chưa bao giờ nhận được dữ liệu sau thời gian grace
                status_text = latest.get("esp32_status", "unknown")
                if status_text != "online":
                    dummy_offline = {
                        "event_key": "ESP_OFFLINE",
                        "severity": "DANGER",
                        "title": "Chưa nhận được tín hiệu từ ESP32",
                        "message": "Hệ thống chưa nhận được bản tin telemetry nào từ thiết bị ESP32 tại ao nuôi.",
                        "recommendation": "Kiểm tra nguồn điện và kết nối mạng của ESP32.",
                        "source": "watchdog",
                    }
                    handle_triggered_incident(dummy_offline, latest, device_id)

            # 2. Xử lý phục hồi khi thiết bị kết nối lại
            process_active_incidents(latest, cfg)

        except Exception as e:
            logger.error(f"[Watchdog] Lỗi ngoại lệ trong vòng lặp watchdog: {e}")

        # Kiểm tra chu kỳ mỗi 15 giây
        _stop_event.wait(15)

    logger.info("[Watchdog] Dịch vụ Watchdog đã dừng.")

def start_watchdog():
    global _watchdog_thread
    if _watchdog_thread and _watchdog_thread.is_alive():
        return
    _stop_event.clear()
    _watchdog_thread = threading.Thread(target=_watchdog_loop, name="NotifyWatchdogThread", daemon=True)
    _watchdog_thread.start()

def stop_watchdog():
    _stop_event.set()

