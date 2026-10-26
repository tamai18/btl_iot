-- ============================================================================
-- DỮ LIỆU TEST PAGE 2 - TỪ 26/10/2026 ĐẾN 30/10/2026
-- ============================================================================
-- Chạy sau 01_create_database.sql.
-- File có thể chạy lại: dữ liệu test cũ của thiết bị esp32-page2-test sẽ được
-- xóa trước khi chèn lại.
--
-- Lưu ý: page 2 lọc thống kê theo thời gian thực (NOW()). Các bản ghi từ
-- 27/10 trở đi là dữ liệu tương lai để kiểm tra biểu đồ theo ngày; chúng sẽ
-- xuất hiện trong biểu đồ 7 ngày/30 ngày nhưng không được tính vào thống kê
-- realtime cho tới khi đồng hồ hệ thống tới thời điểm tương ứng.
-- ============================================================================

USE iot_ao_nuoi;

DELETE FROM sensor_data
WHERE esp32_id = 'esp32-page2-test'
  AND recorded_at >= '2026-10-26 00:00:00'
  AND recorded_at <  '2026-10-31 00:00:00';

-- 48 điểm/ngày, cách nhau 30 phút. Mực nước dao động theo chu kỳ và có
-- các khoảng bật bơm để timeline page 2 có cả trạng thái ON/OFF.
INSERT INTO sensor_data (
    recorded_at, water_level, distance_cm, pump_in, pump_out, auto_mode,
    sensor_err, fault_code, rssi, uptime_sec, esp32_id, topic
)
WITH RECURSIVE points AS (
    SELECT 0 AS n
    UNION ALL
    SELECT n + 1
    FROM points
    WHERE n < 239
)
SELECT
    TIMESTAMP('2026-10-26 00:00:00') + INTERVAL (n * 30) MINUTE AS recorded_at,
    ROUND(
        GREATEST(
            5,
            LEAST(
                95,
                48
                + 12 * SIN((n MOD 48) / 48 * 2 * PI())
                + 4 * SIN(n / 7)
                + CASE
                    WHEN (n MOD 48) BETWEEN 8 AND 13 THEN (n MOD 48) - 7
                    WHEN (n MOD 48) BETWEEN 30 AND 35 THEN 35 - (n MOD 48)
                    ELSE 0
                  END
            )
        ),
        1
    ) AS water_level,
    ROUND(
        100 - (
            48
            + 12 * SIN((n MOD 48) / 48 * 2 * PI())
            + 4 * SIN(n / 7)
        ) * 0.9,
        1
    ) AS distance_cm,
    CASE WHEN (n MOD 48) BETWEEN 8 AND 13 THEN 1 ELSE 0 END AS pump_in,
    CASE WHEN (n MOD 48) BETWEEN 30 AND 35 THEN 1 ELSE 0 END AS pump_out,
    CASE WHEN (n MOD 24) < 18 THEN 1 ELSE 0 END AS auto_mode,
    0 AS sensor_err,
    'none' AS fault_code,
    -55 - (n MOD 6) AS rssi,
    3600 + n * 1800 AS uptime_sec,
    'esp32-page2-test' AS esp32_id,
    'iot-ao-demo-123/data' AS topic
FROM points;

-- Kiểm tra nhanh số lượng dữ liệu theo ngày:
SELECT DATE(recorded_at) AS test_date, COUNT(*) AS records
FROM sensor_data
WHERE esp32_id = 'esp32-page2-test'
GROUP BY DATE(recorded_at)
ORDER BY test_date;