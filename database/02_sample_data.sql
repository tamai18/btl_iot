-- ============================================================================
--  DỮ LIỆU MẪU - iot_ao_nuoi
--  Dùng để kiểm thử khi chưa có phần cứng ESP32
-- ============================================================================
USE iot_ao_nuoi;

-- ============================================================================
-- Dữ liệu mẫu: sensor_data (7 ngày gần đây, mỗi 2 phút)
-- ============================================================================
INSERT INTO sensor_data (recorded_at, water_level, distance_cm, pump_in, pump_out, auto_mode, sensor_err, fault_code, rssi, uptime_sec, esp32_id) VALUES
(NOW() - INTERVAL 30 MINUTE, 36.7, 65.0, 0, 0, 1, 0, 'none', -55, 3600, 'esp32-ao-demo'),
(NOW() - INTERVAL 28 MINUTE, 37.9, 63.8, 0, 0, 1, 0, 'none', -54, 3720, 'esp32-ao-demo'),
(NOW() - INTERVAL 26 MINUTE, 38.2, 63.4, 0, 0, 1, 0, 'none', -55, 3840, 'esp32-ao-demo'),
(NOW() - INTERVAL 24 MINUTE, 39.5, 62.0, 1, 0, 1, 0, 'none', -56, 3960, 'esp32-ao-demo'),
(NOW() - INTERVAL 22 MINUTE, 40.8, 60.9, 1, 0, 1, 0, 'none', -55, 4080, 'esp32-ao-demo'),
(NOW() - INTERVAL 20 MINUTE, 41.2, 60.5, 1, 0, 1, 0, 'none', -54, 4200, 'esp32-ao-demo'),
(NOW() - INTERVAL 18 MINUTE, 42.6, 59.3, 1, 0, 1, 0, 'none', -55, 4320, 'esp32-ao-demo'),
(NOW() - INTERVAL 16 MINUTE, 43.9, 58.0, 0, 0, 1, 0, 'none', -53, 4440, 'esp32-ao-demo'),
(NOW() - INTERVAL 14 MINUTE, 44.8, 57.1, 0, 0, 1, 0, 'none', -55, 4560, 'esp32-ao-demo'),
(NOW() - INTERVAL 12 MINUTE, 45.5, 56.7, 0, 0, 1, 0, 'none', -55, 4680, 'esp32-ao-demo'),
(NOW() - INTERVAL 10 MINUTE, 46.1, 56.2, 0, 0, 1, 0, 'none', -54, 4800, 'esp32-ao-demo'),
(NOW() - INTERVAL  8 MINUTE, 46.8, 55.8, 0, 0, 1, 0, 'none', -55, 4920, 'esp32-ao-demo'),
(NOW() - INTERVAL  6 MINUTE, 47.2, 55.5, 0, 0, 1, 0, 'none', -53, 5040, 'esp32-ao-demo'),
(NOW() - INTERVAL  4 MINUTE, 47.5, 55.2, 0, 0, 1, 0, 'none', -55, 5160, 'esp32-ao-demo'),
(NOW() - INTERVAL  2 MINUTE, 45.5, 56.7, 0, 0, 1, 0, 'none', -55, 5280, 'esp32-ao-demo');

-- Dữ liệu ngày hôm qua
INSERT INTO sensor_data (recorded_at, water_level, distance_cm, pump_in, pump_out, auto_mode, sensor_err, fault_code, rssi, uptime_sec, esp32_id)
SELECT 
    DATE_SUB(recorded_at, INTERVAL 1 DAY),
    water_level + (RAND() * 10 - 5),
    distance_cm + (RAND() * 5 - 2.5),
    pump_in, pump_out, auto_mode, sensor_err, fault_code,
    rssi - ROUND(RAND() * 5),
    uptime_sec + 86400,
    esp32_id
FROM sensor_data;

-- ============================================================================
-- Dữ liệu mẫu: alerts
-- ============================================================================
INSERT INTO alerts (created_at, alert_code, message, severity, water_level, value_str, status, resolved_at, resolved_by) VALUES
(NOW() - INTERVAL 5 MINUTE,  'HIGH_LEVEL',   'Mực nước đạt 92% (nguy cơ tràn ao)', 'DANGER',  92.0, '92 %',   'UNRESOLVED',  NULL, NULL),
(NOW() - INTERVAL 25 MINUTE, 'PUMP_IN_OFF',  'Máy bơm cấp đã tắt',                 'WARNING', 50.5, NULL,     'RESOLVED', NOW() - INTERVAL 20 MINUTE, 'system'),
(NOW() - INTERVAL 45 MINUTE, 'MODE',         'Chế độ MANUAL được kích hoạt',        'INFO',    43.2, NULL,     'RESOLVED', NOW() - INTERVAL 40 MINUTE, 'system'),
(NOW() - INTERVAL 2 HOUR,    'HIGH_TREND',   'Mực nước tăng nhanh',                 'WARNING', 65.0, '+5.2 %/h','RESOLVED', NOW() - INTERVAL 90 MINUTE, 'system'),
(NOW() - INTERVAL 6 HOUR,    'SENSOR',       'Cảm biến đo không ổn định',           'WARNING', 40.0, NULL,     'RESOLVED', NOW() - INTERVAL 5 HOUR, 'user'),
(NOW() - INTERVAL 8 HOUR,    'PUMP_IN',      'Máy bơm cấp đã bật',                 'INFO',    28.5, NULL,     'RESOLVED', NOW() - INTERVAL 7 HOUR, 'system'),
(NOW() - INTERVAL 12 HOUR,   'LOW_LEVEL',    'Mực nước thấp, nguy cơ cạn ao',       'DANGER',  4.5,  '4.5 %',  'RESOLVED', NOW() - INTERVAL 11 HOUR, 'system'),
(NOW() - INTERVAL 1 DAY,     'PUMP_OVERRUN', 'Bơm chạy quá 20 phút liên tục',      'DANGER',  78.0, '22 phút','RESOLVED', NOW() - INTERVAL 23 HOUR, 'user');

