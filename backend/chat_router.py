# ============================================================================
#  chat_router.py – Bộ định tuyến ý định tiếng Việt thông minh (Fast Path + Context)
#  Hỗ trợ hỏi đáp tự nhiên tiếng Việt và xử lý câu hỏi tiếp nối theo ngữ cảnh
# ============================================================================
import re
import unicodedata
from datetime import datetime

import chat_tools

# ── Quản lý ngữ cảnh hội thoại gần nhất (Session Context) ────────────────────
_last_context = {
    "intent": None,
    "minutes": 30,
    "timestamp": None,
}


def update_context(intent: str, **kwargs):
    """Cập nhật ngữ cảnh câu hỏi vừa xử lý."""
    global _last_context
    _last_context["intent"] = intent
    _last_context["timestamp"] = datetime.now()
    for k, v in kwargs.items():
        _last_context[k] = v


def get_context() -> dict:
    """Lấy ngữ cảnh hiện tại, tự động hết hạn sau 5 phút."""
    global _last_context
    if _last_context.get("timestamp"):
        diff = (datetime.now() - _last_context["timestamp"]).total_seconds()
        if diff > 300:  # Quá 5 phút thì đặt lại
            _last_context = {"intent": None, "minutes": 30, "timestamp": None}
    return _last_context


def _strip_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để so khớp linh hoạt."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text)


def normalize_text(text: str) -> str:
    """Chuẩn hóa văn bản đầu vào: chữ thường, bỏ ký tự đặc biệt, chuẩn hóa khoảng trắng."""
    if not text:
        return ""
    text = text.lower().strip()
    # Thay thế một số từ viết tắt thông dụng trong tiếng Việt
    text = re.sub(r"\bko\b|\bk\b|\bhok\b", "không", text)
    text = re.sub(r"\bdc\b|\bđc\b", "được", text)
    text = re.sub(r"\bvs\b", "với", text)
    text = re.sub(r"\btg\b", "thời gian", text)
    text = re.sub(r"\bmc\b", "máy", text)
    text = re.sub(r"\bntn\b", "như thế nào", text)
    text = re.sub(r"\bstt\b", "trạng thái", text)
    # Xóa dấu chấm câu dư thừa ở cuối
    text = re.sub(r"[?!.,;]+$", "", text).strip()
    return text


def extract_minutes(u: str) -> int | None:
    """Trích xuất khoảng thời gian tính bằng phút từ câu tiếng Việt."""
    if "nay gio" in u or "tu nay den gio" in u:
        return 30
    if "nua tieng" in u or "nua gio" in u:
        return 30
    if "tieng ruoi" in u or "gio ruoi" in u:
        return 90

    # Dạng số + giờ/tiếng/h (ví dụ: 1 giờ, 2 tiếng, 1h)
    hr_match = re.search(r"(\d+)\s*(gio|tieng|h)\b", u)
    if hr_match:
        try:
            return int(hr_match.group(1)) * 60
        except ValueError:
            pass

    # Dạng chữ + giờ/tiếng (ví dụ: một giờ, hai tiếng)
    word_hr_match = re.search(r"\b(mot|hai|ba|bon|nam)\s*(gio|tieng)\b", u)
    if word_hr_match:
        words = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5}
        return words.get(word_hr_match.group(1), 1) * 60

    # Dạng số + phút/p/m (ví dụ: 15 phút, 30p, 45m)
    min_match = re.search(r"(\d+)\s*(phut|p|m)\b", u)
    if min_match:
        try:
            return int(min_match.group(1))
        except ValueError:
            pass

    return None


def format_vn_number(val: float | int | None, decimals: int = 1) -> str:
    """Định dạng số theo chuẩn Việt Nam (dấu phẩy thập phân: 45,5)."""
    if val is None:
        return "--"
    formatted = f"{val:.{decimals}f}".replace(".", ",")
    return formatted


def format_timestamp(iso_str: str | None) -> str:
    """Định dạng ISO timestamp thành 'HH:MM:SS - DD/MM/YYYY'."""
    if not iso_str:
        return datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%H:%M:%S - %d/%m/%Y")
    except Exception:
        return str(iso_str)


def format_time_only(iso_str: str | None) -> str:
    """Lấy phần HH:MM:SS từ ISO timestamp."""
    if not iso_str:
        return datetime.now().strftime("%H:%M:%S")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%H:%M:%S")
    except Exception:
        return str(iso_str)


# ============================================================================
#  Các hàm xử lý từng ý định (Intent Handlers)
# ============================================================================

def handle_greeting() -> dict:
    """Chào hỏi thân thiện với người dùng."""
    update_context("greeting")
    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    return {
        "handled": True,
        "intent": "greeting",
        "type": "text",
        "status_icon": "👋",
        "title": "Chào bạn! Tôi là Trợ lý AI ao nuôi.",
        "description": (
            "Tôi có thể giúp bạn kiểm tra tình hình mực nước ao nuôi, theo dõi hai máy bơm, "
            "phân tích biến động và hỗ trợ điều khiển thiết bị an toàn. Bạn cần tôi hỗ trợ gì?"
        ),
        "metrics": [
            {"icon": "💧", "label": "Mực nước ao", "type": "info"},
            {"icon": "🚰", "label": "Bơm cấp & xả", "type": "info"},
            {"icon": "📈", "label": "Biến động 30p", "type": "info"},
            {"icon": "📅", "label": "Tóm tắt hôm nay", "type": "info"},
        ],
        "data_time": f"Sẵn sàng lúc {now_str}",
    }


def handle_thanks() -> dict:
    """Phản hồi lời cảm ơn từ người dùng."""
    update_context("thanks")
    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    return {
        "handled": True,
        "intent": "thanks",
        "type": "text",
        "status_icon": "😊",
        "title": "Rất vui được hỗ trợ bạn!",
        "description": "Nếu cần kiểm tra thông tin ao nuôi hoặc điều khiển thiết bị, bạn cứ nhắn tôi bất cứ lúc nào nhé! Chúc đàn cá luôn khỏe mạnh! 🐟",
        "metrics": [],
        "data_time": f"Thời gian: {now_str}",
    }


