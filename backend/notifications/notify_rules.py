# ============================================================================
#  notifications/notify_rules.py – Bộ quy tắc cảnh báo (Rule Engine)
#  Phát hiện sự cố dựa trên cảm biến, trạng thái máy bơm và mã lỗi ESP32.
# ============================================================================
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def evaluate_all_rules(latest_status: dict, cfg: dict, recent_history: list | None = None) -> list[dict]:
    """
    Chạy tất cả các quy tắc nghiệp vụ trên trạng thái hiện tại.
    Trả về danh sách các sự cố được kích hoạt:
    [
        {
            "event_key": "HIGH_LEVEL",
            "severity": "DANGER",
            "title": "Mực nước ao nuôi vượt ngưỡng cao",
            "message": "...",
            "recommendation": "...",
            "source": "backend_rule"
        },
        ...
    ]
    """
    results = []
    if not latest_status:
        return results

    # Rule 1: Mực nước cao / thấp khẩn cấp
    level_rule = check_water_level(latest_status, cfg)
    if level_rule:
        results.append(level_rule)
    else:
        # Rule 2: Cảnh báo sớm tiến gần giới hạn (chỉ xét khi chưa chạm mức khẩn cấp)
        near_rule = check_near_limit(latest_status, cfg, recent_history)
        if near_rule:
            results.append(near_rule)

    # Rule 3: Bơm không hiệu quả (chạy nhưng mức nước không đổi)
    if recent_history:
        pump_eff = check_pump_effectiveness(latest_status, recent_history, cfg)
        if pump_eff:
            results.append(pump_eff)

    # Rule 4: Bơm chạy quá thời gian (pump_overrun)
    overrun = check_pump_overrun(latest_status, cfg)
    if overrun:
        results.append(overrun)

    # Rule 5: Lỗi cảm biến đo khoảng cách
    sensor_fault = check_sensor_fault(latest_status)
    if sensor_fault:
        results.append(sensor_fault)

    return results

def check_water_level(status: dict, cfg: dict) -> dict | None:
    """Kiểm tra mực nước vượt ngưỡng nguy hiểm cao hoặc thấp."""
    try:
        level = float(status.get("water_level", -1))
        if level < 0:
            return None
    except (TypeError, ValueError):
        return None

    try:
        limit_high = float(cfg.get("limit_high", 95))
        limit_low = float(cfg.get("limit_low", 5))
    except (TypeError, ValueError):
        limit_high, limit_low = 95.0, 5.0

    if level >= limit_high:
        return {
            "event_key": "HIGH_LEVEL",
            "severity": "DANGER",
            "title": "Mực nước ao nuôi vượt ngưỡng nguy hiểm cao",
            "message": f"Mực nước hiện tại đạt {level:.1f}%, đã vượt quá giới hạn an toàn cao ({limit_high:.1f}%). Nguy cơ tràn bờ ao gây thất thoát cá!",
            "recommendation": "Ngắt ngay bơm cấp nước và kích hoạt bơm thoát (OUT) nếu cần thiết để hạ mức nước về vùng an toàn.",
            "source": "backend_rule",
        }

    if level <= limit_low:
        return {
            "event_key": "LOW_LEVEL",
            "severity": "DANGER",
            "title": "Mực nước ao nuôi giảm dưới ngưỡng nguy hiểm thấp",
            "message": f"Mực nước hiện tại giảm xuống {level:.1f}%, thấp hơn giới hạn an toàn tối thiểu ({limit_low:.1f}%). Ao có nguy cơ cạn kiệt đe dọa sinh trưởng của đàn cá!",
            "recommendation": "Kiểm tra rò rỉ bờ ao, cống xả đáy và lập tức bật bơm cấp nước (IN) vào ao.",
            "source": "backend_rule",
        }

    return None

