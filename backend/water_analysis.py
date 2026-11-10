# ============================================================================
#  water_analysis.py – Phân tích xu hướng & Dự báo mực nước ao nuôi
#  Kế hoạch v2: Hồi quy tuyến tính cuốn chiếu 5 phút, gộp mốc 10 giây
#  Nhận định theo quy tắc logic nghiệp vụ, đồng bộ với Rule Engine
# ============================================================================
import os
import math
from datetime import datetime, timedelta
import db

# ── HẰNG SỐ CẤU HÌNH THEO KẾ HOẠCH V2 ────────────────────────────────────────
WINDOW_SECONDS = 300                 # Cửa sổ phân tích: 5 phút gần nhất
BIN_SECONDS = 10                     # Độ rộng mốc gộp trung vị: 10 giây (khoảng 30 mốc)
MIN_COVERAGE_S = 240                 # Độ phủ tối thiểu khi bơm không đổi: 240s (80%)
MIN_COVERAGE_AFTER_PUMP_S = 120      # Độ phủ tối thiểu sau lần đổi trạng thái bơm
SETTLE_SECONDS = 20                  # Bỏ qua 20 giây đầu ngay sau khi bơm đổi trạng thái
MAX_LAST_SAMPLE_AGE_S = 15           # Mẫu cuối cũ hơn 15s thì coi là mất kết nối (DEVICE_OFFLINE)
MAX_GAP_S = 30                       # Khoảng hở dữ liệu lớn nhất cho phép
MIN_BINS = 10                        # Số mốc sau gộp tối thiểu

STABLE_SLOPE_THRESHOLD = 0.05        # Ngưỡng ổn định: dưới 0.05 điểm %/phút
SLOW_SLOPE_THRESHOLD = 0.3           # Ngưỡng tăng/giảm nhẹ: 0.05 đến dưới 0.3
MODERATE_SLOPE_THRESHOLD = 1.0       # Ngưỡng tăng/giảm: 0.3 đến dưới 1.0


# ── HÀM THUẦN: TÍNH TOÁN TRUNG VỊ (MEDIAN) ──────────────────────────────────
def _median(values):
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


# ── HÀM THUẦN: HỒI QUY BÌNH PHƯƠNG TỐI THIỂU BẬC NHẤT (OLS) ──────────────────
def fit_line(ts, hs):
    """
    ts: danh sách thời gian tính bằng phút (t_i)
    hs: danh sách mực nước tương ứng (%)
    Trả về dict: slope (v), h0, resid_std (s), slope_se
    """
    n = len(ts)
    if n < 3:
        return None
    t_mean = sum(ts) / n
    h_mean = sum(hs) / n
    sxx = sum((t - t_mean) ** 2 for t in ts)
    if sxx == 0:
        return None
    
    # Hệ số góc v (tốc độ đổi điểm %/phút)
    v = sum((t - t_mean) * (h - h_mean) for t, h in zip(ts, hs)) / sxx
    # h0: Mực nước ước tính tại mốc cuối cùng trên đường thẳng hồi quy
    h0 = h_mean + v * (ts[-1] - t_mean)
    
    # Tổng bình phương phần dư (SSR) và độ lệch chuẩn phần dư (s)
    ssr = sum((h - (h_mean + v * (t - t_mean))) ** 2 for t, h in zip(ts, hs))
    df = max(n - 2, 1)
    s = (ssr / df) ** 0.5
    slope_se = s / (sxx ** 0.5)
    
    return {
        "slope": v,
        "h0": h0,
        "resid_std": s,
        "slope_se": slope_se
    }


