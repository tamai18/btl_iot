# ============================================================================
#  chat_tools.py – Các hàm truy xuất dữ liệu cho hệ thống chatbox ao nuôi
#  Dùng bởi cả Fast Path router (chat_router.py) và LLM function calling
# ============================================================================
import logging
import threading
import uuid
from datetime import datetime, timedelta

import db
import mqtt_client

logger = logging.getLogger(__name__)

# ── Module-level state ──────────────────────────────────────────────────────
# Lệnh điều khiển đang chờ xác nhận (action_id → dict)
_pending_actions: dict = {}
_pending_lock = threading.Lock()

# Cache ngưỡng cấu hình (tránh query liên tục)
_config_cache: dict = {}
_config_cache_ts: datetime | None = None
_CONFIG_CACHE_TTL = 30  # giây


# ============================================================================
#  Helper: Lấy ngưỡng cấu hình (có cache 30 giây)
# ============================================================================

def _get_config_thresholds() -> dict:
    """Truy vấn system_config và cache lại 30 giây. Trả về dict các giá trị số."""
    global _config_cache, _config_cache_ts

    now = datetime.now()
    if _config_cache_ts and (now - _config_cache_ts).total_seconds() < _CONFIG_CACHE_TTL:
        return dict(_config_cache)

    try:
        rows = db.execute(
            "SELECT config_key, config_value FROM system_config",
            fetch="all",
        )
        raw = {r["config_key"]: r["config_value"] for r in (rows or [])}
    except Exception as e:
        logger.warning("[ChatTools] Lỗi truy vấn system_config: %s", e)
        return dict(_config_cache) if _config_cache else {}

    # Chuyển các giá trị số quan trọng
    numeric_keys = [
        "in_on_pct", "in_off_pct", "out_on_pct", "out_off_pct",
        "limit_high", "limit_low", "d_empty", "d_full",
        "max_run_min", "publish_sec",
    ]
    result = {}
    for k in numeric_keys:
        try:
            result[k] = float(raw.get(k, 0))
        except (TypeError, ValueError):
            result[k] = 0.0
    # Giữ lại cả raw string cho tham khảo
    result["_raw"] = raw

    _config_cache = result
    _config_cache_ts = now
    return dict(result)


def _determine_level_state(level: float, cfg: dict) -> str:
    """Xác định trạng thái mực nước dựa trên ngưỡng cấu hình."""
    limit_high = cfg.get("limit_high", 95)
    limit_low = cfg.get("limit_low", 5)
    in_on = cfg.get("in_on_pct", 30)
    out_on = cfg.get("out_on_pct", 90)

    if level >= limit_high:
        return "vượt ngưỡng cảnh báo cao"
    if level <= limit_low:
        return "dưới ngưỡng cảnh báo thấp"
    # Gần ngưỡng = trong khoảng 5% so với ngưỡng bật bơm
    if level <= in_on + 5:
        return "gần ngưỡng bật bơm cấp"
    if level >= out_on - 5:
        return "gần ngưỡng bật bơm thoát"
    return "bình thường"


def _iso(dt_val) -> str | None:
    """Chuyển datetime hoặc string thành ISO string an toàn."""
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime):
        return dt_val.isoformat(timespec="seconds")
    return str(dt_val)


# ============================================================================
#  1. get_current_status() – Trạng thái hiện tại của ao
# ============================================================================

