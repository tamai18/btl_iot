-- ============================================================================
--  notification_tables.sql
--  Bảng dữ liệu cho Hệ thống Cảnh báo Nguy hiểm và Gửi Email Tự động
-- ============================================================================

CREATE TABLE IF NOT EXISTS notification_recipients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100) DEFAULT 'Người nuôi cá',
    enabled TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS incidents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_key VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL, -- DANGER, WARNING, INFO
    device_id VARCHAR(50) DEFAULT 'esp32-ao-01',
    status VARCHAR(20) DEFAULT 'ACTIVE', -- ACTIVE, RECOVERED
    water_level_at_detect DOUBLE NULL,
    pump_in_at_detect INT DEFAULT 0,
    pump_out_at_detect INT DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recovered_at TIMESTAMP NULL,
    last_notified_at TIMESTAMP NULL,
    remind_count INT DEFAULT 0,
    source VARCHAR(50) DEFAULT 'backend_rule', -- esp32, backend_rule, watchdog
    notes TEXT NULL,
    INDEX idx_incident_lookup (event_key, device_id, status),
    INDEX idx_incident_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notification_outbox (
    id INT AUTO_INCREMENT PRIMARY KEY,
    incident_id INT NULL,
    recipient_id INT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body_html MEDIUMTEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, SENT, FAILED
    scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP NULL,
    attempt_count INT DEFAULT 0,
    last_error TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_outbox_queue (status, scheduled_at),
    INDEX idx_outbox_sent (sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Mặc định thêm 1 người nhận mẫu nếu chưa có
INSERT IGNORE INTO notification_recipients (email, name, enabled)
VALUES ('nguoinuoi@example.com', 'Chủ ao nuôi cá', 1);

-- Thêm cấu hình gửi mail vào system_config nếu chưa có
INSERT IGNORE INTO system_config (config_key, config_value, description)
VALUES 
    ('mail_enabled', '1', 'Bật/tắt gửi email cảnh báo tự động'),
    ('mail_recipient_default', 'nguoinuoi@example.com', 'Email nhận cảnh báo chính');