def check_near_limit(status: dict, cfg: dict, recent_history: list | None = None) -> dict | None:
    """Cảnh báo sớm khi mực nước tiến gần giới hạn và xu hướng tiếp tục bất lợi."""
    try:
        level = float(status.get("water_level", -1))
        if level < 0:
            return None
        limit_high = float(cfg.get("limit_high", 95))
        limit_low = float(cfg.get("limit_low", 5))
    except (TypeError, ValueError):
        return None

    # Biên độ cảnh báo sớm: cách giới hạn 5%
    near_high_threshold = max(limit_high - 5.0, 80.0)
    near_low_threshold = min(limit_low + 5.0, 20.0)

    # Tính biến động mực nước trong dữ liệu gần nhất (nếu có)
    delta = 0.0
    if recent_history and len(recent_history) >= 2:
        try:
            first_lvl = float(recent_history[0].get("water_level", level))
            delta = level - first_lvl
        except (TypeError, ValueError):
            delta = 0.0

    pump_in = int(status.get("pump_in", 0) or 0)
    pump_out = int(status.get("pump_out", 0) or 0)

    # Tiến gần mức cao và xu hướng đang tăng hoặc bơm cấp vẫn bật
    if level >= near_high_threshold and level < limit_high:
        if delta > 0 or pump_in == 1:
            return {
                "event_key": "NEAR_HIGH_LEVEL",
                "severity": "WARNING",
                "title": "Mực nước đang tiến sát ngưỡng tràn ao",
                "message": f"Mực nước đạt {level:.1f}%, đang tiệm cận mức nguy hiểm ({limit_high:.1f}%). Xu hướng mực nước tiếp tục tăng (Bơm cấp: {'BẬT' if pump_in == 1 else 'TẮT'}).",
                "recommendation": "Theo dõi sát diễn biến mực nước hoặc chủ động tắt bơm cấp trước khi chạm ngưỡng báo động tràn.",
                "source": "backend_rule",
            }

    # Tiến gần mức thấp và xu hướng đang giảm hoặc bơm xả vẫn bật
    if level <= near_low_threshold and level > limit_low:
        if delta < 0 or pump_out == 1:
            return {
                "event_key": "NEAR_LOW_LEVEL",
                "severity": "WARNING",
                "title": "Mực nước đang tiến sát mức cạn ao",
                "message": f"Mực nước giảm còn {level:.1f}%, đang tiến gần mức nguy hiểm ({limit_low:.1f}%). Xu hướng mực nước tiếp tục giảm (Bơm thoát: {'BẬT' if pump_out == 1 else 'TẮT'}).",
                "recommendation": "Kiểm tra cống thoát nước và chuẩn bị kế hoạch cấp bổ sung nước cho ao nuôi.",
                "source": "backend_rule",
            }

    return None

def check_pump_effectiveness(status: dict, recent_history: list, cfg: dict) -> dict | None:
    """
    Kiểm tra hiệu quả bơm: Bơm bật liên tục trong >= 3 phút nhưng mực nước không thay đổi tương ứng.
    recent_history: danh sách các bản ghi sensor_data trong vòng 3 - 5 phút gần nhất, sắp xếp theo thời gian tăng dần.
    """
    if not recent_history or len(recent_history) < 4:
        return None

    pump_in = int(status.get("pump_in", 0) or 0)
    pump_out = int(status.get("pump_out", 0) or 0)

    # Kiểm tra bơm IN: nếu tất cả bản ghi gần đây đều có pump_in == 1
    if pump_in == 1:
        all_in_on = all(int(r.get("pump_in", 0) or 0) == 1 for r in recent_history)
        if all_in_on:
            try:
                start_lvl = float(recent_history[0]["water_level"])
                end_lvl = float(recent_history[-1]["water_level"])
                delta = end_lvl - start_lvl
                # Nếu bơm cấp chạy liên tục mà nước tăng dưới 0.3% hoặc giảm
                if delta < 0.3:
                    return {
                        "event_key": "NO_FLOW_IN",
                        "severity": "WARNING",
                        "title": "Bơm cấp nước hoạt động không hiệu quả",
                        "message": f"Máy bơm cấp (IN) đang bật liên tục nhưng mực nước không tăng (thay đổi {delta:+.1f}% trong thời gian bơm). Có thể do hụt nước đầu vào, kẹt van hoặc hỏng cánh bơm.",
                        "recommendation": "Kiểm tra nguồn cấp nước, đường ống hút và hoạt động thực tế của máy bơm cấp.",
                        "source": "backend_rule",
                    }
            except (KeyError, TypeError, ValueError):
                pass

    # Kiểm tra bơm OUT: nếu tất cả bản ghi gần đây đều có pump_out == 1
    if pump_out == 1:
        all_out_on = all(int(r.get("pump_out", 0) or 0) == 1 for r in recent_history)
        if all_out_on:
            try:
                start_lvl = float(recent_history[0]["water_level"])
                end_lvl = float(recent_history[-1]["water_level"])
                delta = end_lvl - start_lvl
                # Nếu bơm thoát chạy liên tục mà nước giảm dưới 0.3% (delta > -0.3)
                if delta > -0.3:
                    return {
                        "event_key": "NO_FLOW_OUT",
                        "severity": "WARNING",
                        "title": "Bơm thoát nước hoạt động không hiệu quả",
                        "message": f"Máy bơm thoát (OUT) đang bật liên tục nhưng mực nước không hạ (thay đổi {delta:+.1f}% trong thời gian bơm). Có thể do tắc ống xả, kẹt rác hoặc đường ống bị nghẽn.",
                        "recommendation": "Kiểm tra cửa cống xả, lưới chắn rác và đường ống dẫn của bơm thoát nước.",
                        "source": "backend_rule",
                    }
            except (KeyError, TypeError, ValueError):
                pass

    return None