def get_current_status() -> dict:
    """
    Đọc trạng thái mới nhất từ MQTT (nhanh nhất), fallback sang DB.
    Trả về dict đầy đủ thông tin mực nước, bơm, thiết bị.
    """
    cfg = _get_config_thresholds()
    latest = mqtt_client.get_latest()
    mqtt_connected = mqtt_client.is_connected()
    is_stale = False
    data_time = None

    # Ưu tiên dữ liệu MQTT (real-time)
    if latest and latest.get("level") is not None:
        try:
            water_level = float(latest["level"])
            distance_cm = float(latest.get("dist", 0))
            pump_in = bool(latest.get("in", 0))
            pump_out = bool(latest.get("out", 0))
            auto_mode = bool(latest.get("auto", 1))
            sensor_err = bool(latest.get("err", 0))
            fault_code = str(latest.get("fault", "none"))
            rssi = int(latest.get("rssi", 0))
            esp32_status = latest.get("esp32_status", "unknown")
            data_time = latest.get("ts")

            # Kiểm tra dữ liệu cũ (stale > 15 giây)
            if data_time:
                try:
                    ts_dt = datetime.fromisoformat(data_time)
                    is_stale = (datetime.now() - ts_dt).total_seconds() > 15
                except (ValueError, TypeError):
                    is_stale = True
        except (TypeError, ValueError, KeyError):
            latest = None  # Fallback sang DB

    # Fallback: truy vấn DB nếu MQTT không có dữ liệu
    if not latest or latest.get("level") is None:
        row = db.execute(
            "SELECT * FROM sensor_data ORDER BY recorded_at DESC LIMIT 1",
            fetch="one",
        )
        if row:
            water_level = float(row.get("water_level", 0))
            distance_cm = float(row.get("distance_cm", 0))
            pump_in = bool(row.get("pump_in", 0))
            pump_out = bool(row.get("pump_out", 0))
            auto_mode = bool(row.get("auto_mode", 1))
            sensor_err = bool(row.get("sensor_err", 0))
            fault_code = str(row.get("fault_code", "none"))
            rssi = int(row.get("rssi", 0))
            esp32_status = latest.get("esp32_status", "unknown") if latest else "unknown"
            data_time = _iso(row.get("recorded_at"))

            # Dữ liệu DB luôn stale nếu > 15 giây
            if data_time:
                try:
                    ts_dt = datetime.fromisoformat(data_time)
                    is_stale = (datetime.now() - ts_dt).total_seconds() > 15
                except (ValueError, TypeError):
                    is_stale = True
            else:
                is_stale = True
        else:
            # Không có dữ liệu nào
            return {
                "water_level": None,
                "distance_cm": None,
                "pump_in": False,
                "pump_out": False,
                "auto_mode": True,
                "sensor_err": False,
                "fault_code": "none",
                "rssi": 0,
                "esp32_status": "offline",
                "data_time": None,
                "is_stale": True,
                "mqtt_connected": mqtt_connected,
                "level_state": "không có dữ liệu",
                "config": cfg,
            }

    level_state = _determine_level_state(water_level, cfg)

    return {
        "water_level": round(water_level, 1),
        "distance_cm": round(distance_cm, 1),
        "pump_in": pump_in,
        "pump_out": pump_out,
        "auto_mode": auto_mode,
        "sensor_err": sensor_err,
        "fault_code": fault_code,
        "rssi": rssi,
        "esp32_status": esp32_status,
        "data_time": data_time,
        "is_stale": is_stale,
        "mqtt_connected": mqtt_connected,
        "level_state": level_state,
        "config": {
            "in_on_pct": cfg.get("in_on_pct", 30),
            "in_off_pct": cfg.get("in_off_pct", 50),
            "out_on_pct": cfg.get("out_on_pct", 90),
            "out_off_pct": cfg.get("out_off_pct", 80),
            "limit_high": cfg.get("limit_high", 95),
            "limit_low": cfg.get("limit_low", 5),
        },
    }


# ============================================================================
#  2. get_level_change() – Biến động mực nước trong N phút
# ============================================================================

