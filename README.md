# Hệ thống giám sát và điều khiển mực nước ao nuôi

Ứng dụng IoT gồm ESP32/ESP32 giả lập, cảm biến HC-SR04, hai bơm, MQTT
(Mosquitto), backend Flask và Web Dashboard.

## Chọn cách chạy

### Chạy nhanh bằng SQLite (không cần MySQL, không cần phần cứng)

Đây là cách phù hợp để xem giao diện và kiểm thử toàn bộ luồng điều khiển.

1. Cài **Python 3.10 trở lên** và đánh dấu **Add Python to PATH** trong trình
   cài đặt.
2. Cài **Mosquitto 2.x**. Broker phải được chạy trước backend và simulator.
3. Mở Mosquitto theo hướng dẫn tại mục [Cài đặt Mosquitto](HUONG_DAN_CAI_DAT.md#bước-3-cài-đặt-mosquitto-mqtt--chạy-esp32-giả-lập).
4. Chạy `start.bat`. Lần đầu, script sẽ cài các thư viện Python và tạo
   `backend\.env`. Có thể giữ cấu hình mặc định để dùng SQLite fallback.
5. Mở một cửa sổ terminal khác và chạy `start_simulator.bat`.
6. Truy cập <http://localhost:5000>.

Backend sẽ tự chuyển sang `backend\data.db` nếu không kết nối được MySQL.
Simulator vẫn cần Mosquitto để trao đổi dữ liệu MQTT.

### Chạy với MySQL

1. Cài MySQL Server 8.x và MySQL Workbench.
2. Chạy lần lượt `database\01_create_database.sql` và tùy chọn
   `database\02_sample_data.sql` trong MySQL Workbench.
3. Sửa các giá trị `DB_*` trong `backend\.env` cho đúng tài khoản MySQL.
4. Chạy Mosquitto, sau đó chạy `start.bat` và `start_simulator.bat` như luồng
   SQLite ở trên.

Hướng dẫn cài đặt, cấu hình MQTT, MySQL, phần cứng và dashboard nằm trong
[HUONG_DAN_CAI_DAT.md](HUONG_DAN_CAI_DAT.md).

## Chạy ESP32 thật

Mở [ao_nuoc/ao_nuoc.ino](ao_nuoc/ao_nuoc.ino) bằng Arduino IDE, cài board
ESP32 và thư viện `PubSubClient`, rồi sửa Wi-Fi, IP máy chạy Mosquitto và
thông tin MQTT trước khi nạp. Chi tiết sơ đồ nối dây và cảnh báo mức điện áp
được trình bày trong hướng dẫn cài đặt.

## Các file khởi chạy

| File | Mục đích |
| --- | --- |
| `start.bat` | Cài dependency và chạy Flask backend tại cổng 5000 |
| `start_simulator.bat` | Chạy ESP32 simulator, phát dữ liệu mỗi 2 giây |
| `run.bat` | Bí danh gọi `start.bat` |

## Xử lý nhanh lỗi thường gặp

- **Không mở được `http://localhost:5000`**: kiểm tra cửa sổ `start.bat` còn
  đang chạy và cổng 5000 chưa bị ứng dụng khác sử dụng.
- **Simulator báo không kết nối MQTT**: kiểm tra Mosquitto đang chạy ở cổng
  1883, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS` trong
  `backend\.env`, và file mật khẩu Mosquitto có tài khoản `esp32`.
- **Backend báo không kết nối MySQL**: kiểm tra MySQL đang chạy, database đã
  được tạo và thông tin `DB_*` đúng. Nếu không cần MySQL, có thể tiếp tục dùng
  SQLite fallback.
- **ESP32 thật không kết nối được**: máy tính chạy Mosquitto và ESP32 phải
  cùng mạng LAN; trong firmware không dùng `127.0.0.1` mà dùng IP LAN của máy
  tính.