def handle_status() -> dict:
    """Xử lý ý định: Kiểm tra mực nước và trạng thái tổng quan ao."""
    update_context("status")
    data = chat_tools.get_current_status()

    level = data.get("water_level")
    dist = data.get("distance_cm")
    pump_in = data.get("pump_in", False)
    pump_out = data.get("pump_out", False)
    auto_mode = data.get("auto_mode", True)
    sensor_err = data.get("sensor_err", False)
    level_state = data.get("level_state", "bình thường")
    data_time = data.get("data_time")
    is_stale = data.get("is_stale", False)

    time_str = format_timestamp(data_time)

    if level is None:
        return {
            "handled": True,
            "intent": "status",
            "type": "text",
            "title": "⚠️ Chưa có dữ liệu cảm biến",
            "description": "Hệ thống chưa nhận được dữ liệu từ cảm biến mực nước hoặc thiết bị đang ngoại tuyến.",
            "metrics": [
                {"icon": "💧", "label": "-- %", "type": "water"},
                {"icon": "📏", "label": "-- cm", "type": "distance"},
                {"icon": "⚪", "label": "ESP32: Offline", "type": "status"},
            ],
            "data_time": f"Thời gian: {time_str}",
        }

    level_vn = format_vn_number(level, 1)
    dist_vn = format_vn_number(dist, 1)

    if level <= 10:
        title = f"⚠️ Ao sắp cạn nước, mực nước hiện tại là {level_vn} % (cách cảm biến {dist_vn} cm)."
    elif level >= 90:
        title = f"⚠️ Cảnh báo nước đầy, mực nước hiện tại là {level_vn} % (cách cảm biến {dist_vn} cm)."
    else:
        title = f"Ao còn nước, mực nước hiện tại là {level_vn} % (cách cảm biến {dist_vn} cm)."

    if pump_out and not pump_in:
        pump_desc = "Bơm thoát (OUT) đang bật, bơm cấp tắt"
    elif pump_in and not pump_out:
        pump_desc = "Bơm cấp (IN) đang bật, bơm thoát tắt"
    elif pump_in and pump_out:
        pump_desc = "Cả hai bơm đều đang BẬT"
    else:
        pump_desc = "Cả hai bơm đều đang tắt"

    mode_desc = "chế độ AUTO" if auto_mode else "chế độ MANUAL"
    description = f"Mức nước đang ở ngưỡng {level_state}. {pump_desc}, {mode_desc}."

    if sensor_err:
        description += " ⚠️ Lưu ý: Cảm biến đang báo lỗi!"
    if is_stale:
        description += " (Dữ liệu chưa được làm mới)"

    # Cảnh báo lỗi hệ thống nếu MQTT broker mất kết nối hoặc ESP32 offline
    mqtt_conn = data.get("mqtt_connected", True)
    esp_stat = data.get("esp32_status", "unknown")
    sys_faults = []
    if not mqtt_conn:
        sys_faults.append("MQTT Broker đang mất kết nối")
    if esp_stat != "online":
        sys_faults.append(f"ESP32 đang ngoại tuyến ({esp_stat})")

    if sys_faults:
        description += f"\n\n⚠️ [Lỗi hệ thống] {', '.join(sys_faults)}. Dữ liệu trên được lấy từ bản ghi lưu trữ cuối cùng."

    metrics = [
        {"icon": "💧", "label": f"{level_vn} %", "type": "water"},
        {"icon": "📏", "label": f"{dist_vn} cm", "type": "distance"},
        {"icon": "🔴" if pump_in else "🟢", "label": f"Bơm IN: {'Bật' if pump_in else 'Tắt'}", "type": "pump"},
        {"icon": "🔴" if pump_out else "🟢", "label": f"Bơm OUT: {'Bật' if pump_out else 'Tắt'}", "type": "pump"},
        {"icon": "⚙️", "label": "AUTO" if auto_mode else "MANUAL", "type": "mode"},
    ]

    return {
        "handled": True,
        "intent": "status",
        "type": "status",
        "status_icon": "✅" if not sensor_err and level > 15 else "⚠️",
        "title": title,
        "description": description,
        "metrics": metrics,
        "data_time": f"Dữ liệu lúc {time_str}",
    }


def handle_device_status() -> dict:
    """Xử lý ý định: Trạng thái chi tiết của hai máy bơm và thiết bị ESP32."""
    update_context("device_status")
    data = chat_tools.get_current_status()

    pump_in = data.get("pump_in", False)
    pump_out = data.get("pump_out", False)
    auto_mode = data.get("auto_mode", True)
    esp_status = data.get("esp32_status", "unknown")
    fault_code = data.get("fault_code", "none")
    rssi = data.get("rssi", 0)
    data_time = data.get("data_time")
    time_str = format_timestamp(data_time)

    title = "Trạng thái bơm cấp, bơm xả và thiết bị điều khiển:"
    desc_parts = []

    if pump_in:
        desc_parts.append("Bơm cấp (IN): ĐANG CHẠY 🟢")
    else:
        desc_parts.append("Bơm cấp (IN): Đang tắt ⚪")

    if pump_out:
        desc_parts.append("Bơm thoát (OUT): ĐANG CHẠY 🟢")
    else:
        desc_parts.append("Bơm thoát (OUT): Đang tắt ⚪")

    mode_str = "Tự động (AUTO)" if auto_mode else "Thủ công (MANUAL)"
    desc_parts.append(f"Chế độ vận hành: {mode_str}")

    esp_str = "Online (kết nối tốt)" if esp_status == "online" else f"Ngoại tuyến ({esp_status})"
    desc_parts.append(f"ESP32: {esp_str} (RSSI: {rssi} dBm)")

    if fault_code != "none":
        desc_parts.append(f"Mã lỗi hiện tại: {fault_code}")

    description = ". ".join(desc_parts) + "."

    metrics = [
        {"icon": "🔴" if pump_in else "🟢", "label": f"Bơm IN: {'Bật' if pump_in else 'Tắt'}", "type": "pump"},
        {"icon": "🔴" if pump_out else "🟢", "label": f"Bơm OUT: {'Bật' if pump_out else 'Tắt'}", "type": "pump"},
        {"icon": "⚙️", "label": "AUTO" if auto_mode else "MANUAL", "type": "mode"},
        {"icon": "📡", "label": f"ESP32: {esp_status.upper()}", "type": "device"},
        {"icon": "📶", "label": f"{rssi} dBm", "type": "wifi"},
    ]

    return {
        "handled": True,
        "intent": "device_status",
        "type": "device_status",
        "status_icon": "🚰",
        "title": title,
        "description": description,
        "metrics": metrics,
        "data_time": f"Dữ liệu lúc {time_str}",
    }