def check_pump_overrun(status: dict, cfg: dict) -> dict | None:
    """Kiểm tra lỗi bơm chạy quá thời gian cho phép."""
    fault_code = str(status.get("fault_code", "none")).lower()
    if fault_code in ("pump_overrun", "overrun"):
        max_run = cfg.get("max_run_min", "20")
        return {
            "event_key": "PUMP_OVERRUN",
            "severity": "WARNING",
            "title": "Máy bơm chạy quá thời gian bảo vệ",
            "message": f"Hệ thống ghi nhận lỗi máy bơm chạy liên tục vượt quá thời gian tối đa ({max_run} phút). ESP32 đã ngắt bơm tự động để chống cháy động cơ.",
            "recommendation": "Kiểm tra lưu lượng bơm, rò rỉ nước hoặc tăng thời gian giới hạn nếu ao có diện tích lớn.",
            "source": "esp32",
        }
    return None

def check_sensor_fault(status: dict) -> dict | None:
    """Kiểm tra lỗi cảm biến siêu âm HC-SR04."""
    sensor_err = int(status.get("sensor_err", 0) or 0)
    fault_code = str(status.get("fault_code", "none")).lower()
    if sensor_err == 1 or fault_code in ("sensor_err", "sensor_error"):
        return {
            "event_key": "SENSOR_ERROR",
            "severity": "WARNING",
            "title": "Lỗi cảm biến đo mực nước HC-SR04",
            "message": "Cảm biến khoảng cách không phản hồi hoặc trả về tín hiệu ngoài dải đo cho phép. Việc giám sát tự động bị tạm dừng.",
            "recommendation": "Kiểm tra dây nối Echo/Trig của cảm biến HC-SR04, bề mặt phát sóng và nguồn cấp 5V.",
            "source": "esp32",
        }
    return None

def check_device_offline(last_seen_seconds: float) -> dict | None:
    """Kiểm tra thiết bị ESP32 mất kết nối quá thời gian cho phép (> 120s)."""
    if last_seen_seconds > 120:
        return {
            "event_key": "ESP_OFFLINE",
            "severity": "DANGER",
            "title": "Mất kết nối với thiết bị ESP32",
            "message": f"Đã quá {int(last_seen_seconds)} giây kể từ lần cuối nhận được tín hiệu từ ESP32 tại ao nuôi. Toàn bộ giám sát từ xa đang bị gián đoạn!",
            "recommendation": "Kiểm tra nguồn điện cung cấp cho ESP32 và chất lượng đường truyền mạng WiFi.",
            "source": "watchdog",
        }
    return None

def evaluate_recovery(incident: dict, current_status: dict, cfg: dict) -> bool:
    """
    Xác định xem một sự cố đang ACTIVE có đủ điều kiện chuyển sang RECOVERED hay chưa.
    Áp dụng hysteresis để tránh rung lắc (chatter).
    """
    event_key = incident.get("event_key")
    if not current_status:
        return False

    try:
        level = float(current_status.get("water_level", -1))
        limit_high = float(cfg.get("limit_high", 95))
        limit_low = float(cfg.get("limit_low", 5))
    except (TypeError, ValueError):
        return False

    # 1. Mực nước cao: phục hồi khi hạ xuống dưới limit_high - 2%
    if event_key == "HIGH_LEVEL":
        return level > 0 and level <= (limit_high - 2.0)

    # 2. Mực nước thấp: phục hồi khi tăng lên trên limit_low + 2%
    if event_key == "LOW_LEVEL":
        return level >= (limit_low + 2.0)

    # 3. Tiến gần mức cao: phục hồi khi lùi sâu vào vùng an toàn
    if event_key == "NEAR_HIGH_LEVEL":
        return level > 0 and level <= (limit_high - 6.0)

    # 4. Tiến gần mức thấp: phục hồi khi nâng lên vùng an toàn
    if event_key == "NEAR_LOW_LEVEL":
        return level >= (limit_low + 6.0)

    # 5. Bơm không hiệu quả: phục hồi khi bơm đã tắt hoặc trạng thái bình thường
    if event_key == "NO_FLOW_IN":
        pump_in = int(current_status.get("pump_in", 0) or 0)
        return pump_in == 0

    if event_key == "NO_FLOW_OUT":
        pump_out = int(current_status.get("pump_out", 0) or 0)
        return pump_out == 0

    # 6. Bơm quá giờ: phục hồi khi mã lỗi được xóa
    if event_key == "PUMP_OVERRUN":
        fault = str(current_status.get("fault_code", "")).lower()
        return fault not in ("pump_overrun", "overrun")

    # 7. Cảm biến lỗi: phục hồi khi cảm biến đo bình thường trở lại
    if event_key == "SENSOR_ERROR":
        sensor_err = int(current_status.get("sensor_err", 0) or 0)
        fault = str(current_status.get("fault_code", "")).lower()
        return sensor_err == 0 and fault not in ("sensor_err", "sensor_error")

    # 8. Mất kết nối: phục hồi khi ESP32 trực tuyến trở lại
    if event_key == "ESP_OFFLINE":
        status_text = current_status.get("esp32_status", "")
        return status_text == "online"

    return False