-- ============================================================================
-- Dữ liệu mẫu: control_logs
-- ============================================================================
INSERT INTO control_logs (sent_at, acked_at, command, payload, topic, ack_payload, status, initiated_by, client_ip, esp32_id) VALUES
(NOW() - INTERVAL 30 MINUTE, NOW() - INTERVAL 30 MINUTE + INTERVAL 1 SECOND, 'mode',      'AUTO',        'iot-ao-demo-123/cmd/mode',      'ok:mode=AUTO',    'ACK_OK', 'web', '192.168.1.5', 'esp32-ao-demo'),
(NOW() - INTERVAL 45 MINUTE, NOW() - INTERVAL 45 MINUTE + INTERVAL 1 SECOND, 'mode',      'MANUAL',      'iot-ao-demo-123/cmd/mode',      'ok:mode=MANUAL',  'ACK_OK', 'web', '192.168.1.5', 'esp32-ao-demo'),
(NOW() - INTERVAL 46 MINUTE, NOW() - INTERVAL 46 MINUTE + INTERVAL 1 SECOND, 'pump_in',   'ON',          'iot-ao-demo-123/cmd/pump_in',   'ok:pump=ON',      'ACK_OK', 'web', '192.168.1.5', 'esp32-ao-demo'),
(NOW() - INTERVAL 1 HOUR,    NOW() - INTERVAL 1 HOUR + INTERVAL 1 SECOND,    'threshold', '30,50,90,80', 'iot-ao-demo-123/cmd/threshold', 'ok:threshold',    'ACK_OK', 'web', '192.168.1.5', 'esp32-ao-demo'),
(NOW() - INTERVAL 2 HOUR,    NULL,                                             'pump_out',  'ON',          'iot-ao-demo-123/cmd/pump_out',  NULL,              'TIMEOUT','web', '192.168.1.5', 'esp32-ao-demo'),
(NOW() - INTERVAL 3 HOUR,    NOW() - INTERVAL 3 HOUR + INTERVAL 2 SECOND,    'calib',     '100,10',      'iot-ao-demo-123/cmd/calib',     'ok:calib',        'ACK_OK', 'web', '192.168.1.5', 'esp32-ao-demo');

-- ============================================================================
-- Dữ liệu mẫu: system_logs
-- ============================================================================
INSERT INTO system_logs (logged_at, log_level, component, event_type, message, esp32_id, ip_address) VALUES
(NOW() - INTERVAL 2 MINUTE,  'INFO',    'mqtt',     'data_received',  'Nhận dữ liệu từ ESP32: level=45.5%',                   'esp32-ao-demo', NULL),
(NOW() - INTERVAL 4 MINUTE,  'INFO',    'mqtt',     'keepalive',      'MQTT keep alive – esp32-ao-demo',                      'esp32-ao-demo', NULL),
(NOW() - INTERVAL 41 MINUTE, 'INFO',    'flask',    'cmd_sent',       'Gửi lệnh bật bơm cấp',                                 'esp32-ao-demo', '192.168.1.5'),
(NOW() - INTERVAL 39 MINUTE, 'INFO',    'mqtt',     'ack_received',   'Nhận ACK: bơm cấp ON',                                 'esp32-ao-demo', NULL),
(NOW() - INTERVAL 34 MINUTE, 'WARNING', 'flask',    'alert_triggered','Cảnh báo: mực nước 92%',                               'esp32-ao-demo', NULL),
(NOW() - INTERVAL 30 MINUTE, 'INFO',    'mqtt',     'connected',      'Kết nối MQTT thành công',                              'esp32-ao-demo', '192.168.1.100'),
(NOW() - INTERVAL 2 HOUR,    'ERROR',   'mqtt',     'disconnected',   'Mất kết nối MQTT – thử kết nối lại',                  'esp32-ao-demo', NULL),
(NOW() - INTERVAL 2 HOUR + INTERVAL 10 SECOND, 'INFO', 'mqtt', 'reconnected', 'Kết nối lại MQTT thành công',                'esp32-ao-demo', '192.168.1.100'),
(NOW() - INTERVAL 3 HOUR,    'INFO',    'database', 'cleanup',        'Dọn dẹp dữ liệu cũ hơn 30 ngày: xóa 120 bản ghi',    NULL, NULL),
(NOW() - INTERVAL 1 DAY,     'INFO',    'flask',    'startup',        'Khởi động Flask backend v1.0.0',                       NULL, NULL);