def handle_change(minutes: int = 30) -> dict:
    """Xử lý ý định: Biến động mực nước trong N phút."""
    update_context("change", minutes=minutes)
    data = chat_tools.get_level_change(minutes=minutes)

    delta_pct = data.get("delta_pct", 0.0)
    delta_cm = data.get("delta_cm", 0.0)
    trend = data.get("trend", "ổn định")
    min_lvl = data.get("min_level")
    max_lvl = data.get("max_level")
    first_at = data.get("first_sample_at")
    last_at = data.get("last_sample_at")
    coverage_minutes = data.get("coverage_minutes", minutes)

    first_time_str = format_time_only(first_at)
    last_time_str = format_time_only(last_at)

    delta_sign = "+" if delta_pct > 0 else ""
    delta_pct_vn = f"{delta_sign}{format_vn_number(delta_pct, 1)}"
    delta_cm_sign = "+" if delta_cm > 0 else ""
    delta_cm_vn = f"{delta_cm_sign}{format_vn_number(delta_cm, 1)}"

    abs_pct_vn = format_vn_number(abs(delta_pct), 1)
    abs_cm_vn = format_vn_number(abs(delta_cm), 1)

    min_lvl_vn = format_vn_number(min_lvl, 1)
    max_lvl_vn = format_vn_number(max_lvl, 1)

    # Định dạng mô tả thời gian tự nhiên: "1 giờ", "2 giờ", "30 phút"
    if minutes == 60:
        time_desc = "1 giờ"
    elif minutes % 60 == 0:
        time_desc = f"{minutes // 60} giờ"
    else:
        time_desc = f"{minutes} phút"

    if trend == "tăng":
        action_word = "tăng"
        trend_label = "Tăng"
        trend_icon = "📈"
        arrow = "↑"
        modifier = "tăng nhẹ" if abs(delta_pct) < 5 else "tăng nhanh"
    elif trend == "giảm":
        action_word = "giảm"
        trend_label = "Giảm"
        trend_icon = "📉"
        arrow = "↓"
        modifier = "giảm nhẹ" if abs(delta_pct) < 5 else "giảm nhanh"
    else:
        action_word = "thay đổi không đáng kể"
        trend_label = "Ổn định"
        trend_icon = "➡️"
        arrow = "→"
        modifier = "mực nước duy trì ổn định"

    if trend in ("tăng", "giảm"):
        title = f"Trong {time_desc} qua, mực nước {action_word} {abs_pct_vn} điểm phần trăm."
        description = f"Tương đương {action_word} khoảng {abs_cm_vn} cm. Mức nước {modifier}, xu hướng đang {trend}."
    else:
        title = f"Trong {time_desc} qua, mực nước duy trì ổn định (dao động {abs_pct_vn}%)."
        description = f"Mức nước biến động khoảng {abs_cm_vn} cm. Xu hướng hiện tại ổn định, không có thay đổi bất thường."

    metrics = [
        {"icon": arrow, "label": f"{delta_pct_vn} %", "type": "change"},
        {"icon": trend_icon, "label": f"{delta_cm_vn} cm", "type": "distance"},
        {"icon": trend_icon, "label": f"Xu hướng: {trend_label}", "type": "trend"},
        {"icon": "", "label": f"Min: {min_lvl_vn} %", "type": "min"},
        {"icon": "", "label": f"Max: {max_lvl_vn} %", "type": "max"},
    ]

    cov_desc = f"{int(coverage_minutes)} phút" if coverage_minutes < 60 else (f"{coverage_minutes / 60:.1f} giờ".replace(".0", ""))

    return {
        "handled": True,
        "intent": "change",
        "type": "change",
        "status_icon": trend_icon,
        "title": title,
        "description": description,
        "metrics": metrics,
        "data_time": f"Khoảng thời gian: {first_time_str} – {last_time_str} ({cov_desc})",
    }


def handle_summary(since_midnight: bool = True) -> dict:
    """Xử lý ý định: Tóm tắt tình trạng hoạt động ao hôm nay hoặc 24h qua."""
    update_context("summary", since_midnight=since_midnight)
    data = chat_tools.get_day_summary(hours=24, since_midnight=since_midnight)

    period_desc = "hôm nay" if since_midnight else "24 giờ qua"
    min_lvl = data.get("min_level")
    max_lvl = data.get("max_level")
    avg_lvl = data.get("avg_level")
    pin_act = data.get("pump_in_activations", 0)
    pout_act = data.get("pump_out_activations", 0)
    pin_min = data.get("pump_in_total_minutes", 0)
    pout_min = data.get("pump_out_total_minutes", 0)
    alert_cnt = data.get("alert_count", 0)
    unresolved_cnt = data.get("unresolved_alert_count", 0)
    sample_cnt = data.get("sample_count", 0)

    min_vn = format_vn_number(min_lvl, 1)
    max_vn = format_vn_number(max_lvl, 1)
    avg_vn = format_vn_number(avg_lvl, 1)

    title = f"Tóm tắt tình trạng hoạt động ao {period_desc}:"
    if sample_cnt == 0:
        description = f"Chưa có dữ liệu cảm biến được ghi nhận trong {period_desc}."
    else:
        description = (
            f"Mực nước dao động từ {min_vn}% đến {max_vn}%, trung bình {avg_vn}%. "
            f"Bơm cấp đã bật {pin_act} lần (tổng ~{format_vn_number(pin_min, 1)} phút), "
            f"bơm thoát bật {pout_act} lần (tổng ~{format_vn_number(pout_min, 1)} phút). "
            f"Ghi nhận {alert_cnt} cảnh báo ({unresolved_cnt} chưa xử lý)."
        )

    metrics = [
        {"icon": "📉", "label": f"Min: {min_vn} %", "type": "min"},
        {"icon": "📈", "label": f"Max: {max_vn} %", "type": "max"},
        {"icon": "💧", "label": f"TB: {avg_vn} %", "type": "avg"},
        {"icon": "🚰", "label": f"Bơm IN: {pin_act} lần", "type": "pump"},
        {"icon": "🚰", "label": f"Bơm OUT: {pout_act} lần", "type": "pump"},
        {"icon": "⚠️", "label": f"Cảnh báo: {alert_cnt}", "type": "alert"},
    ]

    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")

    return {
        "handled": True,
        "intent": "summary",
        "type": "summary",
        "status_icon": "📅",
        "title": title,
        "description": description,
        "metrics": metrics,
        "data_time": f"Tổng hợp lúc {now_str}",
    }