def get_level_change(minutes: int = 30) -> dict:
    """
    Tính toán xu hướng thay đổi mực nước trong khoảng thời gian cho trước.
    Lấy trung bình 3 mẫu đầu và 3 mẫu cuối để giảm nhiễu.
    """
    cfg = _get_config_thresholds()
    now = datetime.now()
    since = now - timedelta(minutes=minutes)

    rows = db.execute(
        """SELECT water_level, distance_cm, recorded_at
           FROM sensor_data
           WHERE recorded_at >= %s AND recorded_at <= %s
           ORDER BY recorded_at ASC""",
        (since, now),
        fetch="all",
    )

    if not rows or len(rows) < 2:
        return {
            "delta_pct": 0.0,
            "delta_cm": 0.0,
            "trend": "không đủ dữ liệu",
            "min_level": None,
            "max_level": None,
            "avg_level": None,
            "sample_count": len(rows) if rows else 0,
            "first_sample_at": None,
            "last_sample_at": None,
            "coverage_minutes": 0,
            "requested_minutes": minutes,
            "coverage_ok": False,
        }

    levels = [float(r["water_level"]) for r in rows]

    # Trung bình 3 mẫu đầu và cuối để giảm nhiễu
    n_avg = min(3, len(levels))
    avg_first = sum(levels[:n_avg]) / n_avg
    avg_last = sum(levels[-n_avg:]) / n_avg

    delta_pct = round(avg_last - avg_first, 2)

    # Tính delta_cm dựa trên khoảng cách d_empty - d_full
    d_empty = cfg.get("d_empty", 100)
    d_full = cfg.get("d_full", 10)
    range_cm = d_empty - d_full
    delta_cm = round(delta_pct * range_cm / 100, 2) if range_cm > 0 else 0.0

    # Xác định xu hướng
    if delta_pct > 0.5:
        trend = "tăng"
    elif delta_pct < -0.5:
        trend = "giảm"
    else:
        trend = "ổn định"

    # Tính phạm vi thời gian thực tế
    first_at = _iso(rows[0].get("recorded_at"))
    last_at = _iso(rows[-1].get("recorded_at"))

    try:
        first_dt = datetime.fromisoformat(str(rows[0]["recorded_at"]))
        last_dt = datetime.fromisoformat(str(rows[-1]["recorded_at"]))
        coverage_minutes = round((last_dt - first_dt).total_seconds() / 60, 1)
    except (ValueError, TypeError):
        coverage_minutes = 0

    coverage_ok = coverage_minutes >= (minutes * 0.7)

    return {
        "delta_pct": delta_pct,
        "delta_cm": delta_cm,
        "trend": trend,
        "min_level": round(min(levels), 1),
        "max_level": round(max(levels), 1),
        "avg_level": round(sum(levels) / len(levels), 1),
        "sample_count": len(rows),
        "first_sample_at": first_at,
        "last_sample_at": last_at,
        "coverage_minutes": coverage_minutes,
        "requested_minutes": minutes,
        "coverage_ok": coverage_ok,
    }


# ============================================================================
#  3. get_day_summary() – Tổng kết hoạt động trong N giờ / từ đầu ngày
# ============================================================================

