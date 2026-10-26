

# HỆ THỐNG GIÁM SÁT VÀ ĐIỀU KHIỂN MỰC NƯỚC AO NUÔI (IoT - ESP32 - MQTT)

> **Báo cáo và hướng dẫn triển khai đồ án IoT**  
> **Thành phần:** ESP32 · Cảm biến HC-SR04 · Relay 2 kênh · Mosquitto MQTT · Python Flask · MySQL 8.x · Web Dashboard 7 trang (Chart.js)

---

## MỤC LỤC
1. [Bộ công nghệ & Cấu trúc thư mục](#1-bộ-công-nghệ--cấu-trúc-thư-mục)
2. [Bước 1: Cài đặt MySQL và MySQL Workbench](#bước-1-cài-đặt-mysql-và-mysql-workbench)
3. [Bước 2: Thiết kế các bảng MySQL & Nạp dữ liệu mẫu](#bước-2-thiết-kế-các-bảng-mysql--nạp-dữ-liệu-mẫu)
4. [Bước 3: Cài đặt Mosquitto MQTT & Chạy ESP32 Giả lập](#bước-3-cài-đặt-mosquitto-mqtt--chạy-esp32-giả-lập)
5. [Bước 4: Cấu hình và Khởi động Backend Flask](#bước-4-cấu-hình-và-khởi-động-backend-flask)
6. [Bước 5: Hướng dẫn sử dụng Web Dashboard 7 Trang](#bước-5-hướng-dẫn-sử-dụng-web-dashboard-7-trang)
7. [Bước 6: Hướng dẫn nạp code ESP32 thật & Sơ đồ nối dây](#bước-6-hướng-dẫn-nạp-code-esp32-thật--sơ-đồ-nối-dây)

---

## 1. BỘ CÔNG NGHỆ & CẤU TRÚC THƯ MỤC

### 1.1. Bảng công nghệ thống nhất
| Thành phần | Công nghệ / Phần mềm | Ghi chú |
| :--- | :--- | :--- |
| **Vi điều khiển** | ESP32 Dev Module (30 chân) | WiFi 2.4GHz, bộ nhớ Flash lưu cấu hình |
| **Cảm biến** | HC-SR04 (Siêu âm) | Đo khoảng cách từ đỉnh ao đến mặt nước |
| **Điều khiển** | Relay 2 kênh (Opto cách ly) | Bơm cấp (GPIO 32) và Bơm thoát (GPIO 33) |
| **Giao thức** | MQTT (QoS 0/1, LWT, Retain) | Topic tiền tố: `iot-ao-demo-123` |
| **MQTT Broker** | Eclipse Mosquitto v2.x | Lắng nghe cổng `1883` |
| **Kiểm thử MQTT**| MQTT Explorer | Giám sát và gửi thử tin nhắn MQTT |
| **Backend** | Python 3.10+ (Flask, Paho-MQTT) | RESTful API, luồng nhận MQTT liên tục |
| **Cơ sở dữ liệu** | MySQL 8.x *(hỗ trợ fallback SQLite)*| Lưu trữ cảm biến, cảnh báo, log |
| **Quản lý CSDL** | MySQL Workbench | Thiết kế bảng và truy vấn |
| **Frontend** | HTML5, CSS3, JavaScript (ES6) | Single Page Application (SPA), Responsive |
| **Biểu đồ** | Chart.js v4.4 | Đường mực nước thời gian thực, min/max |

### 1.2. Cấu trúc thư mục dự án
```text
d:\btl iot\
├── ao_nuoc\
│   └── ao_nuoc.ino              # Code nạp cho mạch ESP32
├── backend\
│   ├── .env.example             # Mẫu cấu hình môi trường (MySQL, MQTT, Flask)
│   ├── app.py                   # Flask REST API server (phục vụ cả web frontend)
│   ├── db.py                    # Kết nối MySQL và tự động chuyển SQLite khi cần
│   ├── mqtt_client.py           # Luồng nhận MQTT và lưu vào database
│   ├── esp32_simulator.py       # Bộ giả lập phần cứng ESP32 phục vụ gửi dữ liệu ESP32 giả lập để không phải chờ phần cứng
│   └── requirements.txt         # Danh sách thư viện Python
├── database\
│   ├── 01_create_database.sql   # Script SQL tạo CSDL iot_ao_nuoi và 5 bảng
│   └── 02_sample_data.sql       # Script SQL nạp dữ liệu kiểm thử ban đầu
├── frontend\
│   ├── index.html               # Giao diện chính gồm 7 trang chức năng
│   ├── style.css                # Toàn bộ định dạng giao diện 
│   ├── api.js                   # Module gọi API backend
│   └── app.js                   # Logic biểu đồ, điều khiển, cảnh báo, lịch sử
├── mosquitto\
│   └── mosquitto.conf           # File cấu hình Mosquitto Broker cổng 1883
├── start.bat                    # Script 1-click khởi động Backend Flask
├── start_simulator.bat          # Script 1-click chạy giả lập ESP32
└── HUONG_DAN_CAI_DAT.md         # File tài liệu này
```

---

## BƯỚC 1: CÀI ĐẶT MYSQL VÀ MYSQL WORKBENCH

1. **Tải và cài đặt MySQL Server:**
   - Tải bộ cài đặt: [MySQL Community Server & Workbench](https://dev.mysql.com/downloads/installer/).
   - Trong quá trình cài đặt, ghi nhớ mật khẩu tài khoản `root` (ví dụ: `root` hoặc `123456`).
   - Cổng mặc định của MySQL là `3306`.

2. **Tạo kết nối trong MySQL Workbench:**
   - Mở **MySQL Workbench** -> Nhấn dấu `+` để thêm kết nối mới:
     - **Connection Name:** `AoNuoi_Local`
     - **Hostname:** `127.0.0.1` (hoặc `localhost`)
     - **Port:** `3306`
     - **Username:** `root`
   - Nhấn **Test Connection** -> Nhập mật khẩu để kiểm tra kết nối thành công.

---

## BƯỚC 2: THIẾT KẾ CÁC BẢNG MYSQL & NẠP DỮ LIỆU MẪU

1. **Chạy file khởi tạo cấu trúc CSDL:**
   - Trong MySQL Workbench, nhấn `File` -> `Open SQL Script...` -> Chọn file:
     `d:\btl iot\database\01_create_database.sql`
   - Nhấn biểu tượng tia sét ⚡ (Execute) để thực thi.
   - Database `iot_ao_nuoi` sẽ được tạo gồm các bảng:
     - `sensor_data`: Lưu trữ mực nước (%), khoảng cách (cm), trạng thái bơm IN/OUT, AUTO/MANUAL, RSSI, thời gian.
     - `alerts`: Lưu trữ các cảnh báo nguy hiểm/thông tin (HIGH_LEVEL, LOW_LEVEL, SENSOR, PUMP,...).
     - `control_logs`: Lưu nhật ký các lệnh điều khiển từ web và phản hồi ACK từ ESP32.
     - `system_logs`: Ghi nhận sự kiện kết nối MQTT, khởi động hệ thống, lỗi.
     - `system_config`: Bảng lưu tham số ngưỡng bật/tắt bơm và khoảng cách ao.

2. **Nạp dữ liệu mẫu để kiểm thử:**
   - Mở và chạy file:
     `d:\btl iot\database\02_sample_data.sql`
   - Kiểm tra dữ liệu vừa nạp:
     ```sql
     USE iot_ao_nuoi;
     SELECT * FROM sensor_data ORDER BY recorded_at DESC LIMIT 10;
     SELECT * FROM alerts;
     ```

---

## BƯỚC 3: CÀI ĐẶT MOSQUITTO MQTT & CHẠY ESP32 GIẢ LẬP

### 3.1. Cài đặt và cấu hình Mosquitto Broker
1. Tải và cài đặt Mosquitto: [Eclipse Mosquitto Downloads](https://mosquitto.org/download/).
2. Sao chép cấu hình hoặc sử dụng file [mosquitto.conf](file:///d:/btl%20iot/mosquitto/mosquitto.conf).
3. Mở Command Prompt (Admin) và khởi động Mosquitto:
   ```cmd
   net start mosquitto
   ```
   *(Hoặc chạy trực tiếp: `mosquitto -v`)*


### 3.2. Chạy bộ giả lập ESP32 (Không cần phần cứng)
Để kiểm thử trọn vẹn toàn bộ chức năng mà không cần cắm mạch thật:
- **Cách 1:** Nhấp đúp vào file `d:\btl iot\start_simulator.bat`.
- **Cách 2:** Mở Terminal và gõ:
  ```cmd
  cd "d:\btl iot\backend"
  python esp32_simulator.py
  ```
- **Bộ giả lập sẽ tự động:**
  - Phát dữ liệu mực nước và khoảng cách cảm biến mỗi 2 giây lên topic `iot-ao-demo-123/data`.
  - Tự động thay đổi mực nước khi bật bơm cấp (tăng dần) hoặc bơm thoát (giảm dần).
  - Tự động kích hoạt AUTO đóng cắt bơm theo ngưỡng đã cấu hình.
  - Nhận các lệnh từ Web Dashboard và gửi phản hồi ACK ngay lập tức.

---

## BƯỚC 4: CẤU HÌNH VÀ KHỞI ĐỘNG BACKEND FLASK

1. **Cấu hình môi trường (.env):**
   - Vào thư mục `backend\`, sao chép `.env.example` thành `.env`:
     ```ini
     # Cấu hình kết nối MySQL
     DB_HOST=localhost
     DB_PORT=3306
     DB_NAME=iot_ao_nuoi
     DB_USER=root
     DB_PASS=mật_khẩu_mysql_của_bạn

     # Cấu hình MQTT Broker
     MQTT_HOST=127.0.0.1
     MQTT_PORT=1883
     MQTT_USER=esp32
     MQTT_PASS=esp32pass
     MQTT_TOPIC_PREFIX=iot-ao-demo-123

     # Flask Web Server
     FLASK_HOST=0.0.0.0
     FLASK_PORT=5000
     FLASK_DEBUG=true
     ```
   > **Lưu ý tính năng Fallback:** Nếu máy tính của bạn chưa bật MySQL Server, hệ thống Backend sẽ tự động phát hiện và chuyển sang chế độ SQLite nhúng (`data.db`) để đảm bảo website hoạt động bình thường ngay lập tức!

2. **Khởi động Backend:**
   - Nhấp đúp chuột vào file: [start.bat](file:///d:/btl%20iot/start.bat).
   - Script sẽ kiểm tra thư viện Python, khởi tạo file cấu hình và khởi chạy máy chủ Flask.
   - Màn hình sẽ hiện:
     ```text
     ================================================
      HE THONG GIAM SAT MUC NUOC AO NUOI
      ESP32 + HC-SR04 + MQTT + Flask + MySQL
     ================================================
      Website: http://localhost:5000
      API:     http://localhost:5000/api/status
     ```

---

## BƯỚC 5: HƯỚNG DẪN SỬ DỤNG WEB DASHBOARD 7 TRANG

Mở trình duyệt bất kỳ (Chrome, Edge, Firefox) và truy cập:
👉 **`http://localhost:5000`**

Giao diện được thiết kế chuẩn xác 100% theo các hình ảnh mô tả:

### 1. Trang "Tổng quan"
- **4 Thẻ chỉ số đầu trang:**
  - *Mực nước hiện tại:* Hiển thị phần trăm (%) và khoảng cách thực tế (cm).
  - *Trạng thái ESP32:* Đèn xanh `Online`, chỉ số cường độ sóng Wi-Fi RSSI (dBm).
  - *Chế độ hoạt động:* Hiển thị chế độ hiện tại (`AUTO` hoặc `MANUAL`).
  - *Kết nối MQTT:* Trạng thái kết nối tới Mosquitto Broker.
- **Biểu đồ mực nước 30 phút qua:** Đường biểu diễn biến thiên mực nước thời gian thực kèm 2 vạch ngưỡng nguy hiểm (90%) và ngưỡng cảnh báo (80%).
- **Trạng thái máy bơm:** Hiển thị trạng thái hoạt động của Bơm cấp (IN) và Bơm thoát (OUT) kèm đèn báo và hoạt họa mực nước ao.
- **Cảnh báo mới nhất:** 3 sự kiện cảnh báo gần nhất với biểu tượng cảnh báo màu đỏ/vàng.
- **Mô hình hệ thống:** Sơ đồ khối trực quan: Cảm biến HC-SR04 -> ESP32 -> MQTT Broker -> Flask Backend -> Web Dashboard.

### 2. Trang "Biểu đồ"
- Chuyển đổi linh hoạt giữa các mốc thời gian: **30 phút**, **24 giờ**, **7 ngày**, **30 ngày**.
- Biểu đồ cột thể hiện thời gian bật/tắt của hai máy bơm.
- Bảng thống kê chi tiết: Mức cao nhất (Max), Mức thấp nhất (Min), Mức trung bình (Avg), Mức hiện tại và tổng số bản ghi đo được.

### 3. Trang "Điều khiển"
- **Chuyển đổi chế độ:** Kích hoạt chế độ `AUTO` (tự động theo ngưỡng) hoặc `MANUAL` (điều khiển bằng tay).
- **Điều khiển trực tiếp:** Nút bấm Bật / Tắt riêng cho Bơm cấp nước (IN) và Bơm thoát nước (OUT) với cơ chế bảo vệ khóa chéo (không cho 2 bơm chạy cùng lúc).
- **Thiết lập ngưỡng nhanh:** Đặt nhanh ngưỡng bật/tắt bơm cấp và bơm thoát.
- **Nhật ký lệnh điều khiển:** Hiển thị danh sách các lệnh vừa gửi, thời gian gửi và nội dung phản hồi ACK từ ESP32.

### 4. Trang "Cấu hình"
- **Ngưỡng điều khiển máy bơm:** Thiết lập chi tiết ngưỡng bật/tắt của Bơm IN và Bơm OUT.
- **Hiệu chỉnh cảm biến:** Thiết lập khoảng cách khi ao cạn ($d_{Empty}$) và khi ao đầy ($d_{Full}$) kèm 2 nút hiệu chỉnh nhanh lấy khoảng cách hiện tại.
- **Tham số an toàn:** Thời gian chạy bơm tối đa chống cháy bơm (phút), thời gian nghỉ giữa 2 bơm (giây), ngưỡng cảnh báo tràn (95%) và cảnh báo cạn (5%).
- **Cài đặt hệ thống & Nút thao tác:**
  - *Lưu cấu hình và gửi xuống ESP32*
  - *Yêu cầu gửi lại cấu hình hiện tại*
  - *Xóa lỗi cảnh báo (Reset)*
  - *Khởi động lại ESP32*
- **Bảng tóm tắt cấu hình hiện tại từ ESP32:** Giúp đối chiếu xác thực thông số đã đồng bộ.

### 5. Trang "Cảnh báo"
- **3 Thẻ thống kê 24 giờ:** Đếm số cảnh báo theo 3 mức độ: *Nguy hiểm (Đỏ)*, *Cảnh báo (Vàng)*, *Thông tin (Xanh)*.
- **Bộ lọc đa tiêu chí:** Lọc theo mức độ, trạng thái xử lý, khoảng thời gian (Từ ngày - Đến ngày).
- **Danh sách cảnh báo:** Xem chi tiết mã cảnh báo, nội dung, giá trị đo được lúc cảnh báo và nút "Xử lý" để đánh dấu đã giải quyết.

### 6. Trang "Lịch sử dữ liệu"
- Bảng tra cứu toàn bộ dữ liệu lịch sử cảm biến từ MySQL.
- Các nút chọn nhanh: **Hôm nay**, **7 ngày**, **30 ngày**, **Tất cả**.
- **Tính năng xuất file:** Nút **"Xuất CSV"** và **"Xuất Excel"** cho phép tải dữ liệu lịch sử về máy tính để làm báo cáo thống kê.
- Phân trang linh hoạt: 20 dòng, 50 dòng hoặc 100 dòng trên mỗi trang.

### 7. Trang "Thông tin hệ thống"
- **Thông tin thiết bị ESP32:** Tên thiết bị, thời gian hoạt động liên tục (Uptime), IP mạng, cường độ WiFi, phiên bản firmware.
- **Thông tin kết nối MQTT:** Địa chỉ Broker, cổng kết nối, danh sách topic MQTT sử dụng.
- **Thông tin hệ thống Web:** Phiên bản ứng dụng, loại CSDL đang hoạt động (`MySQL 8.x` hoặc `SQLite`), tổng số bản ghi dữ liệu.
- **Nhật ký hệ thống (System Log):** Theo dõi các sự kiện thời gian thực (kết nối, nhận dữ liệu, gửi lệnh).

---

## BƯỚC 6: HƯỚNG DẪN NẠP CODE ESP32 THẬT & SƠ ĐỒ NỐI DÂY

### 6.1. Sơ đồ nối dây phần cứng
```text
           +---------------------------------------------+
           |                 ESP32-WROOM                 |
           |                                             |
           |  [GPIO 26] -----------------> Trig (HC-SR04)|
           |                                             |
           |                                 [R1: 1kΩ]   |
           |  [GPIO 27] <-------+--------- Echo (5V)     |
           |                    |                        |
           |                 [R2: 2kΩ]                   |
           |                    |                        |
           |  [GND] ------------+-------- GND (HC-SR04)  |
           |                                             |
           |  [VIN / 5V] ---------------- VCC (HC-SR04)  |
           |                                             |
           |  [GPIO 32] -----------------> IN1 (Relay 1 - Bơm cấp)
           |  [GPIO 33] -----------------> IN2 (Relay 2 - Bơm thoát)
           |  [GND] ---------------------> GND (Relay)   |
           |  [VIN / 5V] ----------------> VCC (Relay)   |
           |                                             |
           |  [GPIO 2]  -----------------> Còi/Đèn cảnh báo
           +---------------------------------------------+
```
> ⚠️ **LƯU Ý QUAN TRỌNG:** Cảm biến HC-SR04 dùng nguồn 5V nên chân `Echo` xuất tín hiệu 5V. Chân GPIO của ESP32 chỉ chịu tối đa 3.3V, do đó **BẮT BUỘC** phải dùng cầu phân áp bằng 2 điện trở (1kΩ nối từ Echo vào GPIO 27, và 2kΩ nối từ GPIO 27 xuống GND) để bảo vệ chip ESP32.

### 6.2. Nạp code bằng Arduino IDE
1. Mở phần mềm **Arduino IDE**.
2. Cài đặt hỗ trợ chip ESP32: Vào `File` -> `Preferences` -> dán URL sau vào mục *Additional Boards Manager URLs*:
   ```text
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Cài đặt thư viện MQTT: Vào `Tools` -> `Manage Libraries...` -> Tìm và cài đặt thư viện **`PubSubClient`** của Nick O'Leary.
4. Mở file [ao_nuoc/ao_nuoc.ino](file:///d:/btl%20iot/ao_nuoc/ao_nuoc.ino).
5. Chỉnh sửa cấu hình mạng Wi-Fi và IP máy tính chạy Mosquitto:
   ```cpp
   const char* WIFI_SSID = "Tên_WiFi_Của_Bạn";
   const char* WIFI_PASS = "Mật_Khẩu_WiFi";
   const char* MQTT_HOST = "192.168.1.100";  // IP máy tính trong mạng Wi-Fi
   ```
6. Vào `Tools` -> Chọn board **ESP32 Dev Module**, chọn đúng cổng COM.
7. Nhấn **Upload** (Mũi tên sang phải) để nạp code vào ESP32.
8. Mở **Serial Monitor** với tốc độ `115200 baud` để theo dõi quá trình kết nối và gửi nhận dữ liệu.

---
**Chúc bạn triển khai thành công đồ án IoT Giám sát và Điều khiển Ao nuôi!**

## XỬ LÝ SỰ CỐ

- **`python` hoặc `pip` không được nhận diện:** cài lại Python và bật
  **Add Python to PATH**, sau đó mở terminal mới.
- **`start.bat` không cài được dependency:** chạy
  `python -m pip install -r backend\requirements.txt` tại thư mục gốc.
- **Simulator không kết nối được:** kiểm tra cửa sổ Mosquitto, tài khoản
  `esp32` trong `passwd.txt`, và các biến `MQTT_*` trong `backend\.env`.
- **Dashboard mở nhưng không có dữ liệu mới:** backend và simulator phải cùng
  dùng một `MQTT_TOPIC_PREFIX`; mặc định là `iot-ao-demo-123`.
- **ESP32 thật không kết nối được:** kiểm tra ESP32 dùng Wi-Fi 2.4 GHz, cùng
  mạng LAN với máy tính, IP broker trong firmware là IP LAN của máy tính, và
  chân `Echo` HC-SR04 đã qua cầu phân áp 3.3 V.