def handle_alerts() -> dict:
    """Xử lý ý định: Tra cứu danh sách cảnh báo."""
    update_context("alerts")
    data = chat_tools.get_alerts(hours=24, limit=5)
    total = data.get("total_count", 0)
    unresolved = data.get("unresolved_count", 0)
    alerts = data.get("alerts", [])

    if total == 0:
        title = "Không có cảnh báo nào trong 24 giờ qua."
        description = "Hệ thống đang hoạt động an toàn, không ghi nhận sự cố hay vượt ngưỡng."
        status_icon = "✅"
    else:
        title = f"Hiện có {unresolved} cảnh báo chưa xử lý (tổng {total} trong 24h qua):"
        alert_lines = []
        for a in alerts[:3]:
            status_text = "Chưa xử lý" if a.get("status") == "UNRESOLVED" else "Đã xử lý"
            alert_lines.append(f"• [{status_text}] {a.get('message', a.get('alert_code'))}")
        description = "\n".join(alert_lines)
        status_icon = "⚠️" if unresolved > 0 else "ℹ️"

    metrics = [
        {"icon": "⚠️", "label": f"Chưa xử lý: {unresolved}", "type": "alert_unresolved"},
        {"icon": "📋", "label": f"Tổng cảnh báo: {total}", "type": "alert_total"},
    ]

    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")

    return {
        "handled": True,
        "intent": "alerts",
        "type": "alerts",
        "status_icon": status_icon,
        "title": title,
        "description": description,
        "metrics": metrics,
        "data_time": f"Cập nhật lúc {now_str}",
    }


def handle_config() -> dict:
    """Xử lý ý định: Tra cứu cấu hình và ngưỡng hoạt động."""
    update_context("config")
    data = chat_tools.get_config()
    server_cfg = data.get("server_config", {})
    synced = data.get("config_synced", False)

    in_on = server_cfg.get("in_on_pct", 30)
    in_off = server_cfg.get("in_off_pct", 50)
    out_on = server_cfg.get("out_on_pct", 90)
    out_off = server_cfg.get("out_off_pct", 80)
    lim_high = server_cfg.get("limit_high", 95)
    lim_low = server_cfg.get("limit_low", 5)

    title = "Cấu hình ngưỡng hoạt động của ao nuôi:"
    sync_str = "Đã đồng bộ với ESP32" if synced else "Chưa đồng bộ hoàn toàn với ESP32"
    description = (
        f"• Ngưỡng bơm cấp (IN): Bật khi nước ≤ {in_on}%, tắt khi đạt {in_off}%.\n"
        f"• Ngưỡng bơm thoát (OUT): Bật khi nước ≥ {out_on}%, tắt khi về {out_off}%.\n"
        f"• Giới hạn an toàn: Báo động tràn khi ≥ {lim_high}%, báo động cạn khi ≤ {lim_low}%.\n"
        f"• Trạng thái đồng bộ: {sync_str}."
    )

    metrics = [
        {"icon": "🚰", "label": f"Bơm IN bật: {in_on}%", "type": "config"},
        {"icon": "🛑", "label": f"Bơm IN tắt: {in_off}%", "type": "config"},
        {"icon": "🌊", "label": f"Bơm OUT bật: {out_on}%", "type": "config"},
        {"icon": "🛑", "label": f"Bơm OUT tắt: {out_off}%", "type": "config"},
        {"icon": "🔄", "label": "Đồng bộ: " + ("OK" if synced else "Lệch"), "type": "sync"},
    ]

    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")

    return {
        "handled": True,
        "intent": "config",
        "type": "config",
        "status_icon": "⚙️",
        "title": title,
        "description": description,
        "metrics": metrics,
        "data_time": f"Cấu hình lúc {now_str}",
    }


def handle_control(command: str, payload: str) -> dict:
    """Xử lý đề xuất điều khiển: Tạo yêu cầu xác nhận kèm cảnh báo."""
    update_context("control", command=command, payload=payload)
    result = chat_tools.propose_control(command, payload)

    if not result.get("success"):
        return {
            "handled": True,
            "intent": "control_error",
            "type": "text",
            "title": "❌ Không thể tạo lệnh điều khiển",
            "description": result.get("message", "Lỗi không xác định"),
            "metrics": [],
            "data_time": datetime.now().strftime("%H:%M:%S - %d/%m/%Y"),
        }

    cmd_names = {"pump_in": "Bơm cấp (IN)", "pump_out": "Bơm thoát (OUT)", "mode": "Chế độ"}
    payload_names = {"ON": "BẬT", "OFF": "TẮT", "AUTO": "TỰ ĐỘNG", "MANUAL": "THỦ CÔNG"}

    cmd_label = cmd_names.get(command, command)
    payload_label = payload_names.get(payload, payload)

    title = f"Xác nhận lệnh: {payload_label} {cmd_label}"
    description = result.get("confirmation_message", "")
    warnings = result.get("warnings", [])

    return {
        "handled": True,
        "intent": "control_propose",
        "type": "confirmation",
        "status_icon": "⚠️",
        "title": title,
        "description": description,
        "action_id": result.get("action_id"),
        "command": command,
        "payload": payload,
        "warnings": warnings,
        "expires_at": result.get("expires_at"),
        "metrics": [
            {"icon": "⚙️", "label": f"Lệnh: {command}", "type": "cmd"},
            {"icon": "🎯", "label": f"Giá trị: {payload}", "type": "payload"},
            {"icon": "⏱️", "label": "Hiệu lực: 60s", "type": "expiry"},
        ],
        "data_time": datetime.now().strftime("%H:%M:%S - %d/%m/%Y"),
    }


