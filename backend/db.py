# ============================================================================
#  db.py – Quản lý kết nối Database (Hỗ trợ kép MySQL 8.x + Tự động Fallback SQLite)
# ============================================================================
import os, sys, logging, sqlite3, re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)

_db_type = None  # 'mysql' hoặc 'sqlite'
_pool = None
_sqlite_path = os.path.join(os.path.dirname(__file__), "data.db")

def init_db():
    global _db_type, _pool
    db_pref = os.getenv("DB_TYPE", "mysql").lower()

    if db_pref == "mysql":
        try:
            import mysql.connector
            from mysql.connector import pooling
            _pool = pooling.MySQLConnectionPool(
                pool_name="ao_pool",
                pool_size=5,
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 3306)),
                database=os.getenv("DB_NAME", "iot_ao_nuoi"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASS", ""),
                charset="utf8mb4",
                autocommit=True,
                connection_timeout=5,
            )
            # Test connection
            test_conn = _pool.get_connection()
            test_conn.close()
            _db_type = "mysql"
            _migrate_alert_status()
            logger.info(">>> [DB] Kết nối thành công MySQL 8.x database: %s", os.getenv("DB_NAME", "iot_ao_nuoi"))
            return
        except Exception as e:
            logger.warning(">>> [DB] Không thể kết nối MySQL (%s). Tự động chuyển sang chế độ SQLite (data.db)...", e)

    # Chuyển sang SQLite fallback
    _db_type = "sqlite"
    _setup_sqlite_schema()
    _migrate_alert_status()
    logger.info(">>> [DB] Đang hoạt động ở chế độ SQLite @ (%s)", _sqlite_path)

def _migrate_alert_status():
    """Chuẩn hóa trạng thái cảnh báo và hỗ trợ dữ liệu cũ dùng PENDING."""
    if _db_type == "mysql":
        conn = _pool.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "ALTER TABLE alerts MODIFY status "
                "ENUM('PENDING','UNRESOLVED','RESOLVED') NOT NULL DEFAULT 'UNRESOLVED'"
            )
            conn.commit()
        except Exception as e:
            logger.warning("[DB] Không thể cập nhật ENUM alerts.status: %s", e)
        finally:
            conn.close()
        execute("UPDATE alerts SET status='UNRESOLVED' WHERE status='PENDING'")
        conn = _pool.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "ALTER TABLE alerts MODIFY status "
                "ENUM('UNRESOLVED','RESOLVED') NOT NULL DEFAULT 'UNRESOLVED'"
            )
            conn.commit()
        except Exception as e:
            logger.warning("[DB] Không thể loại bỏ trạng thái PENDING: %s", e)
        finally:
            conn.close()
    else:
        execute("UPDATE alerts SET status='UNRESOLVED' WHERE status='PENDING'")

def get_db_info():
    if _db_type is None:
        init_db()
    if _db_type == "mysql":
        return f"MySQL 8.x ({os.getenv('DB_NAME', 'iot_ao_nuoi')})"
    return "SQLite @ (data.db)"

