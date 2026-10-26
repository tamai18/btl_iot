-- ============================================================================
--  DATABASE: iot_ao_nuoi
--  Hệ thống giám sát và điều khiển mực nước ao nuôi
--  ESP32 + HC-SR04 + Relay 2 kênh + MQTT (Mosquitto) + Flask
-- ============================================================================

CREATE DATABASE IF NOT EXISTS iot_ao_nuoi
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE iot_ao_nuoi;

-- ============================================================================
-- Bảng 1: sensor_data
-- Lưu dữ liệu cảm biến từ ESP32 (mực nước, khoảng cách, trạng thái bơm)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensor_data (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    recorded_at DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    -- Dữ liệu cảm biến HC-SR04
    water_level FLOAT           NOT NULL COMMENT 'Mực nước (%) 0..100',
    distance_cm FLOAT           NOT NULL COMMENT 'Khoảng cách cảm biến đến mặt nước (cm)',

    -- Trạng thái hai bơm (0=Tắt, 1=Bật)
    pump_in     TINYINT(1)      NOT NULL DEFAULT 0 COMMENT 'Bơm cấp nước (IN)',
    pump_out    TINYINT(1)      NOT NULL DEFAULT 0 COMMENT 'Bơm thoát nước (OUT)',

    -- Chế độ hoạt động
    auto_mode   TINYINT(1)      NOT NULL DEFAULT 1 COMMENT '1=AUTO, 0=MANUAL',

    -- Trạng thái thiết bị
    sensor_err  TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '1=Lỗi cảm biến',
    fault_code  VARCHAR(32)     NOT NULL DEFAULT 'none' COMMENT 'Mã lỗi chốt',
    rssi        SMALLINT        NOT NULL DEFAULT 0 COMMENT 'Cường độ WiFi (dBm)',
    uptime_sec  INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT 'Thời gian hoạt động (giây)',

    -- Metadata
    esp32_id    VARCHAR(32)     NULL COMMENT 'ID thiết bị ESP32',
    topic       VARCHAR(128)    NULL COMMENT 'MQTT topic nguồn',

    PRIMARY KEY (id),
    INDEX idx_recorded_at (recorded_at),
    INDEX idx_water_level (water_level),
    INDEX idx_pump_status (pump_in, pump_out),
    INDEX idx_esp32_time  (esp32_id, recorded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Dữ liệu cảm biến mực nước ao nuôi từ ESP32';


-- ============================================================================
-- Bảng 2: alerts
-- Lưu mã cảnh báo, nội dung, mức độ và trạng thái xử lý
-- ============================================================================
CREATE TABLE IF NOT EXISTS alerts (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

    alert_code  VARCHAR(32)     NOT NULL COMMENT 'Mã cảnh báo (HIGH, SENSOR, PUMP_IN_OFF...)',
    message     VARCHAR(255)    NOT NULL COMMENT 'Nội dung cảnh báo',
    severity    ENUM('INFO','WARNING','DANGER') NOT NULL DEFAULT 'INFO' COMMENT 'Mức độ',

    water_level FLOAT           NULL COMMENT 'Mực nước lúc cảnh báo (%)',
    value_str   VARCHAR(64)     NULL COMMENT 'Giá trị bổ sung',

    status      ENUM('PENDING','RESOLVED') NOT NULL DEFAULT 'PENDING',
    resolved_at DATETIME(3)     NULL,
    resolved_by VARCHAR(64)     NULL,
    note        TEXT            NULL,

    esp32_id    VARCHAR(32)     NULL,
    source_topic VARCHAR(128)   NULL,

    PRIMARY KEY (id),
    INDEX idx_created_at  (created_at),
    INDEX idx_severity    (severity),
    INDEX idx_status      (status),
    INDEX idx_alert_code  (alert_code),
    INDEX idx_sev_status  (severity, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Cảnh báo và sự kiện quan trọng từ hệ thống ao nuôi';


-- ============================================================================
-- Bảng 3: control_logs
-- Lưu các lệnh điều khiển gửi đến ESP32 và phản hồi ACK
-- ============================================================================
CREATE TABLE IF NOT EXISTS control_logs (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sent_at     DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    acked_at    DATETIME(3)     NULL,

    command     VARCHAR(32)     NOT NULL COMMENT 'Tên lệnh (mode, pump_in, pump_out, threshold...)',
    payload     VARCHAR(255)    NOT NULL COMMENT 'Nội dung lệnh',
    topic       VARCHAR(128)    NOT NULL COMMENT 'MQTT topic lệnh',

    ack_payload VARCHAR(255)    NULL COMMENT 'Nội dung ACK từ ESP32',
    status      ENUM('SENT','ACK_OK','ACK_ERR','TIMEOUT') NOT NULL DEFAULT 'SENT',

    initiated_by VARCHAR(64)   NOT NULL DEFAULT 'web',
    client_ip    VARCHAR(45)    NULL,
    esp32_id     VARCHAR(32)    NULL,

    PRIMARY KEY (id),
    INDEX idx_sent_at   (sent_at),
    INDEX idx_command   (command),
    INDEX idx_status    (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Nhật ký lệnh điều khiển gửi đến ESP32 và phản hồi';


-- ============================================================================
-- Bảng 4: system_logs
-- Lưu nhật ký kết nối, khởi động, lỗi và các sự kiện hệ thống
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_logs (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    logged_at   DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    log_level   ENUM('DEBUG','INFO','WARNING','ERROR','CRITICAL') NOT NULL DEFAULT 'INFO',
    component   VARCHAR(32)     NOT NULL COMMENT 'esp32/mqtt/flask/database',
    event_type  VARCHAR(64)     NOT NULL COMMENT 'connected/disconnected/restart/error...',

    message     TEXT            NOT NULL,
    details     JSON            NULL,

    esp32_id    VARCHAR(32)     NULL,
    ip_address  VARCHAR(45)     NULL,

    PRIMARY KEY (id),
    INDEX idx_logged_at   (logged_at),
    INDEX idx_log_level   (log_level),
    INDEX idx_component   (component),
    INDEX idx_comp_time   (component, logged_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Nhật ký hệ thống – kết nối, khởi động, sự kiện';


-- ============================================================================
-- Bảng 5: system_config
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_config (
    config_key   VARCHAR(64)    NOT NULL,
    config_value VARCHAR(255)   NOT NULL,
    description  VARCHAR(255)   NULL,
    updated_at   DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Cấu hình hệ thống lưu trong database';

INSERT INTO system_config (config_key, config_value, description) VALUES
('d_empty',        '100',             'Khoảng cách cảm biến khi ao cạn (cm)'),
('d_full',         '10',              'Khoảng cách cảm biến khi ao đầy (cm)'),
('in_on_pct',      '30',              'Ngưỡng bật bơm cấp (%)'),
('in_off_pct',     '50',              'Ngưỡng tắt bơm cấp (%)'),
('out_on_pct',     '90',              'Ngưỡng bật bơm thoát (%)'),
('out_off_pct',    '80',              'Ngưỡng tắt bơm thoát (%)'),
('limit_high',     '95',              'Ngưỡng cảnh báo cao (%)'),
('limit_low',      '5',               'Ngưỡng cảnh báo thấp (%)'),
('max_run_min',    '20',              'Thời gian chạy bơm tối đa (phút)'),
('publish_sec',    '2',               'Chu kỳ gửi dữ liệu MQTT (giây)'),
('mqtt_broker',    '192.168.1.100',   'IP MQTT Broker'),
('mqtt_port',      '1883',            'Cổng MQTT'),
('topic_prefix',   'iot-ao-demo-123', 'Tiền tố topic MQTT'),
('alert_buzzer',   '1',               'Bật còi cảnh báo'),
('alert_led',      '1',               'Bật đèn LED cảnh báo'),
('web_version',    '1.0.0',           'Phiên bản phần mềm web'),
('language',       'vi',              'Ngôn ngữ giao diện')
ON DUPLICATE KEY UPDATE config_value = VALUES(config_value);