def handle_confirm_action(action_id: str | None = None) -> dict:
    """Xác nhận lệnh đang chờ."""
    update_context("confirm")
    if not action_id:
        action_id = chat_tools.get_latest_pending_action_id()

    if not action_id:
        return {
            "handled": True,
            "intent": "control_confirm",
            "type": "text",
            "title": "ℹ️ Không có lệnh nào đang chờ xác nhận",
            "description": "Không tìm thấy lệnh điều khiển nào đang chờ hoặc lệnh đã hết hạn (quá 60 giây).",
            "metrics": [],
            "data_time": datetime.now().strftime("%H:%M:%S - %d/%m/%Y"),
        }

    res = chat_tools.confirm_control(action_id)
    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")

    if res.get("success"):
        return {
            "handled": True,
            "intent": "control_confirm",
            "type": "text",
            "status_icon": "✅",
            "title": "✅ Lệnh đã được thực thi",
            "description": res.get("message", "Đã gửi lệnh xuống ESP32 thành công."),
            "metrics": [{"icon": "📡", "label": f"Log ID: #{res.get('log_id', 0)}", "type": "log"}],
            "data_time": f"Thực hiện lúc {now_str}",
        }
    else:
        return {
            "handled": True,
            "intent": "control_confirm",
            "type": "text",
            "status_icon": "❌",
            "title": "❌ Không thể thực thi lệnh",
            "description": res.get("message", "Lỗi xác nhận lệnh."),
            "metrics": [],
            "data_time": f"Thời gian: {now_str}",
        }


def handle_cancel_action(action_id: str | None = None) -> dict:
    """Hủy lệnh đang chờ."""
    update_context("cancel")
    if not action_id:
        action_id = chat_tools.get_latest_pending_action_id()

    if not action_id:
        return {
            "handled": True,
            "intent": "control_cancel",
            "type": "text",
            "title": "ℹ️ Không có lệnh nào cần hủy",
            "description": "Không tìm thấy lệnh điều khiển nào đang chờ xác nhận.",
            "metrics": [],
            "data_time": datetime.now().strftime("%H:%M:%S - %d/%m/%Y"),
        }

    res = chat_tools.cancel_control(action_id)
    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")

    return {
        "handled": True,
        "intent": "control_cancel",
        "type": "text",
        "status_icon": "🚫",
        "title": "🚫 Đã hủy lệnh điều khiển",
        "description": res.get("message", "Lệnh đã được hủy bỏ an toàn."),
        "metrics": [],
        "data_time": f"Hủy lúc {now_str}",
    }


def handle_safety_pump_conflict() -> dict:
    """Xử lý từ chối bật đồng thời cả hai bơm cấp và bơm thoát."""
    update_context("safety")
    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    return {
        "handled": True,
        "intent": "safety_pump_conflict",
        "type": "text",
        "status_icon": "🛡️",
        "title": "⚠️ Từ chối lệnh: Không thể bật đồng thời cả hai bơm!",
        "description": (
            "Hệ thống ao nuôi không cho phép bật cả bơm cấp (IN) và bơm thoát (OUT) cùng lúc.\n"
            "Thao tác này gây xung đột thủy lực nghiêm trọng, làm giảm tuổi thọ máy bơm và lãng phí điện năng.\n\n"
            "👉 Quy tắc an toàn: Bạn chỉ có thể chọn Bật bơm cấp HOẶC Bật bơm thoát (và phải qua bước xác nhận bắt buộc)."
        ),
        "metrics": [
            {"icon": "🛑", "label": "Bơm IN & OUT đồng thời: BỊ CHẶN", "type": "blocked"},
            {"icon": "🛡️", "label": "Bảo vệ an toàn: KÍCH HOẠT", "type": "safety"},
            {"icon": "⚡", "label": "Xung đột thủy lực: ĐÃ NGĂN CHẶN", "type": "prevented"},
        ],
        "data_time": f"Kiểm tra lúc {now_str}",
    }


def handle_safety_bypass_attempt() -> dict:
    """Xử lý ngăn chặn Prompt Injection và vượt rào an toàn."""
    update_context("safety")
    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    return {
        "handled": True,
        "intent": "safety_bypass",
        "type": "text",
        "status_icon": "🛡️",
        "title": "🛡️ Từ chối yêu cầu vượt rào an toàn",
        "description": (
            "Cảnh báo: Hệ thống TUYỆT ĐỐI KHÔNG cho phép bỏ qua quy trình an toàn, quy tắc bảo vệ thiết bị hoặc cưỡng chế gửi lệnh trực tiếp xuống ESP32.\n\n"
            "Mọi thao tác điều khiển máy bơm (Bật/Tắt bơm cấp, bơm thoát hay đổi chế độ) bắt buộc phải:\n"
            "1. Kiểm tra an toàn mực nước và chống xung đột thiết bị.\n"
            "2. Được người vận hành ấn nút 'Xác nhận' rõ ràng trước khi gửi lệnh qua MQTT."
        ),
        "metrics": [
            {"icon": "🛡️", "label": "Chống can thiệp: BẬT", "type": "safety"},
            {"icon": "🔒", "label": "Xác nhận 2 bước: BẮT BUỘC", "type": "security"},
            {"icon": "🚫", "label": "Lệnh cưỡng chế: BỊ TỪ CHỐI", "type": "blocked"},
        ],
        "data_time": f"Kiểm tra an toàn lúc {now_str}",
    }


def handle_out_of_scope(param_name: str = "thông số này") -> dict:
    """Xử lý câu hỏi về thông số ngoài phạm vi cảm biến phần cứng."""
    update_context("out_of_scope")
    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    return {
        "handled": True,
        "intent": "out_of_scope",
        "type": "text",
        "status_icon": "ℹ️",
        "title": f"Chưa có cảm biến đo {param_name}",
        "description": (
            f"Hệ thống IoT ao nuôi hiện tại CHƯA ĐƯỢC TRANG BỊ cảm biến để đo {param_name}.\n\n"
            f"📊 Phần cứng ao nuôi hiện chỉ có các cảm biến và thiết bị sau:\n"
            f"• Cảm biến siêu âm HC-SR04: Đo mực nước (%) và khoảng cách đến mặt nước (cm)\n"
            f"• 2 Rơ-le điều khiển máy bơm: Bơm cấp nước (IN) và Bơm thoát nước (OUT)\n"
            f"• Vi điều khiển ESP32: Giám sát chế độ AUTO/MANUAL và kết nối mạng MQTT\n\n"
            f"💡 Bạn có thể hỏi về các thông số đang được giám sát thực tế như:\n"
            f"• 'Mực nước ao hiện tại là bao nhiêu?'\n"
            f"• 'Bơm cấp và bơm xả đang bật hay tắt?'\n"
            f"• 'Trong 30 phút qua nước tăng bao nhiêu?'\n"
            f"• 'Bật bơm cấp nước vào ao'"
        ),
        "metrics": [
            {"icon": "💧", "label": "Mực nước (HC-SR04): ĐÃ CÓ", "type": "supported"},
            {"icon": "🚰", "label": "Điều khiển 2 Bơm: ĐÃ CÓ", "type": "supported"},
            {"icon": "🚫", "label": f"{param_name.capitalize()}: CHƯA CÓ", "type": "unsupported"},
        ],
        "data_time": f"Thông báo lúc {now_str}",
    }