def get_day_summary(hours: int = 24, since_midnight: bool = False) -> dict:
    """
    Thống kê tổng hợp: min/max mực nước, số lần bật bơm, số cảnh báo...
    """
    now = datetime.now()

    if since_midnight:
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        period_start = now - timedelta(hours=hours)

    period_end = now

    # ── Truy vấn dữ liệu cảm biến ──────────────────────────────────────────
    rows = db.execute(
        """SELECT water_level, pump_in, pump_out, recorded_at
           FROM sensor_data
           WHERE recorded_at >= %s AND recorded_at <= %s
           ORDER BY recorded_at ASC""",
        (period_start, period_end),
        fetch="all",
    )

    if not rows:
        return {
            "max_level": None, "max_time": None,
            "min_level": None, "min_time": None,
            "avg_level": None,
            "pump_in_activations": 0, "pump_out_activations": 0,
            "pump_in_total_minutes": 0, "pump_out_total_minutes": 0,
            "alert_count": 0, "unresolved_alert_count": 0,
            "sample_count": 0,
            "period_start": _iso(period_start),
            "period_end": _iso(period_end),
        }

    levels = [float(r["water_level"]) for r in rows]
    max_level = max(levels)
    min_level = min(levels)
    avg_level = round(sum(levels) / len(levels), 1)

    # Tìm thời điểm max/min
    max_idx = levels.index(max_level)
    min_idx = levels.index(min_level)
    max_time = _iso(rows[max_idx].get("recorded_at"))
    min_time = _iso(rows[min_idx].get("recorded_at"))

    # ── Đếm số lần bật bơm (chuyển từ OFF → ON) ────────────────────────────
    pump_in_activations = 0
    pump_out_activations = 0
    pump_in_on_records = 0
    pump_out_on_records = 0

    prev_pin = None
    prev_pout = None
    for r in rows:
        pin = bool(r.get("pump_in", 0))
        pout = bool(r.get("pump_out", 0))

        if prev_pin is not None and pin and not prev_pin:
            pump_in_activations += 1
        if prev_pout is not None and pout and not prev_pout:
            pump_out_activations += 1

        if pin:
            pump_in_on_records += 1
        if pout:
            pump_out_on_records += 1

        prev_pin = pin
        prev_pout = pout

    # Ước tính thời gian chạy bơm (số bản ghi ON × chu kỳ gửi dữ liệu)
    cfg = _get_config_thresholds()
    publish_sec = cfg.get("publish_sec", 2)
    pump_in_total_minutes = round(pump_in_on_records * publish_sec / 60, 1)
    pump_out_total_minutes = round(pump_out_on_records * publish_sec / 60, 1)

    # ── Đếm cảnh báo trong khoảng thời gian ────────────────────────────────
    alert_stats = db.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN status = 'UNRESOLVED' THEN 1 ELSE 0 END) AS unresolved
           FROM alerts
           WHERE created_at >= %s AND created_at <= %s""",
        (period_start, period_end),
        fetch="one",
    )

    alert_count = int(alert_stats["total"]) if alert_stats and alert_stats.get("total") else 0
    unresolved_count = int(alert_stats["unresolved"]) if alert_stats and alert_stats.get("unresolved") else 0

    return {
        "max_level": round(max_level, 1),
        "max_time": max_time,
        "min_level": round(min_level, 1),
        "min_time": min_time,
        "avg_level": avg_level,
        "pump_in_activations": pump_in_activations,
        "pump_out_activations": pump_out_activations,
        "pump_in_total_minutes": pump_in_total_minutes,
        "pump_out_total_minutes": pump_out_total_minutes,
        "alert_count": alert_count,
        "unresolved_alert_count": unresolved_count,
        "sample_count": len(rows),
        "period_start": _iso(period_start),
        "period_end": _iso(period_end),
    }


# ============================================================================
#  4. get_alerts() – Danh sách cảnh báo
# ============================================================================

def get_alerts(status: str | None = None, hours: int = 24, limit: int = 5) -> dict:
    """
    Truy vấn bảng alerts với bộ lọc trạng thái và thời gian.
    """
    now = datetime.now()
    since = now - timedelta(hours=hours)

    where_clauses = ["created_at >= %s"]
    params: list = [since]

    if status:
        where_clauses.append("status = %s")
        params.append(status.upper())

    where_sql = "WHERE " + " AND ".join(where_clauses)

    # Lấy danh sách cảnh báo
    rows = db.execute(
        f"""SELECT id, alert_code, message, severity, water_level, status,
                   created_at, resolved_at
            FROM alerts
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s""",
        params + [limit],
        fetch="all",
    )

    # Đếm tổng và chưa xử lý
    count_row = db.execute(
        f"SELECT COUNT(*) AS total FROM alerts {where_sql}",
        params,
        fetch="one",
    )
    unresolved_row = db.execute(
        """SELECT COUNT(*) AS cnt FROM alerts
           WHERE created_at >= %s AND status = 'UNRESOLVED'""",
        (since,),
        fetch="one",
    )

    total_count = int(count_row["total"]) if count_row and count_row.get("total") else 0
    unresolved_count = int(unresolved_row["cnt"]) if unresolved_row and unresolved_row.get("cnt") else 0

    alerts_list = []
    for r in (rows or []):
        alerts_list.append({
            "id": r.get("id"),
            "alert_code": r.get("alert_code"),
            "message": r.get("message"),
            "severity": r.get("severity"),
            "status": r.get("status"),
            "created_at": _iso(r.get("created_at")),
            "water_level": r.get("water_level"),
        })

    return {
        "total_count": total_count,
        "unresolved_count": unresolved_count,
        "alerts": alerts_list,
    }


# ============================================================================
#  5. get_config() – Cấu hình hệ thống + ESP32
# ============================================================================

def get_config() -> dict:
    """
    Lấy cấu hình server (system_config) và cấu hình báo cáo từ ESP32.
    So sánh xem server và ESP32 có đồng bộ hay không.
    """
    cfg = _get_config_thresholds()
    raw = cfg.get("_raw", {})

    server_config = {
        "in_on_pct": cfg.get("in_on_pct", 30),
        "in_off_pct": cfg.get("in_off_pct", 50),
        "out_on_pct": cfg.get("out_on_pct", 90),
        "out_off_pct": cfg.get("out_off_pct", 80),
        "limit_high": cfg.get("limit_high", 95),
        "limit_low": cfg.get("limit_low", 5),
        "d_empty": cfg.get("d_empty", 100),
        "d_full": cfg.get("d_full", 10),
        "max_run_min": cfg.get("max_run_min", 20),
        "publish_sec": cfg.get("publish_sec", 2),
    }

    # Lấy cấu hình báo cáo từ ESP32 qua MQTT
    latest = mqtt_client.get_latest()
    esp32_config = latest.get("reported_cfg")
    cfg_updated_at = latest.get("cfg_updated_at")

    # So sánh đồng bộ trên các ngưỡng quan trọng
    config_synced = False
    if esp32_config and isinstance(esp32_config, dict):
        try:
            synced = True
            check_keys = [
                ("in_on_pct", "inOn"), ("in_off_pct", "inOff"),
                ("out_on_pct", "outOn"), ("out_off_pct", "outOff"),
            ]
            for server_key, esp_key in check_keys:
                server_val = float(server_config.get(server_key, 0))
                esp_val = float(esp32_config.get(esp_key, -1))
                if abs(server_val - esp_val) > 0.1:
                    synced = False
                    break
            config_synced = synced
        except (TypeError, ValueError):
            config_synced = False

    result = {
        "server_config": server_config,
        "esp32_config": esp32_config,
        "config_synced": config_synced,
    }
    if cfg_updated_at:
        result["cfg_updated_at"] = cfg_updated_at

    return result


# ============================================================================
#  6. propose_control() – Đề xuất lệnh điều khiển (cần xác nhận)
# ============================================================================

def propose_control(command: str, payload: str) -> dict:
    """
    Tạo lệnh chờ xác nhận. Kiểm tra an toàn và cảnh báo trước khi thực thi.
    command: pump_in | pump_out | mode
    payload: ON/OFF cho bơm, AUTO/MANUAL cho mode
    """
    # Kiểm tra lệnh hợp lệ
    allowed_commands = {"pump_in", "pump_out", "mode"}
    if command not in allowed_commands:
        return {
            "success": False,
            "message": f"Lệnh không hợp lệ: {command}. Chỉ hỗ trợ: {', '.join(allowed_commands)}",
        }

    payload = payload.upper()
    if command in ("pump_in", "pump_out") and payload not in ("ON", "OFF"):
        return {
            "success": False,
            "message": "Trạng thái bơm chỉ được là ON hoặc OFF",
        }
    if command == "mode" and payload not in ("AUTO", "MANUAL"):
        return {
            "success": False,
            "message": "Chế độ chỉ được là AUTO hoặc MANUAL",
        }

    # Tạo action_id duy nhất
    action_id = uuid.uuid4().hex[:8]
    expires_at = datetime.now() + timedelta(seconds=60)

    # Kiểm tra trạng thái hiện tại để đưa ra cảnh báo
    warnings = []
    try:
        status = get_current_status()
        if status.get("water_level") is not None:
            level = status["water_level"]

            if command == "pump_in" and payload == "ON":
                if level >= 85:
                    warnings.append(f"Mực nước hiện tại đã cao ({level}%), bật bơm cấp có thể gây tràn")
                if status.get("pump_out"):
                    warnings.append("Bơm thoát đang chạy, bật thêm bơm cấp có thể gây xung đột")

            elif command == "pump_out" and payload == "ON":
                if level <= 15:
                    warnings.append(f"Mực nước hiện tại rất thấp ({level}%), bật bơm thoát có thể gây cạn ao")
                if status.get("pump_in"):
                    warnings.append("Bơm cấp đang chạy, bật thêm bơm thoát có thể gây xung đột")

            if command in ("pump_in", "pump_out") and payload == "ON":
                if status.get("auto_mode"):
                    warnings.append("Bật bơm sẽ tự động chuyển hệ thống sang chế độ MANUAL")

            if status.get("sensor_err"):
                warnings.append("Cảm biến đang báo lỗi, thao tác điều khiển có thể không an toàn")

            if status.get("is_stale"):
                warnings.append("Dữ liệu cảm biến không được cập nhật, kết quả có thể không chính xác")
    except Exception as e:
        logger.warning("[ChatTools] Lỗi kiểm tra trạng thái khi propose_control: %s", e)

    # Tạo thông điệp xác nhận bằng tiếng Việt
    cmd_names = {
        "pump_in": "bơm cấp (IN)",
        "pump_out": "bơm thoát (OUT)",
        "mode": "chế độ",
    }
    payload_names = {
        "ON": "BẬT", "OFF": "TẮT",
        "AUTO": "TỰ ĐỘNG", "MANUAL": "THỦ CÔNG",
    }
    cmd_vn = cmd_names.get(command, command)
    payload_vn = payload_names.get(payload, payload)

    confirmation_message = (
        f"Bạn muốn {payload_vn} {cmd_vn}?\n"
        f"Gõ 'xác nhận' hoặc 'đồng ý' để thực hiện, "
        f"'hủy' để bỏ qua. (Hiệu lực 60 giây)"
    )

    # Lưu vào pending
    action_data = {
        "action_id": action_id,
        "command": command,
        "payload": payload,
        "expires_at": expires_at,
        "used": False,
        "created_at": datetime.now(),
    }
    with _pending_lock:
        # Dọn dẹp các action đã hết hạn
        expired_keys = [
            k for k, v in _pending_actions.items()
            if v["expires_at"] < datetime.now()
        ]
        for k in expired_keys:
            del _pending_actions[k]

        _pending_actions[action_id] = action_data

    if warnings:
        confirmation_message += "\n⚠️ Lưu ý:\n" + "\n".join(f"  - {w}" for w in warnings)

    return {
        "success": True,
        "action_id": action_id,
        "command": command,
        "payload": payload,
        "expires_at": _iso(expires_at),
        "warnings": warnings,
        "confirmation_message": confirmation_message,
    }


# ============================================================================
#  7. confirm_control() – Xác nhận và thực thi lệnh điều khiển
# ============================================================================

def confirm_control(action_id: str) -> dict:
    """
    Tìm lệnh trong pending, kiểm tra chưa hết hạn, thực thi qua MQTT.
    """
    with _pending_lock:
        action = _pending_actions.get(action_id)
        if not action:
            return {
                "success": False,
                "message": "Không tìm thấy lệnh chờ xác nhận. Có thể đã hết hạn hoặc bị hủy.",
            }

        if action["expires_at"] < datetime.now():
            del _pending_actions[action_id]
            return {
                "success": False,
                "message": "Lệnh đã hết hạn (quá 60 giây). Vui lòng thao tác lại.",
            }

        if action["used"]:
            return {
                "success": False,
                "message": "Lệnh này đã được thực hiện trước đó.",
            }

        # Đánh dấu đã dùng
        action["used"] = True

    # Kiểm tra an toàn kết nối trước khi gửi lệnh
    if not mqtt_client.is_connected():
        return {
            "success": False,
            "message": "❌ Lỗi hệ thống: MQTT Broker đang mất kết nối. Vui lòng bật dịch vụ Mosquitto!",
        }

    latest = mqtt_client.get_latest()
    if latest.get("esp32_status") != "online":
        return {
            "success": False,
            "message": "❌ Thiết bị ngoại tuyến: ESP32 đang offline hoặc chưa kết nối MQTT. Không thể gửi lệnh điều khiển!",
        }

    # Thực thi lệnh qua MQTT
    command = action["command"]
    payload = action["payload"]

    try:
        log_id = mqtt_client.publish_command(command, payload, "chatbot")
    except Exception as e:
        logger.error("[ChatTools] Lỗi gửi lệnh MQTT: %s", e)
        return {
            "success": False,
            "message": f"Lỗi gửi lệnh: {e}",
        }

    # Xóa khỏi pending sau khi thực thi
    with _pending_lock:
        _pending_actions.pop(action_id, None)

    cmd_names = {"pump_in": "bơm cấp (IN)", "pump_out": "bơm thoát (OUT)", "mode": "chế độ"}
    payload_names = {"ON": "BẬT", "OFF": "TẮT", "AUTO": "TỰ ĐỘNG", "MANUAL": "THỦ CÔNG"}
    cmd_vn = cmd_names.get(command, command)
    payload_vn = payload_names.get(payload, payload)

    return {
        "success": True,
        "log_id": log_id,
        "message": f"✅ Đã gửi lệnh {payload_vn} {cmd_vn} tới ESP32 thành công (log #{log_id}).",
    }


# ============================================================================
#  8. cancel_control() – Hủy lệnh đang chờ xác nhận
# ============================================================================

def cancel_control(action_id: str) -> dict:
    """Xóa lệnh khỏi danh sách chờ xác nhận."""
    with _pending_lock:
        action = _pending_actions.pop(action_id, None)

    if action:
        return {
            "success": True,
            "message": "Đã hủy lệnh điều khiển. Không có thay đổi nào được thực hiện.",
        }
    return {
        "success": False,
        "message": "Không tìm thấy lệnh cần hủy (có thể đã hết hạn).",
    }


# ============================================================================
#  Helper: Lấy action_id đang chờ gần nhất (cho confirm/cancel flow)
# ============================================================================

def get_latest_pending_action_id() -> str | None:
    """Trả về action_id chưa dùng, chưa hết hạn gần nhất."""
    now = datetime.now()
    with _pending_lock:
        # Tìm action mới nhất còn hiệu lực
        valid = [
            (v["created_at"], k)
            for k, v in _pending_actions.items()
            if not v["used"] and v["expires_at"] > now
        ]
    if not valid:
        return None
    valid.sort(reverse=True)
    return valid[0][1]