# ── LỌC DỮ LIỆU & GỘP MỐC 10 GIÂY ───────────────────────────────────────────
def process_samples(raw_samples, now_dt):
    """
    Làm sạch, xử lý lần đổi bơm, kiểm tra độ phủ và gộp mốc 10s bằng trung vị.
    Trả về (status_code, binned_ts, binned_hs, extra_info)
    """
    if not raw_samples:
        return "INSUFFICIENT_DATA", [], [], {"reason": "Không có dữ liệu trong cửa sổ 5 phút"}

    # 1. Làm sạch: bỏ sensor_err=1, water_level is None, hoặc ngoài 0-100%
    clean = []
    sensor_err_count = 0
    for r in raw_samples:
        if r.get("sensor_err") == 1:
            sensor_err_count += 1
            continue
        wl = r.get("water_level")
        if wl is None or wl < 0.0 or wl > 100.0:
            continue
        clean.append(r)

    if len(clean) < 3:
        if sensor_err_count > 0:
            return "SENSOR_ERROR", [], [], {"reason": "Cảm biến báo lỗi liên tục"}
        return "INSUFFICIENT_DATA", [], [], {"reason": "Quá ít mẫu hợp lệ sau làm sạch"}

    # Sắp xếp theo recorded_at tăng dần, id tăng dần
    def get_rec_dt(row):
        t = row["recorded_at"]
        if isinstance(t, str):
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(t, fmt)
                except ValueError:
                    pass
            return datetime.now()
        return t

    clean.sort(key=lambda x: (get_rec_dt(x), x.get("id", 0)))

    # Loại bỏ trùng lặp thời gian nếu có (giữ bản ghi id lớn nhất)
    dedup = []
    for row in clean:
        r_dt = get_rec_dt(row)
        if dedup and get_rec_dt(dedup[-1]) == r_dt:
            if (row.get("id") or 0) >= (dedup[-1].get("id") or 0):
                dedup[-1] = row
        else:
            dedup.append(row)

    # 2. Cắt cửa sổ theo lần đổi trạng thái bơm gần nhất
    last_pump_change_dt = None
    prev_state = None
    for row in dedup:
        cur_state = (row.get("pump_in", 0), row.get("pump_out", 0))
        if prev_state is not None and cur_state != prev_state:
            last_pump_change_dt = get_rec_dt(row)
        prev_state = cur_state

    max_confidence = "HIGH"
    effective_samples = dedup
    if last_pump_change_dt is not None:
        # Bỏ 20 giây đầu ngay sau khi bơm đổi trạng thái
        settle_dt = last_pump_change_dt + timedelta(seconds=SETTLE_SECONDS)
        latest_dt = get_rec_dt(dedup[-1])
        rem_sec = (latest_dt - settle_dt).total_seconds()
        
        if rem_sec < MIN_COVERAGE_AFTER_PUMP_S:
            # Dưới 120s -> Trả STABILIZING, không dự báo
            return "STABILIZING", [], [], {
                "reason": "Bơm vừa đổi trạng thái, đang chờ xu hướng mới ổn định",
                "rem_seconds": rem_sec
            }
        
        # Chỉ giữ dữ liệu sau settle_dt
        effective_samples = [r for r in dedup if get_rec_dt(r) >= settle_dt]
        if rem_sec < MIN_COVERAGE_S:
            max_confidence = "MEDIUM"

    if len(effective_samples) < 3:
        return "INSUFFICIENT_DATA", [], [], {"reason": "Không đủ mẫu sau khi lọc thời gian bơm đổi"}

    # 3. Gộp mốc 10 giây bằng trung vị
    t_start = get_rec_dt(effective_samples[0])
    bins = {}
    for r in effective_samples:
        t_cur = get_rec_dt(r)
        offset_sec = (t_cur - t_start).total_seconds()
        bin_idx = int(offset_sec // BIN_SECONDS)
        if bin_idx not in bins:
            bins[bin_idx] = []
        bins[bin_idx].append((offset_sec, float(r["water_level"])))

    sorted_bin_indices = sorted(bins.keys())
    if len(sorted_bin_indices) < MIN_BINS:
        return "INSUFFICIENT_DATA", [], [], {
            "reason": f"Số mốc sau gộp ({len(sorted_bin_indices)}) không đạt tối thiểu {MIN_BINS}"
        }

    # Kiểm tra khoảng hở lớn nhất
    for i in range(1, len(sorted_bin_indices)):
        gap_sec = (sorted_bin_indices[i] - sorted_bin_indices[i - 1]) * BIN_SECONDS
        if gap_sec > MAX_GAP_S:
            return "INSUFFICIENT_DATA", [], [], {
                "reason": f"Khoảng hở dữ liệu ({gap_sec:.0f}s) vượt quá giới hạn {MAX_GAP_S}s"
            }

    # Tạo chuỗi ts (phút) và hs (%)
    binned_ts = []
    binned_hs = []
    for b_idx in sorted_bin_indices:
        pts = bins[b_idx]
        b_time_min = (b_idx * BIN_SECONDS + BIN_SECONDS / 2.0) / 60.0
        b_val = _median([p[1] for p in pts])
        binned_ts.append(b_time_min)
        binned_hs.append(b_val)

    # Kiểm tra độ phủ tổng
    cov_s = (binned_ts[-1] - binned_ts[0]) * 60.0
    req_cov = MIN_COVERAGE_AFTER_PUMP_S if last_pump_change_dt else MIN_COVERAGE_S
    if cov_s < req_cov:
        return "INSUFFICIENT_DATA", [], [], {
            "reason": f"Độ phủ dữ liệu ({cov_s:.0f}s) chưa đạt yêu cầu ({req_cov}s)"
        }

    extra = {
        "max_confidence": max_confidence,
        "bins_count": len(binned_ts),
        "coverage_s": cov_s,
        "last_sample_dt": get_rec_dt(effective_samples[-1]),
        "latest_raw_sample": effective_samples[-1]
    }
    return "OK", binned_ts, binned_hs, extra


# ── ĐỌC THAM SỐ CẤU HÌNH HỆ THỐNG ───────────────────────────────────────────
def get_system_limits():
    """Lấy limit_high, limit_low, d_empty, d_full từ system_config"""
    cfg_rows = db.execute("SELECT config_key, config_value FROM system_config", fetch="all") or []
    cfg = {r["config_key"]: r["config_value"] for r in cfg_rows}
    
    try:
        limit_high = float(cfg.get("limit_high", 97.0))
    except ValueError:
        limit_high = 97.0
    try:
        limit_low = float(cfg.get("limit_low", 0.0))
    except ValueError:
        limit_low = 0.0
    try:
        d_empty = float(cfg.get("d_empty", 18.0))
    except ValueError:
        d_empty = 18.0
    try:
        d_full = float(cfg.get("d_full", 5.0))
    except ValueError:
        d_full = 5.0

    return {
        "limit_high": limit_high,
        "limit_low": limit_low,
        "d_empty": d_empty,
        "d_full": d_full,
    }


# ── HÀM CHÍNH: XÂY DỰNG TOÀN BỘ INSIGHTS & FORECAST CHO DASHBOARD ────────────
def build_dashboard_insights(as_of=None, demo_mode=False):
    """
    Điểm vào chính sinh toàn bộ kết quả phân tích xu hướng và dự báo.
    as_of: datetime mốc thời gian (None -> lấy datetime.now())
    demo_mode: nếu True, lấy mốc as_of từ mẫu cuối trong DB để test/demo
    """
    now = datetime.now() if as_of is None else as_of
    limits = get_system_limits()
    
    # 1. Truy vấn mẫu dữ liệu gần nhất trong DB để kiểm tra độ mới
    latest_row = db.execute(
        "SELECT * FROM sensor_data ORDER BY recorded_at DESC, id DESC LIMIT 1",
        fetch="one"
    )

    if not latest_row:
        return _build_fallback_response(
            status="UNKNOWN",
            trend_state="INSUFFICIENT_DATA",
            title="Tình hình hiện tại: Chưa xác định (UNKNOWN)",
            desc="Hệ thống chưa có dữ liệu quan trắc nào trong cơ sở dữ liệu.",
            recom="Kiểm tra kết nối và cảm biến, chưa thể kết luận.",
            limits=limits,
            now=now
        )

    # Xử lý thời gian của bản ghi cuối
    rec_at = latest_row["recorded_at"]
    if isinstance(rec_at, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                rec_at = datetime.strptime(rec_at, fmt)
                break
            except ValueError:
                pass
        if isinstance(rec_at, str):
            rec_at = now

    if demo_mode:
        now = rec_at

    last_age_s = (now - rec_at).total_seconds()
    
    # Kiểm tra mất kết nối thiết bị nếu không ở chế độ demo và mẫu cũ > 15s
    is_device_offline = (not demo_mode) and (last_age_s > MAX_LAST_SAMPLE_AGE_S)

    # 2. Truy vấn dữ liệu trong cửa sổ 5 phút (WINDOW_SECONDS)
    since = now - timedelta(seconds=WINDOW_SECONDS)
    raw_samples = db.execute(
        """SELECT id, recorded_at, water_level, distance_cm, sensor_err, pump_in, pump_out, auto_mode, fault_code
           FROM sensor_data
           WHERE recorded_at >= %s AND recorded_at <= %s
           ORDER BY recorded_at ASC, id ASC""",
        (since, now + timedelta(seconds=2)),
        fetch="all"
    ) or []

    # Kiểm tra các cảnh báo chưa xử lý trong bảng alerts
    active_alerts = db.execute(
        """SELECT alert_code, severity, message FROM alerts
           WHERE status = 'UNRESOLVED'
           ORDER BY created_at DESC LIMIT 5""",
        fetch="all"
    ) or []

    has_danger_alert = any(a.get("severity") == "DANGER" for a in active_alerts)
    has_warning_alert = any(a.get("severity") == "WARNING" for a in active_alerts)

    # Xử lý trạng thái bơm hiện tại
    p_in = bool(latest_row.get("pump_in", 0))
    p_out = bool(latest_row.get("pump_out", 0))
    auto_mode = bool(latest_row.get("auto_mode", 1))
    fault_code = str(latest_row.get("fault_code", "none"))

    pumps_info = {
        "pump_in": p_in,
        "pump_out": p_out,
        "auto_mode": auto_mode
    }

    # Nếu thiết bị mất kết nối quá lâu
    if is_device_offline:
        return _build_fallback_response(
            status="UNKNOWN",
            trend_state="DEVICE_OFFLINE",
            title="Tình hình hiện tại: Mất kết nối (UNKNOWN)",
            desc=f"Thiết bị ESP32 không gửi dữ liệu trong {int(last_age_s)} giây qua. Không thể cập nhật xu hướng và dự báo.",
            recom="Kiểm tra nguồn điện trạm bờ ao và kết nối Wi-Fi/MQTT của ESP32.",
            limits=limits,
            now=now,
            data_as_of=rec_at,
            pumps=pumps_info,
            last_sample_age_s=int(last_age_s)
        )

    # 3. Chạy Pipeline lọc mẫu và gộp mốc
    step_code, b_ts, b_hs, extra = process_samples(raw_samples, now)

    if step_code != "OK":
        # STABILIZING, SENSOR_ERROR, hoặc INSUFFICIENT_DATA
        status_eval = "NORMAL"
        if has_danger_alert:
            status_eval = "DANGER"
        elif has_warning_alert or fault_code != "none":
            status_eval = "WARNING"
        elif step_code in ("SENSOR_ERROR", "INSUFFICIENT_DATA"):
            status_eval = "UNKNOWN"

        title = "Tình hình hiện tại: " + ("Đang chờ ổn định" if step_code == "STABILIZING" else ("Lỗi cảm biến" if step_code == "SENSOR_ERROR" else "Chưa xác định"))
        desc = extra.get("reason", "Chưa đủ dữ liệu để phân tích xu hướng.")
        recom = "Tiếp tục theo dõi, hệ thống sẽ tự cập nhật khi đủ dữ liệu." if step_code == "STABILIZING" else "Kiểm tra kết nối và cảm biến, chưa thể kết luận."

        return _build_fallback_response(
            status=status_eval,
            trend_state=step_code,
            title=f"{title} ({status_eval})",
            desc=desc,
            recom=recom,
            limits=limits,
            now=now,
            data_as_of=rec_at,
            pumps=pumps_info,
            last_sample_age_s=int(last_age_s)
        )

    # 4. Hồi quy tuyến tính
    fit = fit_line(b_ts, b_hs)
    if not fit:
        return _build_fallback_response(
            status="UNKNOWN",
            trend_state="INSUFFICIENT_DATA",
            title="Tình hình hiện tại: Chưa đủ dữ liệu (UNKNOWN)",
            desc="Không thể khớp đường hồi quy tuyến tính trên các mốc đo.",
            recom="Kiểm tra kết nối và cảm biến, chưa thể kết luận.",
            limits=limits,
            now=now,
            data_as_of=rec_at,
            pumps=pumps_info
        )

    v = fit["slope"]
    h0 = fit["h0"]
    s = fit["resid_std"]
    slope_se = fit["slope_se"]

    # Phân loại xu hướng
    abs_v = abs(v)
    if abs_v < STABLE_SLOPE_THRESHOLD or abs_v <= 2.0 * slope_se:
        direction = "STABLE"
        strength = "STABLE"
        trend_text = "tương đối ổn định"
    else:
        direction = "INCREASING" if v > 0 else "DECREASING"
        if abs_v < SLOW_SLOPE_THRESHOLD:
            strength = "SLOW"
            trend_text = "tăng nhẹ" if v > 0 else "giảm nhẹ"
        elif abs_v < MODERATE_SLOPE_THRESHOLD:
            strength = "MODERATE"
            trend_text = "tăng" if v > 0 else "giảm"
        else:
            strength = "FAST"
            trend_text = "tăng nhanh" if v > 0 else "giảm nhanh"

    # Tốc độ cm/phút
    d_range = limits["d_empty"] - limits["d_full"]
    slope_cm_per_min = round(v * d_range / 100.0, 2) if d_range != 0 else None

    # Đánh giá độ tin cậy
    confidence = "HIGH"
    if s > 1.0 or abs(h0 - _median(b_hs[-3:])) > 1.5:
        confidence = "LOW"
    elif extra.get("coverage_s", 0) < MIN_COVERAGE_S or extra.get("bins_count", 0) < 20 or s > 0.5:
        confidence = "MEDIUM"

    if extra.get("max_confidence") == "MEDIUM" and confidence == "HIGH":
        confidence = "MEDIUM"

    # 5. Tính toán dự báo cho 10, 20, 30 phút
    predictions = {}
    base_err_map = {10: 0.4, 20: 0.8, 30: 1.3}
    for t_min in (10, 20, 30):
        val = h0 + v * t_min
        # Ước lượng sai số ngoại suy theo cửa sổ và độ tin cậy
        base_err = base_err_map.get(t_min, 0.5)
        err = round(max(base_err, t_min * slope_se + 0.5 * s), 1)
        if val < 0.0 or val > 100.0:
            predictions[str(t_min)] = {
                "value": None,
                "state": "OUT_OF_RANGE",
                "error_margin": err,
                "reference_only": t_min >= 20
            }
        else:
            predictions[str(t_min)] = {
                "value": round(val, 1),
                "state": "OK",
                "error_margin": err,
                "reference_only": t_min >= 20
            }

    # 6. Tính ETA tới giới hạn cao (95%) và giới hạn thấp (5%)
    eta_high = _calc_eta(h0, limits["limit_high"], v, direction == "INCREASING")
    eta_low = _calc_eta(h0, limits["limit_low"], v, direction == "DECREASING")

    # 7. Nhận định và khuyến nghị theo 5 bậc ưu tiên
    sys_status = "NORMAL"
    recom_text = "Tiếp tục theo dõi, chưa cần can thiệp."

    # Ưu tiên 1: Cảnh báo DANGER trong bảng alerts
    if has_danger_alert:
        sys_status = "DANGER"
        recom_text = "Kiểm tra và xử lý sự cố nguy hiểm ngay."
    # Ưu tiên 2: Cảm biến hỏng hoặc mất kết nối
    elif extra.get("reason") and "cảm biến" in extra["reason"].lower():
        sys_status = "UNKNOWN"
        recom_text = "Kiểm tra kết nối và cảm biến, chưa thể kết luận."
    # Ưu tiên 3: Mực nước chạm hoặc vượt giới hạn
    elif h0 >= limits["limit_high"] or h0 <= limits["limit_low"]:
        sys_status = "DANGER"
        recom_text = "Kiểm tra và xử lý kịp thời để tránh tràn hoặc cạn ao."
    # Ưu tiên 4: Cảnh báo WARNING hoặc lỗi bơm hoặc ETA ngắn <= 30 phút
    elif (has_warning_alert or 
          fault_code != "none" or 
          eta_high.get("state") == "MINUTES" or 
          eta_low.get("state") == "MINUTES" or 
          (limits["limit_high"] - h0 < 5.0 and direction == "INCREASING") or 
          (h0 - limits["limit_low"] < 5.0 and direction == "DECREASING")):
        sys_status = "WARNING"
        if direction == "DECREASING":
            recom_text = "Theo dõi xu hướng giảm; nếu tiếp diễn, kiểm tra nguồn cấp và hoạt động của bơm."
        elif direction == "INCREASING":
            recom_text = "Theo dõi xu hướng tăng và kiểm tra bơm thoát nếu mực nước tiếp tục cao."
        else:
            recom_text = "Kiểm tra trạng thái bơm và nguồn nước."
    else:
        sys_status = "NORMAL"
        recom_text = "Tiếp tục theo dõi, chưa cần can thiệp."

    # Xây dựng câu mô tả trạng thái (Description)
    pumps_desc = "Hai máy bơm đang tắt"
    if p_in and p_out:
        pumps_desc = "Cả hai máy bơm đang bật đồng thời"
    elif p_in:
        pumps_desc = "Máy bơm cấp nước (IN) đang bật"
    elif p_out:
        pumps_desc = "Máy bơm thoát nước (OUT) đang bật"

    cm_str = f" (≈ {abs(slope_cm_per_min):.2f} cm/phút)" if slope_cm_per_min is not None else ""
    rate_str = f" với tốc độ khoảng {v:+.2f}%/phút{cm_str}" if direction != "STABLE" else ""

    auto_note = " (nếu không có can thiệp của chế độ AUTO)" if (auto_mode and (eta_high["state"] == "MINUTES" or eta_low["state"] == "MINUTES")) else ""

    desc_text = (
        f"Mực nước hiện tại là {h0:.1f} %, có xu hướng {trend_text}{rate_str}. "
        f"{pumps_desc}, thiết bị ESP32 kết nối bình thường và chưa ghi nhận lỗi{auto_note}."
    )

    status_titles = {
        "NORMAL": "Tình hình hiện tại: Bình thường (NORMAL)",
        "WARNING": "Tình hình hiện tại: Cần lưu ý (WARNING)",
        "DANGER": "Tình hình hiện tại: Nguy hiểm (DANGER)",
        "UNKNOWN": "Tình hình hiện tại: Chưa xác định (UNKNOWN)"
    }

    return {
        "ok": True,
        "status": sys_status,
        "data_quality": {
            "level": "GOOD" if confidence == "HIGH" else ("DEGRADED" if confidence == "MEDIUM" else "POOR"),
            "reasons": [],
            "window_seconds_used": WINDOW_SECONDS,
            "bins": extra.get("bins_count", len(b_ts)),
            "last_sample_age_s": int(last_age_s)
        },
        "current_level_pct": round(h0, 1),
        "trend": {
            "state": "OK",
            "direction": direction,
            "strength": strength,
            "slope_pct_per_min": round(v, 2),
            "slope_cm_per_min": slope_cm_per_min,
            "confidence": confidence,
            "text": trend_text
        },
        "prediction": predictions,
        "eta": {
            "high": eta_high,
            "low": eta_low
        },
        "pumps": pumps_info,
        "insight": {
            "title": status_titles.get(sys_status, "Tình hình ao nuôi"),
            "description": desc_text,
            "recommendation": recom_text
        },
        "data_as_of": rec_at.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%S+07:00")
    }


def _calc_eta(h0, limit, slope, is_moving_towards):
    """Tính toán thời gian dự kiến (ETA) tới một ngưỡng giới hạn"""
    if not is_moving_towards or slope == 0:
        return {
            "minutes": None,
            "state": "NOT_EXPECTED",
            "formatted": "An toàn (> 24 giờ)",
            "limit": limit
        }
    
    diff = limit - h0 if slope > 0 else h0 - limit
    if diff <= 0:
        return {
            "minutes": 0,
            "state": "REACHED",
            "formatted": f"Đã chạm ngưỡng ({limit} %)",
            "limit": limit
        }
    
    eta_min = diff / abs(slope)
    
    if eta_min <= 30.0:
        mins = int(round(eta_min))
        return {
            "minutes": mins,
            "state": "MINUTES",
            "formatted": f"Khoảng {mins} phút nữa",
            "limit": limit
        }
    elif eta_min <= 1440.0:
        # Trong vòng 24 giờ
        hours = int(eta_min // 60)
        mins = int(round(eta_min % 60))
        time_str = f"≈ {hours} giờ {mins} phút nữa" if mins > 0 else f"≈ {hours} giờ nữa"
        return {
            "minutes": int(round(eta_min)),
            "state": "BEYOND_HORIZON",
            "formatted": time_str,
            "limit": limit
        }
    else:
        return {
            "minutes": int(round(eta_min)),
            "state": "BEYOND_HORIZON",
            "formatted": "An toàn (> 24 giờ)",
            "limit": limit
        }


def _build_fallback_response(status, trend_state, title, desc, recom, limits, now, data_as_of=None, pumps=None, last_sample_age_s=0):
    """Tạo response chuẩn khi dữ liệu không đủ hoặc gặp lỗi"""
    return {
        "ok": True,
        "status": status,
        "data_quality": {
            "level": "POOR",
            "reasons": [desc],
            "window_seconds_used": WINDOW_SECONDS,
            "bins": 0,
            "last_sample_age_s": last_sample_age_s
        },
        "current_level_pct": None,
        "trend": {
            "state": trend_state,
            "direction": "UNKNOWN",
            "strength": "UNKNOWN",
            "slope_pct_per_min": 0.0,
            "slope_cm_per_min": None,
            "confidence": "LOW",
            "text": "chưa xác định"
        },
        "prediction": {
            "10": {"value": None, "state": "UNAVAILABLE", "error_margin": 0.0, "reference_only": False},
            "20": {"value": None, "state": "UNAVAILABLE", "error_margin": 0.0, "reference_only": True},
            "30": {"value": None, "state": "UNAVAILABLE", "error_margin": 0.0, "reference_only": True}
        },
        "eta": {
            "high": {"minutes": None, "state": "UNAVAILABLE", "formatted": "Đang theo dõi", "limit": limits.get("limit_high", 97)},
            "low": {"minutes": None, "state": "UNAVAILABLE", "formatted": "Đang theo dõi", "limit": limits.get("limit_low", 0)}
        },
        "pumps": pumps or {"pump_in": False, "pump_out": False, "auto_mode": True},
        "insight": {
            "title": title,
            "description": desc,
            "recommendation": recom
        },
        "data_as_of": (data_as_of or now).strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%S+07:00")
    }