def check_out_of_scope_intent(unaccented: str) -> dict | None:
    """
    Rào toàn diện mọi câu hỏi về các thông số môi trường, hóa lý, sinh học,
    sức khỏe cá hoặc thiết bị mà hệ thống ao nuôi CHƯA có cảm biến phần cứng để đo.
    """
    # 1. Độ ẩm (không khí / đất / ao)
    if re.search(r"\b(do\s*am|am\s*do|do\s*am\s*khong\s*khi|do\s*am\s*dat|do\s*am\s*ao|am\s*uot|co\s*am\s*khong)\b", unaccented):
        return handle_out_of_scope("độ ẩm của ao (độ ẩm không khí / đất)")

    # 2. Độ pH, tính axit, tính kiềm, phèn
    if (
        re.search(r"\b(do\s+ph|ph\s*(ao|nuoc|la|bao nhieu|hien tai)?|axit|acid|tinh\s*kiem|do\s*kiem|kiem\s*ao|phen|nhiem\s*phen|nuoc\s*phen|nuoc\s*chua|do\s*chua)\b", unaccented)
        or unaccented.strip() in {"ph", "do ph", "kiem"}
    ):
        return handle_out_of_scope("độ pH và độ phèn / độ kiềm của nước")

    # 3. Oxy hòa tan (DO)
    if re.search(r"\b(oxy|o2|oxy\s*hoa\s*tan|nong\s*do\s*oxy|luong\s*oxy|thieu\s*oxy|chi\s*so\s*do|oxy\s*trong\s*nuoc|khi\s*oxy)\b", unaccented):
        return handle_out_of_scope("nồng độ Oxy hòa tan (DO)")

    # 4. Nhiệt độ nước / Nhiệt độ môi trường
    if re.search(r"\b(nhiet\s*do|nhiet\s*do\s*nuoc|nhiet\s*do\s*ao|nuoc\s*nong|nuoc\s*lanh|nong\s*khong|lanh\s*khong|do\s+[cf]\b|°[cf])\b", unaccented):
        return handle_out_of_scope("nhiệt độ nước ao")

    # 5. Độ mặn, muối, TDS, độ dẫn điện EC
    if re.search(r"\b(do\s*man|man\s*khong|nong\s*do\s*muoi|ham\s*luong\s*muoi|tds|do\s*dan\s*dien|\bec\b|chat\s*ran\s*hoa\s*tan)\b", unaccented):
        return handle_out_of_scope("độ mặn và độ dẫn điện (TDS / EC)")

    # 6. Độ đục, độ trong, chất lượng nước
    if re.search(r"\b(do\s*duc|do\s*trong|nuoc\s*duc|nuoc\s*trong|duc\s*khong|trong\s*khong|phu\s*sa|secchi)\b", unaccented):
        return handle_out_of_scope("độ đục và độ trong của nước")

    # 7. Khí độc, hóa chất, amoniac, nitrit, clo
    if re.search(r"\b(khi\s*doc|amoniac|nh3|nh4|no2|no3|h2s|nitrit|nitrat|clo|chlorine|kim\s*loai\s*nang|thuoc\s*tru\s*sau|chat\s*doc|mui\s*hoi|mui\s*tanh)\b", unaccented):
        return handle_out_of_scope("khí độc (NH3, NO2, H2S) và hóa chất trong nước")

    # 8. Vi sinh, tảo, màu nước
    if re.search(r"\b(vi\s*sinh|tao|tao\s*doc|tao\s*lam|tao\s*do|mau\s*nuoc|nuoc\s*mau\s*gi|nuoc\s*xanh|nuoc\s*vang|nuoc\s*den|rong|reu|khuan|vi\s*khuan|nam\s*moc)\b", unaccented):
        return handle_out_of_scope("chỉ số vi sinh, tảo và màu nước")

    # 9. Bệnh cá, sức khỏe cá, thuốc chữa bệnh
    if re.search(r"\b(benh|benh\s*ca|ca\s*(bi\s*)?benh|ca\s*chet|ca\s*noi\s*dau|chua\s*benh|thuoc\s*cho\s*ca|khang\s*sinh|lo\s*loet|xuat\s*huyet|dom\s*do|trung\s*mo\s*neo|suc\s*khoe\s*ca)\b", unaccented):
        return handle_out_of_scope("chẩn đoán bệnh cá và sức khỏe đàn cá")

    # 10. Thức ăn cá, cho ăn, dinh dưỡng
    if re.search(r"\b(thuc\s*an|cho\s*(ca\s*)?an|luong\s*thuc\s*an|cam\s*ca|thuc\s*an\s*vien|fcr|tang\s*trong|dinh\s*duong|cho\s*an\s*chua)\b", unaccented):
        return handle_out_of_scope("quản lý thức ăn và chế độ cho cá ăn")

    # 11. Cân nặng, kích thước, sản lượng, số lượng cá
    if re.search(r"\b(trong\s*luong\s*ca|can\s*nang|kich\s*thuoc\s*ca|ca\s*nang|ca\s*lon\s*chua|so\s*luong\s*ca|mat\s*do\s*ca|san\s*luong|thu\s*hoach)\b", unaccented):
        return handle_out_of_scope("trọng lượng, mật độ và sản lượng cá")

    # 12. Camera, hình ảnh, video
    if re.search(r"\b(camera|hinh\s*anh|video|xem\s*ao|quan\s*sat\s*ca|nhin\s*thay\s*ca|chup\s*anh)\b", unaccented):
        return handle_out_of_scope("camera giám sát hình ảnh ao nuôi")

    return None