def _setup_sqlite_schema():
    conn = sqlite3.connect(_sqlite_path)
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS sensor_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        water_level REAL NOT NULL,
        distance_cm REAL NOT NULL,
        pump_in INTEGER DEFAULT 0,
        pump_out INTEGER DEFAULT 0,
        auto_mode INTEGER DEFAULT 1,
        sensor_err INTEGER DEFAULT 0,
        fault_code TEXT DEFAULT 'none',
        rssi INTEGER DEFAULT 0,
        uptime_sec INTEGER DEFAULT 0,
        esp32_id TEXT,
        topic TEXT
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        alert_code TEXT NOT NULL,
        message TEXT NOT NULL,
        severity TEXT DEFAULT 'INFO',
        water_level REAL,
        value_str TEXT,
        status TEXT DEFAULT 'UNRESOLVED',
        resolved_at TIMESTAMP,
        resolved_by TEXT,
        note TEXT,
        esp32_id TEXT,
        source_topic TEXT
    );

    CREATE TABLE IF NOT EXISTS control_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        acked_at TIMESTAMP,
        command TEXT NOT NULL,
        payload TEXT NOT NULL,
        topic TEXT NOT NULL,
        ack_payload TEXT,
        status TEXT DEFAULT 'SENT',
        initiated_by TEXT DEFAULT 'web',
        client_ip TEXT,
        esp32_id TEXT
    );

    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        log_level TEXT DEFAULT 'INFO',
        component TEXT NOT NULL,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        details TEXT,
        esp32_id TEXT,
        ip_address TEXT
    );

    CREATE TABLE IF NOT EXISTS system_config (
        config_key TEXT PRIMARY KEY,
        config_value TEXT NOT NULL,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Seed default config
    configs = [
        ('d_empty', '100', 'Khoảng cách khi cạn (cm)'),
        ('d_full', '10', 'Khoảng cách khi đầy (cm)'),
        ('in_on_pct', '30', 'Ngưỡng bật bơm IN (%)'),
        ('in_off_pct', '50', 'Ngưỡng tắt bơm IN (%)'),
        ('out_on_pct', '90', 'Ngưỡng bật bơm OUT (%)'),
        ('out_off_pct', '80', 'Ngưỡng tắt bơm OUT (%)'),
        ('limit_high', '95', 'Ngưỡng cảnh báo cao (%)'),
        ('limit_low', '5', 'Ngưỡng cảnh báo thấp (%)'),
        ('max_run_min', '20', 'Thời gian bơm chạy tối đa (phút)'),
        ('switch_delay_sec', '3', 'Nghỉ giữa 2 bơm (giây)'),
        ('min_rest_sec', '10', 'Nghỉ tối thiểu trước khi bật lại (giây)'),
        ('noflow_min', '2', 'Thời gian không đổi mức nước (phút)'),
        ('publish_sec', '2', 'Chu kỳ gửi dữ liệu (giây)'),
        ('alert_mode', '1', 'Chế độ cảnh báo bật/tắt'),
        ('alert_led', '1', 'Đèn LED cảnh báo'),
        ('alert_buzzer', '1', 'Còi buzzer cảnh báo'),
        ('web_version', '1.0.0', 'Phiên bản Web Dashboard'),
        ('mqtt_broker', os.getenv('MQTT_HOST', '127.0.0.1'), 'MQTT Broker IP'),
        ('mqtt_port', os.getenv('MQTT_PORT', '1883'), 'MQTT Broker Port'),
        ('topic_prefix', os.getenv('MQTT_TOPIC_PREFIX', 'iot-ao-demo-123'), 'Tiền tố Topic MQTT'),
        ('language', 'vi', 'Ngôn ngữ hiển thị')
    ]
    cur.executemany("INSERT OR IGNORE INTO system_config (config_key, config_value, description) VALUES (?,?,?)", configs)

    # Seed initial sensor data if empty
    cur.execute("SELECT COUNT(*) FROM sensor_data")
    if cur.fetchone()[0] == 0:
        logger.info(">>> [DB] Nạp dữ liệu mẫu ban đầu cho SQLite...")
        cur.executemany("""
            INSERT INTO sensor_data (water_level, distance_cm, pump_in, pump_out, auto_mode, sensor_err, fault_code, rssi, uptime_sec, esp32_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (36.7, 65.0, 0, 0, 1, 0, 'none', -55, 3600, 'esp32-ao-demo'),
            (37.9, 63.8, 0, 0, 1, 0, 'none', -54, 3720, 'esp32-ao-demo'),
            (38.2, 63.4, 0, 0, 1, 0, 'none', -55, 3840, 'esp32-ao-demo'),
            (39.5, 62.0, 1, 0, 1, 0, 'none', -56, 3960, 'esp32-ao-demo'),
            (40.8, 60.9, 1, 0, 1, 0, 'none', -55, 4080, 'esp32-ao-demo'),
            (41.2, 60.5, 1, 0, 1, 0, 'none', -54, 4200, 'esp32-ao-demo'),
            (42.6, 59.3, 1, 0, 1, 0, 'none', -55, 4320, 'esp32-ao-demo'),
            (43.9, 58.0, 0, 0, 1, 0, 'none', -53, 4440, 'esp32-ao-demo'),
            (44.8, 57.1, 0, 0, 1, 0, 'none', -55, 4560, 'esp32-ao-demo'),
            (45.5, 56.7, 0, 0, 1, 0, 'none', -55, 4680, 'esp32-ao-demo'),
        ])

        cur.executemany("""
            INSERT INTO alerts (alert_code, message, severity, water_level, value_str, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            ('HIGH_LEVEL', 'Mực nước đạt 92% (nguy cơ tràn ao)', 'DANGER', 92.0, '92 %', 'UNRESOLVED'),
            ('PUMP_IN_OFF', 'Máy bơm cấp đã tắt', 'WARNING', 50.5, None, 'RESOLVED'),
            ('MODE', 'Chế độ MANUAL được kích hoạt', 'INFO', 43.2, None, 'RESOLVED'),
            ('HIGH_TREND', 'Mực nước tăng nhanh', 'WARNING', 65.0, '+5.2 %/h', 'RESOLVED'),
            ('SENSOR', 'Cảm biến đo không ổn định', 'WARNING', 40.0, None, 'RESOLVED'),
            ('PUMP_IN', 'Máy bơm cấp đã bật', 'INFO', 28.5, None, 'RESOLVED')
        ])

        cur.executemany("""
            INSERT INTO system_logs (log_level, component, event_type, message)
            VALUES (?, ?, ?, ?)
        """, [
            ('INFO', 'flask', 'started', 'Khởi động Flask Backend thành công'),
            ('INFO', 'mqtt', 'connected', 'Kết nối Mosquitto MQTT Broker thành công'),
            ('INFO', 'esp32', 'online', 'ESP32 trực tuyến (IP: 192.168.1.23)'),
            ('INFO', 'mqtt', 'data_received', 'Nhận dữ liệu ESP32: level=45.5% dist=56.7cm')
        ])

    conn.commit()
    conn.close()

def execute(sql: str, params=None, fetch: str = "none"):
    """
    Thực thi SQL theo db hiện tại (MySQL hoặc SQLite).
    Tự động chuẩn hóa cú pháp SQL (%s vs ?, NOW(), INTERVAL...).
    """
    if _db_type is None:
        init_db()

    if _db_type == "mysql":
        conn = _pool.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params or ())
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return cur.lastrowid
        finally:
            conn.close()
    else:
        # SQLite
        conn = sqlite3.connect(_sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            sql_lite = sql.replace("%s", "?")
            sql_lite = re.sub(
                r"NOW\(\)\s*-\s*INTERVAL\s+(\d+)\s+(MINUTE|HOUR|DAY)",
                r"datetime('now', '-\1 \2')",
                sql_lite,
                flags=re.IGNORECASE
            )
            sql_lite = sql_lite.replace("NOW(3)", "CURRENT_TIMESTAMP").replace("NOW()", "CURRENT_TIMESTAMP")
            sql_lite = sql_lite.replace("DATE_SUB(recorded_at, INTERVAL 1 DAY)", "datetime(recorded_at, '-1 day')")
            sql_lite = re.sub(r"DATE_FORMAT\(([^,]+),\s*'[^']+'\)", r"strftime('%Y-%m-%d %H:%M', \1)", sql_lite)

            cur.execute(sql_lite, params or ())
            if fetch == "one":
                row = cur.fetchone()
                return dict(row) if row else None
            if fetch == "all":
                rows = cur.fetchall()
                return [dict(r) for r in rows]
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()