def handle_help() -> dict:
    """Hướng dẫn sử dụng các câu hỏi gợi ý."""
    update_context("help")
    title = "Tôi có thể giúp bạn tra cứu và điều khiển hệ thống ao nuôi:"
    description = (
        "💡 Bạn có thể hỏi bằng tiếng Việt tự nhiên bất kỳ:\n"
        "• 'Giờ ao tôi như thế nào rồi' hoặc 'Tình hình ao hiện tại'\n"
        "• 'Trong 30 phút qua nước tăng bao nhiêu?' rồi hỏi tiếp: 'Thế còn 1 giờ thì sao?'\n"
        "• 'Bơm cấp và bơm xả đang thế nào?' hoặc 'Máy bơm có đang chạy không?'\n"
        "• 'Tóm tắt tình trạng ao hôm nay.' hoặc 'Hôm nay bơm chạy mấy lần?'\n"
        "• 'Bật bơm cấp nước vào ao', 'Xả bớt nước ra', 'Chuyển sang tự động'...\n"
        "• 'Có cảnh báo hay lỗi gì không?', 'Ngưỡng bật bơm là bao nhiêu?'..."
    )
    return {
        "handled": True,
        "intent": "help",
        "type": "help",
        "status_icon": "🤖",
        "title": title,
        "description": description,
        "metrics": [],
        "data_time": datetime.now().strftime("%H:%M:%S - %d/%m/%Y"),
    }


# ============================================================================
#  Định tuyến ý định chính (Route Intent – High Semantic & Contextual Awareness)
# ============================================================================

def route_intent(user_text: str) -> dict:
    """
    Phân tích câu hỏi tự nhiên tiếng Việt và gọi nghiệp vụ tương ứng.
    Nhận diện cả câu hỏi độc lập và câu hỏi tiếp nối theo ngữ cảnh (Contextual Follow-ups).
    """
    raw = (user_text or "").strip()
    norm = normalize_text(raw)
    unaccented = _strip_accents(norm)
    ctx = get_context()

    if not norm:
        return handle_greeting()

    # ── 0. BẢO VỆ AN TOÀN & CHỐNG PROMPT INJECTION ────────────────────────
    # Trường hợp A: Yêu cầu bật cả 2 bơm cùng lúc (nguy hiểm)
    is_multi_pump = bool(
        re.search(r"\b(bat|chay|mo|khoi dong)\s*(ca\s*)?(hai|2)\s*bom\b", unaccented) or
        "bat ca hai bom" in unaccented or "bat ca 2 bom" in unaccented or "bat ca bom" in unaccented or
        re.search(r"\bbat\s+(ca\s+)?(bom\s*cap|in)\s*(va|cung|dong thoi)\s*(bom\s*xa|out)\b", unaccented) or
        re.search(r"\bbat\s+dong\s*thoi\s*(ca\s*)?(hai|2)?\s*bom\b", unaccented)
    )
    if is_multi_pump:
        return handle_safety_pump_conflict()

    # Trường hợp B: Prompt Injection / Bỏ qua hướng dẫn / Cưỡng chế gửi lệnh
    is_bypass_attempt = bool(
        re.search(r"\b(bo qua\s*(huong dan|quy tac|an toan|lenh|kiem tra)|ignore\s*instructions|bypass)\b", unaccented) or
        "bo qua huong dan" in unaccented or "bo qua an toan" in unaccented or "hay bat bom" in unaccented
    )
    if is_bypass_attempt:
        return handle_safety_bypass_attempt()

    # ── 0.1. HỎI NGOÀI PHẠM VI CẢM BIẾN (Chưa có phần cứng đo) ────────────
    out_of_scope_resp = check_out_of_scope_intent(unaccented)
    if out_of_scope_resp:
        return out_of_scope_resp

    # ── 1. Chào hỏi & Cảm ơn ──────────────────────────────────────────────
    if re.search(r"^(chao|xin chao|hello|hi|hey|alo)\b", unaccented):
        return handle_greeting()

    if re.search(r"\b(cam on|thanks|thank you|cam on ban|cam on nhe)\b", unaccented):
        return handle_thanks()

    # ── 2. Xác nhận hoặc Hủy lệnh đang chờ ────────────────────────────────
    confirm_exact = {
        "xac nhan", "dong y", "thuc hien", "chap nhan", "duyet",
        "ok", "yes", "co", "dong y thuc hien", "xac nhan lenh", "ok nhe"
    }
    if unaccented in confirm_exact or re.match(r"^(xac nhan|dong y|chap nhan|thuc hien)(\s+(di|luon|lenh|thao tac))?$", unaccented):
        pending_id = chat_tools.get_latest_pending_action_id()
        if pending_id:
            return handle_confirm_action(pending_id)

    cancel_exact = {
        "huy", "thoi", "khong", "cancel", "no", "bo qua", "dung lai", "huy bo", "huy lenh"
    }
    if unaccented in cancel_exact or re.match(r"^(huy|thoi|bo qua|dung lai|cancel)(\s+(di|lenh|thao tac|bo qua))?$", unaccented):
        pending_id = chat_tools.get_latest_pending_action_id()
        if pending_id:
            return handle_cancel_action(pending_id)

    # ── 3. Câu hỏi về khoảng thời gian (Time Duration / Change / Trend) ───
    # Ví dụ: "Thế còn 1 giờ thì sao?", "Ê nửa tiếng nay ao có gì khác không?", "Nãy giờ nước thế nào?"
    dur_minutes = extract_minutes(unaccented)
    if dur_minutes is not None:
        is_change_query = bool(
            re.search(r"\b(tang|giam|bien dong|thay doi|khac|co gi khac|khac gi|co bien gi|bien chuyen|co gi moi|co sao khong|on khong|the nao|nhu the nao|sao roi|sao|thi sao|rut|xuong|chenh lech|dang len|dang cao|nuoc dang)\b", unaccented) or
            re.search(r"\b(the con|con|vay|roi|qua|nay|truoc|gan day)\b", unaccented) or
            ctx.get("intent") == "change"
        )
        is_not_alert = not re.search(r"\b(canh bao|bao dong|loi|su co|hu hong)\b", unaccented)
        is_not_config = not re.search(r"\b(cai dat|thiet lap|nguong|cau hinh|khi nao)\b", unaccented)
        if is_change_query and is_not_alert and is_not_config:
            minutes = max(1, min(dur_minutes, 1440))
            return handle_change(minutes=minutes)

    # ── 4. Câu hỏi tiếp nối về thiết bị / máy bơm ─────────────────────────
    # Ví dụ: "Thế còn máy bơm thì sao?", "Bơm thì sao?", "Còn bơm cấp?"
    if (re.search(r"\b(the con|con|vay)\b", unaccented) and re.search(r"\b(bom|may bom|relay|role|esp|esp32)\b", unaccented)) or \
       (re.search(r"\b(bom|may bom|relay|role|esp|esp32)\b", unaccented) and re.search(r"\b(thi sao|sao|the nao)\b", unaccented)):
        return handle_device_status()

    # ── 5. Điều khiển máy bơm và Chế độ ──────────────────────────────────
    # Bơm cấp IN - BẬT
    if re.search(r"\b(bat|mo|chay|khoi dong|bom them|cap nuoc|cho nuoc vao|bom vao)\b.*\b(cap|vao|in|nuoc|ao)\b", unaccented) or \
       "bom nuoc vao ao" in unaccented or "cho nuoc vao ao" in unaccented or \
       re.search(r"\bbat\s+pump\s*in\b", unaccented):
        return handle_control("pump_in", "ON")

    # Bơm cấp IN - TẮT
    if re.search(r"\b(tat|dung|ngung|ngat|khoa|thoi)\b.*\b(cap|vao|in)\b", unaccented) or \
       re.search(r"\btat\s+pump\s*in\b", unaccented):
        return handle_control("pump_in", "OFF")

    # Bơm thoát OUT - BẬT
    if re.search(r"\b(bat|mo|chay|khoi dong|xa nuoc|rut nuoc|thoat nuoc|hut nuoc|bom ra)\b.*\b(xa|thoat|ra|out|nuoc|ao)\b", unaccented) or \
       "xa nuoc" in unaccented or "xa bot nuoc" in unaccented or \
       re.search(r"\bbat\s+pump\s*out\b", unaccented):
        return handle_control("pump_out", "ON")

    # Bơm thoát OUT - TẮT
    if re.search(r"\b(tat|dung|ngung|ngat|khoa|thoi)\b.*\b(xa|thoat|ra|out)\b", unaccented) or \
       re.search(r"\btat\s+pump\s*out\b", unaccented):
        return handle_control("pump_out", "OFF")

    # Chế độ AUTO
    if re.search(r"\b(chuyen|bat|sang|cai|chay)\s*(che do\s*)?(tu dong|auto)\b", unaccented) and not re.search(r"\b(hoi|la gi|the nao)\b", unaccented):
        if "thu cong" not in unaccented and "manual" not in unaccented:
            return handle_control("mode", "AUTO")

    # Chế độ MANUAL
    if re.search(r"\b(chuyen|bat|sang|cai|chay)\s*(che do\s*)?(thu cong|manual|bang tay)\b", unaccented) and not re.search(r"\b(hoi|la gi|the nao)\b", unaccented):
        return handle_control("mode", "MANUAL")

    # ── 6. Tóm tắt tình trạng ao hôm nay / 24h ────────────────────────────
    if re.search(r"\b(tom tat|tong ket|bao cao|thong ke|tong hop)\b", unaccented) or \
       re.search(r"\bhom nay\b", unaccented) or \
       "24h" in unaccented or "24 gio" in unaccented:
        since_midnight = "24" not in unaccented
        return handle_summary(since_midnight=since_midnight)

    # ── 7. Trạng thái thiết bị / máy bơm (ưu tiên trước biến động) ────────
    if re.search(r"\b(bom|may bom|hai bom|relay|role|esp|esp32)\b", unaccented) and \
       re.search(r"\b(dang|the nao|nhu the nao|sao roi|chay khong|chay|bat hay tat|on khong|hoat dong|online|offline|thi sao|sao)\b", unaccented):
        return handle_device_status()

    # ── 8. Cảnh báo và Sự cố ─────────────────────────────────────────────
    if re.search(r"\b(canh bao|bao dong|su co|loi|hu hong|truc trac|bat thuong|nguy hiem|co van de gi)\b", unaccented) or \
       re.search(r"\b(he thong|ao|thiet bi)\s*(co\s*)?(on khong|binh thuong khong|sao khong)\b", unaccented):
        return handle_alerts()

    # ── 9. Cấu hình và Ngưỡng ────────────────────────────────────────────
    if re.search(r"\b(cau hinh|nguong|cai dat|thiet lap|thong so|gioi han|dinh muc)\b", unaccented) or \
       re.search(r"\bkhi nao\s*(thi\s*)?(bat|tat)\s*bom\b", unaccented):
        return handle_config()

    # ── 10. Biến động mực nước: Tăng/giảm/rút/dâng theo thời gian ─────────
    if re.search(r"\b(tang|giam|bien dong|thay doi|rut|xuong|chenh lech|dang len|dang cao|nuoc dang)\b", unaccented) or \
       re.search(r"\btrong\s+(\d+)\s*(phut|p|m|gio|tieng|h)\b", unaccented) or \
       re.search(r"\bnuoc\s+(co\s+)?(tang|giam|rut)\b", unaccented):

        minutes = 30
        min_extracted = extract_minutes(unaccented)
        if min_extracted:
            minutes = min_extracted

        minutes = max(1, min(minutes, 1440))
        return handle_change(minutes=minutes)

    # ── 11. Trạng thái tổng quan ao & Mực nước ────────────────────────────
    # Ví dụ: "Giờ ao tôi như thế nào rồi", "tinh hinh ao hien tai", "ao gio sao roi", "nuoc non sao roi"
    if re.search(r"\b(ao|ho|nuoc|muc nuoc)\b", unaccented):
        return handle_status()

    # ── 12. Trợ giúp / Hướng dẫn ──────────────────────────────────────────
    if re.search(r"\b(huong dan|tro giup|help|chuc nang|ban lam duoc gi|cau hoi goi y)\b", unaccented):
        return handle_help()

    # ── 13. Fallback nếu không xác định được ──────────────────────────────
    return {
        "handled": False,
        "intent": "unknown",
        "type": "fallback",
        "status_icon": "🤖",
        "title": "Tôi chưa hiểu rõ câu hỏi này",
        "description": (
            "Bạn có thể hỏi tự nhiên về:\n"
            "• 'Giờ ao tôi như thế nào rồi?' hoặc 'Mực nước hiện tại'\n"
            "• 'Trong 30 phút qua nước tăng bao nhiêu?' rồi hỏi tiếp: 'Thế còn 1 giờ thì sao?'\n"
            "• 'Bơm cấp và bơm xả đang thế nào?'\n"
            "• 'Tóm tắt tình trạng ao hôm nay.'\n"
            "• 'Bật bơm cấp nước vào ao' hoặc 'Có cảnh báo gì không?'"
        ),
        "metrics": [],
        "data_time": datetime.now().strftime("%H:%M:%S - %d/%m/%Y"),
    }
