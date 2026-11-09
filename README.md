# HỆ THỐNG GIÁM SÁT VÀ ĐIỀU KHIỂN MỰC NƯỚC AO NUÔI CÁ THÔNG MINH (IoT - ESP32 - MQTT)

> **Đồ án môn học:** Lập trình nhúng và IoT / Ứng dụng IoT trong Nông nghiệp Thông minh  
> **Nền tảng:** ESP32 · Cảm biến HC-SR04 · Relay 2 kênh · Mosquitto MQTT · Python Flask · MySQL 8.x / SQLite Fallback · Trợ lý AI (Chatbox) · Cảnh báo Email tự động (Rule Engine)

---

## MỤC LỤC
1. [Giới thiệu dự án](#1-giới-thiệu-dự-án)
2. [Bài toán thực tế](#2-bài-toán-thực-tế)
3. [Mục tiêu dự án](#3-mục-tiêu-dự-án)
4. [Chức năng hệ thống](#4-chức-năng-hệ-thống)
5. [Công nghệ sử dụng](#5-công-nghệ-sử-dụng)
6. [Kiến trúc hệ thống](#6-kiến-trúc-hệ-thống)
7. [Nguyên lý hoạt động](#7-nguyên-lý-hoạt-động)
8. [Thiết kế phần cứng](#8-thiết-kế-phần-cứng)
9. [Giao thức MQTT](#9-giao-thức-mqtt)
10. [Cấu trúc thư mục](#10-cấu-trúc-thư-mục)
11. [Cơ sở dữ liệu](#11-cơ-sở-dữ-liệu)
12. [Cài đặt và chạy dự án](#12-cài-đặt-và-chạy-dự-án)
13. [Hướng dẫn sử dụng Web](#13-hướng-dẫn-sử-dụng-web)
14. [API Backend](#14-api-backend)
15. [Cảnh báo và điều khiển](#15-cảnh-báo-và-điều-khiển)

---

## 1. GIỚI THIỆU DỰ ÁN
**Hệ thống giám sát và điều khiển mực nước ao nuôi cá thông minh** là một giải pháp IoT toàn diện từ phần cứng biên (Edge Hardware) đến máy chủ (Backend Server) và giao diện người dùng (Web Dashboard & Trợ lý AI). 

Hệ thống kết hợp vi điều khiển **ESP32**, cảm biến siêu âm **HC-SR04** và cụm **Relay điều khiển 2 máy bơm** (Bơm cấp nước IN và Bơm thoát nước OUT) giao tiếp hai chiều thời gian thực thông qua giao thức **MQTT (Mosquitto)**. Toàn bộ dữ liệu được lưu trữ, tổng hợp tại máy chủ **Python Flask** và **MySQL 8.x** (tự động chuyển đổi **SQLite** khi không có máy chủ MySQL), đồng thời cung cấp:
- **Web Dashboard trực quan 6 trang**: Giám sát biến thiên mực nước thời gian thực, điều khiển máy bơm an toàn, hiệu chỉnh cảm biến và xuất báo cáo dữ liệu.
- **Trợ lý AI (Chatbox)**: Tích hợp mô hình ngôn ngữ tự nhiên (NLP / Fast Path + Gemini Function Calling) cho phép người nuôi tra cứu dữ liệu, phân tích biến động và điều khiển máy bơm bằng tiếng Việt tự nhiên có xác nhận 2 bước an toàn.
- **Hệ thống Cảnh báo & Gửi Email tự động (Rule Engine)**: Phát hiện tự động sự cố mực nước nguy hiểm, bơm chạy không hiệu quả, mất kết nối thiết bị và gửi cảnh báo trực tiếp qua Gmail SMTP mà không cần người dùng phải mở website.

---

## 2. BÀI TOÁN THỰC TẾ
Trong nuôi trồng thủy sản, mực nước là yếu tố sống còn ảnh hưởng trực tiếp đến môi trường sống của cá:
- **Mực nước quá cao (Nguy cơ tràn ao):** Khi xảy ra mưa lớn hoặc bơm cấp nước quên tắt, nước tràn bờ khiến cá thất thoát ra ngoài, gây thiệt hại kinh tế nghiêm trọng và làm vỡ bờ ao.
- **Mực nước quá thấp (Nguy cơ cạn kiệt):** Ao bị rò rỉ hoặc bốc hơi vào mùa nắng nóng làm giảm thể tích nước, nhiệt độ nước tăng nhanh, nồng độ oxy hòa tan sụt giảm gây ngạt cá và bùng phát dịch bệnh.
- **Phương pháp quản lý thủ công bộc lộ nhiều hạn chế:**
  - Người nuôi phải túc trực kiểm tra bờ ao 24/7, đặc biệt vào ban đêm hoặc mùa mưa bão.
  - Phụ thuộc vào quan sát mắt thường, không ghi chép được xu hướng biến động mực nước theo thời gian.
  - Thao tác đóng ngắt máy bơm bằng tay dễ xảy ra sự cố quên tắt làm cháy máy bơm, chạy bơm cấp và bơm thoát cùng lúc gây xung đột thủy lực lãng phí điện năng.
  - Khi sự cố xảy ra ngoài giờ giám sát, không có cơ chế cảnh báo từ xa tức thời đến điện thoại hay hòm thư của người phụ trách.

---

## 3. MỤC TIÊU DỰ ÁN
1. **Giám sát thời gian thực:** Thu thập liên tục mực nước (tính theo % và cm) và trạng thái các thiết bị với chu kỳ 2 giây/lần, hiển thị trực quan lên Dashboard.
2. **Tự động hóa điều khiển:** Vận hành độc lập ở chế độ tự động (`AUTO`) trên ESP32 theo các ngưỡng $in_{On}, in_{Off}, out_{On}, out_{Off}$ đã cài đặt; hỗ trợ can thiệp bằng tay (`MANUAL`) từ xa.
3. **An toàn thiết bị tối đa:** Khóa chéo liên động (Interlock) tuyệt đối không cho 2 bơm chạy đồng thời; tự động ngắt bơm khi chạy quá thời gian tối đa (`pump_overrun`); phát hiện sự cố bơm chạy nhưng nước không đổi (`no_flow`).
4. **Cảnh báo chủ động qua Email:** Triển khai bộ quy tắc (Rule Engine) tự động xếp hàng và gửi email khẩn cấp đến chủ ao qua Gmail SMTP khi có sự cố và gửi thông báo phục hồi khi hệ thống trở lại trạng thái an toàn.
5. **Trợ lý hội thoại AI:** Hỗ trợ người dùng tra cứu dữ liệu, tóm tắt hoạt động trong ngày, kiểm tra biến động nước trong khoảng thời gian bất kỳ bằng tiếng Việt tự nhiên và hỗ trợ đề xuất lệnh điều khiển an toàn.
6. **Độ tin cậy & Tính liên tục:** Hệ thống tự động chuyển đổi CSDL sang SQLite nhúng nếu MySQL chưa bật; ESP32 tự duy trì chế độ tự động an toàn kể cả khi mất kết nối mạng.

---

## 4. CHỨC NĂNG HỆ THỐNG

### 4.1. Nhóm chức năng tại thiết bị biên (ESP32 Firmware)
- **Đo khoảng cách & Tính mực nước:** Lọc nhiễu cảm biến siêu âm HC-SR04, chuyển đổi khoảng cách sang % mực nước dựa theo độ sâu ao ($d_{Empty}, d_{Full}$).
- **Điều khiển 2 rơ-le:** Đóng cắt Bơm cấp nước (IN - GPIO 32) và Bơm thoát nước (OUT - GPIO 33) với cơ chế kích mức thấp (Active LOW) an toàn.
- **Chế độ vận hành kép:**
  - `AUTO`: Tự động bật bơm cấp khi nước $\le in_{On}$, tắt khi $\ge in_{Off}$; bật bơm thoát khi $\ge out_{On}$, tắt khi $\le out_{Off}$.
  - `MANUAL`: Chấp hành lệnh đóng/ngắt trực tiếp từ Web/App qua MQTT.
- **Bảo vệ phần cứng độc lập:** Khóa chéo 2 bơm, chống dội lệnh, thời gian trễ bảo vệ khi đổi bơm (`switch_delay`), giới hạn thời gian chạy liên tục tối đa (`max_run`).
- **Giao tiếp MQTT & Lưu cấu hình:** Nhận lệnh điều khiển, phát dữ liệu telemetry mỗi 2s, phát bản tin cảnh báo khẩn cấp, lưu cấu hình vào bộ nhớ Flash (EEPROM/NVS).

### 4.2. Nhóm chức năng Web Dashboard
- **Trang Tổng quan:** Hiển thị 4 thẻ thông số tức thời (mực nước, ESP32 RSSI, chế độ, MQTT), biểu đồ đường 30 phút, thẻ trạng thái máy bơm và **Widget cấu hình nhanh Cảnh báo qua Email**.
- **Trang Điều khiển:** Chuyển đổi chế độ AUTO/MANUAL, nút bật/tắt bơm có khóa an toàn, đặt nhanh ngưỡng điều khiển và bảng nhật ký lệnh gửi kèm ACK từ ESP32.
- **Trang Cấu hình:** Hiệu chỉnh khoảng cách ao ($d_{Empty}, d_{Full}$), ngưỡng bơm, tham số an toàn (thời gian chạy tối đa, chu kỳ gửi MQTT), đồng bộ cấu hình 2 chiều với ESP32 và **Quản lý danh bạ email nhận cảnh báo**.
- **Trang Cảnh báo:** Thống kê sự cố trong 24h theo mức độ (Nguy hiểm, Cảnh báo, Thông tin), bộ lọc đa tiêu chí (ngày tháng, trạng thái, mức độ).
- **Trang Lịch sử dữ liệu:** Tra cứu toàn bộ bản ghi cảm biến, phân trang linh hoạt, hỗ trợ **Xuất báo cáo định dạng Excel (.xlsx) và CSV**.
- **Trang Trợ lý AI (Chatbox):** Giao diện hội thoại thông minh hỗ trợ hỏi đáp tiếng Việt tự nhiên và xác nhận lệnh điều khiển.

### 4.3. Nhóm chức năng Trợ lý AI (Chatbox)
- **Kiến trúc Hybrid (Fast Path + LLM):** Phản hồi siêu tốc (< 100ms) các câu hỏi chuẩn và mở rộng hiểu ngữ cảnh linh hoạt qua LLM.
- **Hỏi đáp thông số thời gian thực:** Trả lời tình trạng mực nước, trạng thái 2 máy bơm, kết nối thiết bị.
- **Phân tích biến động & Tóm tắt:** Tính toán mức tăng/giảm nước trong khoảng thời gian tùy ý (15 phút, 30 phút, 1 giờ,...), tóm tắt hoạt động trong ngày (số lần bơm chạy, mực nước Min/Max).
- **Hỗ trợ điều khiển an toàn:** Đề xuất lệnh điều khiển -> Yêu cầu người dùng bấm nút xác nhận -> Kiểm tra an toàn trước khi phát lệnh MQTT.
- **Hàng rào an toàn (Safety Guard):**
  - Chống Prompt Injection: Từ chối các câu lệnh phá rào an toàn ("bỏ qua hướng dẫn...").
  - Từ chối lệnh xung đột: Ngăn chặn yêu cầu bật cả hai bơm đồng thời.
  - Rào chặn câu hỏi ngoài phạm vi: Tự động phát hiện và giải thích rõ ràng khi người dùng hỏi các thông số chưa có cảm biến (độ ẩm, pH, oxy DO, nhiệt độ nước, độ mặn, độ đục, khí độc, bệnh cá,...).

### 4.4. Nhóm chức năng Cảnh báo & Gửi Email tự động (Rule Engine)
- **Quy tắc cảnh báo chuyên biệt:**
  - `HIGH_LEVEL`: Mực nước $\ge limit_{high}$ (Nguy hiểm - DANGER).
  - `LOW_LEVEL`: Mực nước $\le limit_{low}$ (Nguy hiểm - DANGER).
  - `NEAR_HIGH_LEVEL` / `NEAR_LOW_LEVEL`: Mực nước tiến sát ngưỡng và xu hướng tiếp tục bất lợi (Cảnh báo - WARNING).
  - `NO_FLOW_IN` / `NO_FLOW_OUT`: Bơm bật liên tục $\ge 3$ phút nhưng mực nước không thay đổi tương ứng.
  - `PUMP_OVERRUN`: Bơm chạy quá thời gian bảo vệ tối đa.
  - `SENSOR_ERROR`: Cảm biến siêu âm mất tín hiệu hoặc trả giá trị bất thường.
  - `ESP_OFFLINE`: Watchdog phát hiện ESP32 mất liên lạc quá 120 giây.
- **Chống spam & Nhắc lại thông minh:** Mỗi sự cố chỉ tạo 1 bản ghi `ACTIVE`; gửi nhắc lại có kiểm soát (30 phút với DANGER, 120 phút với WARNING, tối đa 3 lần); giới hạn an toàn tối đa 10 email/giờ.
- **Thông báo phục hồi:** Tự động gửi email thông báo khi sự cố được khắc phục an toàn (kèm hysteresis chống rung lắc).

---

## 5. CÔNG NGHỆ SỬ DỤNG

| Lĩnh vực | Tên công nghệ / Thư viện | Vai trò trong hệ thống |
| :--- | :--- | :--- |
| **Phần cứng (Hardware)** | **ESP32 NodeMCU 30 chân** | Vi điều khiển trung tâm, xử lý đo đạc, điều khiển rơ-le, kết nối WiFi |
| | **HC-SR04** | Cảm biến siêu âm đo khoảng cách mặt nước (2cm - 400cm) |
| | **Relay Module 2 kênh** | Cách ly quang Opto, đóng cắt nguồn AC/DC cho 2 máy bơm |
| | **Cầu phân áp (1kΩ & 2kΩ)** | Hạ mức logic 5V chân Echo của HC-SR04 xuống 3.3V an toàn cho ESP32 |
| **Phần sụn (Firmware)** | **C / C++ (Arduino Core)** | Lập trình logic biên trên ESP32 |
| | **PubSubClient** | Thư viện client giao tiếp MQTT trên ESP32 |
| | **EEPROM / Preferences** | Lưu cấu hình ngưỡng vào bộ nhớ không bay hơi |
| **Truyền thông (Transport)** | **Eclipse Mosquitto 2.x** | MQTT Broker trung chuyển bản tin telemetry, lệnh và cảnh báo |
| | **Giao thức MQTT v3.1.1** | Giao thức nhẹ, hỗ trợ QoS 0/1, Retain và Last Will (LWT) |
| **Máy chủ (Backend)** | **Python 3.10+** | Ngôn ngữ phát triển dịch vụ phía server |
| | **Flask & Flask-CORS** | Xây dựng RESTful API và phục vụ giao diện tĩnh SPA |
| | **Paho-MQTT v1.6.1** | Client Python nhận dữ liệu MQTT từ broker và ghi vào database |
| | **smtplib & email.mime** | Module chuẩn gửi email qua giao thức SMTP (STARTTLS port 587) |
| **Cơ sở dữ liệu (Storage)** | **MySQL Server 8.x** | Hệ quản trị cơ sở dữ liệu quan hệ lưu trữ dữ liệu lịch sử lâu dài |
| | **SQLite 3 (Fallback Mode)** | Tự động kích hoạt khi chưa có MySQL, lưu trữ độc lập tại `data.db` |
| **Giao diện (Frontend)** | **HTML5, CSS3, JavaScript (ES6)** | Giao diện Single Page Application (SPA), Responsive cho PC & Mobile |
| | **Chart.js v4.4** | Vẽ biểu đồ biến thiên mực nước thời gian thực |
| **Trí tuệ nhân tạo (AI)** | **Rule-based NLP + Regex** | Tầng Fast Path định tuyến ý định và rào an toàn trong < 100ms |
| | **Google Gemini REST API** | Mô hình ngôn ngữ lớn (tùy chọn) hỗ trợ câu hỏi phức tạp |

---

## 6. KIẾN TRÚC HỆ THỐNG

### 6.1. Sơ đồ khối tổng thể
```text
  +-------------------------------------------------------------------------+
  |                             TẦNG THIẾT BỊ BIÊN                           |
  |   +-------------------+                     +-----------------------+   |
  |   | Cảm biến HC-SR04  | ===(Khoảng cách)==> |      ESP32 Board      |   |
  |   +-------------------+                     | (Thu thập, AUTO/MAN,  |   |
  |   +-------------------+                     |  Bảo vệ khóa chéo)   |   |
  |   | 2 Bơm (IN / OUT)  | <===(Relay 2CH)==== |                       |   |
  |   +-------------------+                     +-----------+-----------+   |
  +---------------------------------------------------------|---------------+
                                                            | Wi-Fi (MQTT)
                                                            v
  +-------------------------------------------------------------------------+
  |                          TẦNG TRUYỀN THÔNG (BROKER)                     |
  |                     Eclipse Mosquitto MQTT Broker:1883                  |
  |        Topics: iot/data, iot/alert, iot/cmd/+, iot/ack, iot/status      |
  +---------------------------------------------------------+---------------+
                                                            | TCP/IP
                                                            v
  +-------------------------------------------------------------------------+
  |                             TẦNG DỊCH VỤ BACKEND                         |
  |  +-------------------------------------------------------------------+  |
  |  |                       Flask REST API Service                      |  |
  |  |  * mqtt_client: Nhận telemetry, phát lệnh điều khiển              |  |
  |  |  * Rule Engine (notify_rules): Đánh giá sự cố mực nước & bơm       |  |
  |  |  * Watchdog Service: Giám sát kết nối ESP32 & MQTT                |  |
  |  |  * Mail Worker: Xếp hàng & gửi cảnh báo qua Gmail SMTP            |  |
  |  |  * Chat Router & NLP: Trợ lý AI hỏi đáp dữ liệu ao & điều khiển  |  |
  |  +-------------------------------------------------------------------+  |
  |                         |                               |               |
  |                         v                               v               |
  |            +--------------------------+    +-------------------------+  |
  |            |   CƠ SỞ DỮ LIỆU CHÍNH   |    |       GMAIL SMTP        |  |
  |            |   MySQL 8.x / SQLite     |    |    (STARTTLS Port 587)  |  |
  |            +--------------------------+    +-------------------------+  |
  +---------------------------------------------------------+---------------+
                                                            | HTTP REST API
                                                            v
  +-------------------------------------------------------------------------+
  |                           TẦNG GIAO DIỆN NGƯỜI DÙNG                     |
  |   +----------------------------------+  +---------------------------+   |
  |   |       Web Dashboard 6 Trang      |  |     Trợ lý AI Chatbox     |   |
  |   | (Tổng quan, Điều khiển, Cấu hình,|  | (Hỏi đáp tiếng Việt, xem  |   |
  |   |  Cảnh báo, Lịch sử, Widget Mail) |  |  biến động, xác nhận lệnh)|   |
  |   +----------------------------------+  +---------------------------+   |
  +-------------------------------------------------------------------------+
```

---

## 7. NGUYÊN LÝ HOẠT ĐỘNG

### 7.1. Luồng thu thập dữ liệu cảm biến
1. Cảm biến **HC-SR04** phát xung siêu âm 40kHz từ chân `Trig`, sóng phản hồi đập vào mặt nước dội lại chân `Echo`. ESP32 đo thời gian xung bay về để tính khoảng cách $d$ (cm).
2. ESP32 tính toán phần trăm mực nước: $\text{water\_level} = \frac{d_{Empty} - d}{d_{Empty} - d_{Full}} \times 100\%$.
3. Cứ mỗi **2 giây**, ESP32 đóng gói bản tin JSON (`level`, `dist`, `in`, `out`, `auto`, `err`, `fault`, `rssi`, `up`) và publish lên topic `iot/data`.
4. Luồng `mqtt_client.py` tại backend nhận bản tin, ghi vào bảng `sensor_data` và cập nhật bộ nhớ cache `_latest`.
5. Web Dashboard định kỳ mỗi 5 giây (hoặc qua Event) gọi `/api/status` và `/api/sensor` để cập nhật biểu đồ và chỉ số.

### 7.2. Luồng điều khiển máy bơm
1. Người dùng thao tác nút Bật/Tắt trên Web hoặc Chatbox xác nhận lệnh điều khiển.
2. Web gửi request `POST /api/control` (hoặc `/api/chat/confirm`) tới Flask Backend.
3. Backend kiểm tra tính an toàn: Trạng thái kết nối MQTT, ESP32 phải Online, không cho phép bật cùng lúc 2 bơm. Lệnh được ghi vào bảng `control_logs` với trạng thái `SENT`.
4. Backend publish lệnh xuống topic `iot/cmd/{command}` với QoS 1.
5. ESP32 nhận lệnh, kiểm tra khóa chéo và thời gian trễ an toàn, kích hoạt chân GPIO điều khiển Relay, sau đó gửi phản hồi lên topic `iot/ack` (ví dụ: `ok:pump_in_on`).
6. Backend nhận tin từ `iot/ack`, cập nhật bản ghi trong `control_logs` thành `ACK_OK`.

### 7.3. Luồng cảnh báo & Gửi Email tự động (Rule Engine)
1. Mỗi khi có dữ liệu cảm biến mới hoặc sự kiện từ Watchdog, hàm `on_telemetry_received()` kích hoạt bộ quy tắc `evaluate_all_rules()`.
2. Nếu phát hiện vi phạm ngưỡng (mực nước $\ge 95\%$, $\le 5\%$, bơm không hiệu quả, mất tín hiệu ESP32):
   - Kiểm tra chống trùng: Nếu chưa có sự cố `ACTIVE` cùng loại, tạo mới bản ghi vào bảng `incidents`.
   - Sinh nội dung email HTML chuẩn hóa tiếng Việt, xếp hàng vào bảng `notification_outbox`.
3. Luồng ngầm `Mail Worker` quét các email `PENDING` trong outbox, kiểm tra hạn mức an toàn ($\le 10$ mail/giờ), kết nối Gmail SMTP gửi email đến chủ ao.
4. Khi điều kiện an toàn được tái lập (áp dụng hysteresis), hệ thống chuyển trạng thái sự cố sang `RECOVERED` và gửi email thông báo phục hồi.

---

## 8. THIẾT KẾ PHẦN CỨNG

### 8.1. Danh sách linh kiện
| STT | Tên linh kiện | Thông số kỹ thuật | Số lượng | Chức năng |
| :---: | :--- | :--- | :---: | :--- |
| 1 | **ESP32 NodeMCU** | 30 chân, ESP-WROOM-32, WiFi 2.4GHz | 01 | Vi điều khiển xử lý trung tâm |
| 2 | **Cảm biến HC-SR04** | Nguồn 5V DC, dải đo 2cm – 400cm, góc đo < 15° | 01 | Đo khoảng cách từ đỉnh ao tới mặt nước |
| 3 | **Relay Module 2 kênh** | 5V DC, kích mức thấp (Active LOW), chịu tải 10A 250VAC | 01 | Đóng ngắt Bơm cấp và Bơm thoát |
| 4 | **Điện trở $R_1$** | $1\text{ k}\Omega$ (1/4W) | 01 | Cầu phân áp hạ áp chân Echo |
| 5 | **Điện trở $R_2$** | $2\text{ k}\Omega$ (1/4W) | 01 | Cầu phân áp hạ áp chân Echo |
| 6 | **Nguồn cấp Adapter** | 5V DC - 2A ổn định | 01 | Cung cấp nguồn cho ESP32, Relay và HC-SR04 |
| 7 | **Máy bơm nước mini / LED**| 12V DC hoặc 220V AC (mô hình demo dùng 2 LED) | 02 | Mô phỏng Bơm cấp (IN) và Bơm thoát (OUT) |

### 8.2. Sơ đồ nối dây chi tiết
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
                  |  [GPIO 32] -----------------> IN1 (Relay 1 - Bơm cấp IN)
                  |  [GPIO 33] -----------------> IN2 (Relay 2 - Bơm thoát OUT)
                  |  [GND] ---------------------> GND (Relay 2CH)
                  |  [VIN / 5V] ----------------> VCC (Relay 2CH)
                  |                                             |
                  |  [GPIO 2]  -----------------> LED báo trạng thái
                  +---------------------------------------------+
```
> ⚠️ **LƯU Ý BẢO VỆ PHẦN CỨNG:** Chân `Echo` của cảm biến HC-SR04 xuất ra tín hiệu logic 5V. Chân GPIO của vi điều khiển ESP32 chỉ chịu được điện áp tối đa 3.3V. **Bắt buộc** phải sử dụng cầu phân áp với 2 điện trở $R_1 = 1\text{ k}\Omega$ và $R_2 = 2\text{ k}\Omega$:
> $$V_{out} = 5\text{V} \times \frac{2\text{ k}\Omega}{1\text{ k}\Omega + 2\text{ k}\Omega} \approx 3.33\text{V}$$

---

## 9. GIAO THỨC MQTT

Hệ thống sử dụng tiền tố topic mặc định là `iot` (có thể tùy biến qua biến `MQTT_TOPIC_PREFIX` trong file cấu hình).

### 9.1. Danh mục Topic MQTT
| Topic | Hướng truyền | QoS | Retain | Ý nghĩa |
| :--- | :---: | :---: | :---: | :--- |
| `iot/data` | ESP32 $\rightarrow$ Server | 0 | False | Dữ liệu cảm biến định kỳ mỗi 2 giây |
| `iot/alert` | ESP32 $\rightarrow$ Server | 1 | False | Cảnh báo sự cố khẩn cấp phát hiện từ phần cứng |
| `iot/cmd/+` | Server $\rightarrow$ ESP32 | 1 | False | Gửi lệnh điều khiển (bơm, chế độ, hiệu chỉnh, reset) |
| `iot/ack` | ESP32 $\rightarrow$ Server | 1 | False | Phản hồi xác nhận sau khi thực thi lệnh điều khiển |
| `iot/status` | ESP32 $\rightarrow$ Server | 1 | True | Trạng thái trực tuyến của ESP32 (`online` / `offline`) |
| `iot/cfg` | ESP32 $\rightarrow$ Server | 1 | True | ESP32 công bố cấu hình hiện tại đang lưu trong Flash |
| `iot/backend/status` | Server $\rightarrow$ ESP32 | 1 | True | Trạng thái hoạt động của Backend Flask (LWT) |

### 9.2. Định dạng bản tin dữ liệu mẫu (`iot/data`)
```json
{
  "level": 45.5,
  "dist": 56.7,
  "in": 0,
  "out": 0,
  "auto": 1,
  "err": 0,
  "fault": "none",
  "rssi": -55,
  "up": 5280,
  "id": "esp32-ao-01"
}
```

### 9.3. Danh sách lệnh điều khiển (`iot/cmd/+`)
- `iot/cmd/mode` $\rightarrow$ Payload: `AUTO` hoặc `MANUAL`
- `iot/cmd/pump_in` $\rightarrow$ Payload: `ON` hoặc `OFF`
- `iot/cmd/pump_out` $\rightarrow$ Payload: `ON` hoặc `OFF`
- `iot/cmd/threshold` $\rightarrow$ Payload: `inOn,inOff,outOn,outOff` (Ví dụ: `30,50,90,80`)
- `iot/cmd/calib` $\rightarrow$ Payload: `dEmpty,dFull` (Ví dụ: `100,10`)
- `iot/cmd/reset` $\rightarrow$ Payload: `RESET` (Xóa chốt lỗi an toàn)
- `iot/cmd/restart` $\rightarrow$ Payload: `RESTART` (Khởi động lại ESP32)
- `iot/cmd/get` $\rightarrow$ Payload: `GET` (Yêu cầu gửi lại cấu hình qua `iot/cfg`)

---

## 10. CẤU TRÚC THƯ MỤC
```text
d:\btl iot\
├── ao_nuoc\
│   └── ao_nuoc.ino              # Mã nguồn C/C++ nạp cho vi điều khiển ESP32
├── backend\
│   ├── notifications\           # Gói dịch vụ Cảnh báo Email tự động (Rule Engine)
│   │   ├── __init__.py
│   │   ├── mailer.py            # Kết nối Gmail SMTP, tạo template HTML, chống XSS
│   │   ├── notify_rules.py      # Bộ quy tắc đánh giá mực nước, bơm, cảm biến, phục hồi
│   │   ├── notifier.py          # Quản lý sự cố, chống spam, nhắc lại, xếp hàng outbox
│   │   ├── mail_worker.py       # Luồng ngầm quét outbox, gửi mail, thử lại lũy tiến
│   │   ├── notify_watchdog.py   # Luồng ngầm giám sát mất kết nối ESP32 & MQTT Broker
│   │   └── notify_api.py        # REST API quản lý người nhận, cài đặt email, lịch sử
│   ├── .env                     # File biến môi trường đang kích hoạt (MySQL, MQTT, Mail)
│   ├── .env.example             # File mẫu hướng dẫn thiết lập biến môi trường
│   ├── app.py                   # Điểm khởi chạy Flask REST API server và phục vụ Web
│   ├── chat.py                  # Blueprint cung cấp API cho Trợ lý AI (/api/chat)
│   ├── chat_router.py           # Bộ định tuyến hội thoại, NLP Fast Path, rào an toàn
│   ├── chat_tools.py            # 8 công cụ nghiệp vụ tra cứu dữ liệu & thực thi lệnh
│   ├── db.py                    # Module quản lý kết nối CSDL kép (MySQL 8.x + SQLite)
│   ├── mqtt_client.py           # Client kết nối Mosquitto MQTT, lưu trữ sensor_data
│   ├── esp32_simulator.py       # Bộ giả lập phần cứng ESP32 phục vụ test không cần mạch
│   ├── llm_client.py            # Client tích hợp Google Gemini REST API (tùy chọn)
│   └── requirements.txt         # Danh mục các thư viện Python phụ thuộc
├── database\
│   ├── 01_create_database.sql   # Kịch bản khởi tạo CSDL MySQL và toàn bộ các bảng
│   ├── 02_sample_data.sql       # Kịch bản nạp dữ liệu mẫu ban đầu để kiểm thử
│   └── notification_tables.sql  # Script tạo riêng 3 bảng cho hệ thống cảnh báo email
├── frontend\
│   ├── index.html               # Trang ứng dụng đơn SPA giao diện 6 trang
│   ├── style.css                # Toàn bộ định dạng giao diện người dùng
│   ├── app.js                   # Logic điều khiển, nạp dữ liệu, đồng bộ cấu hình, email
│   ├── api.js                   # Module gọi REST API backend
│   ├── chat.css                 # Định dạng riêng cho giao diện Trợ lý AI (Chatbox)
│   ├── chat.js                  # Xử lý hội thoại, gửi nhận tin nhắn, xác nhận điều khiển
│   └── chart.umd.min.js         # Thư viện Chart.js đóng gói cục bộ
├── mosquitto\
│   └── mosquitto.conf           # File cấu hình Mosquitto Broker mở cổng 1883
├── start.bat                    # Script 1-click tự động khởi động Flask Backend
├── start_simulator.bat          # Script 1-click tự động chạy bộ giả lập ESP32
├── run.bat                      # Phím tắt khởi động nhanh dự án
└── README.md                    # Tài liệu hướng dẫn toàn diện dự án này
```

---

## 11. CƠ SỞ DỮ LIỆU

Dự án áp dụng kiến trúc **Dual-Database Adapter** tại [db.py](file:///d:/btl%20iot/backend/db.py): Mặc định kết nối **MySQL 8.x**, nếu phát hiện máy chủ MySQL chưa khởi động hoặc gặp lỗi, hệ thống sẽ **tự động fallback sang SQLite nhúng (`data.db`)** mà không làm gián đoạn ứng dụng.

### 11.1. Danh mục các bảng dữ liệu
1. **`sensor_data`**: Lưu trữ lịch sử dữ liệu cảm biến định kỳ gửi về từ ESP32.
   - Các trường: `id`, `recorded_at`, `water_level`, `distance_cm`, `pump_in`, `pump_out`, `auto_mode`, `sensor_err`, `fault_code`, `rssi`, `uptime_sec`, `esp32_id`, `topic`.
2. **`alerts`**: Lưu trữ các sự cố, cảnh báo phục vụ hiển thị trên trang Cảnh báo Web.
   - Các trường: `id`, `created_at`, `updated_at`, `alert_code`, `message`, `severity` (DANGER/WARNING/INFO), `water_level`, `status` (UNRESOLVED/RESOLVED), `resolved_at`.
3. **`control_logs`**: Nhật ký các lệnh điều khiển gửi từ Web/Chatbox và phản hồi ACK từ ESP32.
   - Các trường: `id`, `sent_at`, `acked_at`, `command`, `payload`, `topic`, `status`, `initiated_by`, `client_ip`.
4. **`system_logs`**: Nhật ký vận hành hệ thống (khởi động máy chủ, kết nối MQTT, ngoại lệ).
   - Các trường: `id`, `logged_at`, `log_level`, `component`, `event_type`, `message`, `details`.
5. **`system_config`**: Lưu trữ cấu hình tham số hệ thống dạng Key-Value.
   - Các trường: `config_key`, `config_value`, `description`, `updated_at`.
6. **`notification_recipients`**: Danh bạ các địa chỉ email nhận thông báo cảnh báo.
   - Các trường: `id`, `email`, `name`, `enabled` (1=Bật, 0=Tắt), `created_at`, `updated_at`.
7. **`incidents`**: Quản lý vòng đời sự cố phục vụ Rule Engine và chống spam email.
   - Các trường: `id`, `event_key`, `severity`, `device_id`, `status` (ACTIVE/RECOVERED), `water_level_at_detect`, `started_at`, `recovered_at`, `last_notified_at`, `remind_count`, `source`, `notes`.
8. **`notification_outbox`**: Hàng đợi các email cần gửi đi qua Gmail SMTP.
   - Các trường: `id`, `incident_id`, `recipient_email`, `subject`, `body_html`, `status` (PENDING/SENT/FAILED), `scheduled_at`, `sent_at`, `attempt_count`, `last_error`.

---

## 12. CÀI ĐẶT VÀ CHẠY DỰ ÁN

### 12.1. Yêu cầu môi trường
- Hệ điều hành: Windows 10/11, Linux hoặc macOS.
- **Python 3.10** trở lên (Nhớ tích chọn `Add Python to PATH` khi cài đặt).
- **Eclipse Mosquitto 2.x** (MQTT Broker).
- *(Tùy chọn)* **MySQL Server 8.x** & MySQL Workbench (Nếu muốn dùng MySQL thay vì SQLite).

### 12.2. Hướng dẫn chạy nhanh (Không cần MySQL, Không cần phần cứng thật)
Đây là cách nhanh nhất để thử nghiệm đầy đủ toàn bộ Web, Chatbox AI và Điều khiển:
1. **Khởi động Mosquitto Broker:**
   Mở CMD với quyền Admin và gõ lệnh:
   ```cmd
   net start mosquitto
   ```
2. **Khởi động Backend Flask:**
   Nhấp đúp chuột vào file `start.bat` tại thư mục gốc dự án. Script sẽ tự tạo môi trường ảo/cài đặt thư viện phụ thuộc và khởi chạy máy chủ tại cổng `5000`.
3. **Khởi động bộ giả lập ESP32 Simulator:**
   Mở thêm 1 cửa sổ mới và nhấp đúp file `start_simulator.bat`. Simulator sẽ tự động phát dữ liệu ao nuôi lên MQTT.
4. **Mở trình duyệt:**
   Truy cập địa chỉ: 👉 **`http://localhost:5000`**

### 12.3. Hướng dẫn chạy với MySQL Server 8.x
1. Khởi động MySQL Server qua MySQL Workbench hoặc dịch vụ Windows.
2. Mở file `database/01_create_database.sql` trong MySQL Workbench và bấm nút tia sét ⚡ để tạo database `iot_ao_nuoi` và tất cả các bảng.
3. Chỉnh sửa thông tin tài khoản MySQL trong file `backend/.env`:
   ```ini
   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=iot_ao_nuoi
   DB_USER=root
   DB_PASS=mật_khẩu_mysql_của_bạn
   ```
4. Khởi chạy `start.bat` và mở trình duyệt tại `http://localhost:5000`.

### 12.4. Hướng dẫn nạp code vào mạch ESP32 thật
1. Mở phần mềm **Arduino IDE**.
2. Cài đặt Board Package ESP32 trong *Preferences*:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Cài đặt thư viện **`PubSubClient`** của Nick O'Leary từ mục *Library Manager*.
4. Mở file `ao_nuoc/ao_nuoc.ino`, chỉnh sửa cấu hình mạng WiFi và IP máy tính chạy Mosquitto:
   ```cpp
   const char* WIFI_SSID = "Tên_WiFi_Nhà_Bạn";
   const char* WIFI_PASS = "Mật_Khẩu_WiFi";
   const char* MQTT_HOST = "192.168.1.100"; // Thay bằng IP LAN máy tính chạy Mosquitto
   ```
5. Kết nối ESP32 qua cáp MicroUSB, chọn đúng cổng COM và nhấn nút **Upload** (Mũi tên sang phải).

---

## 13. HƯỚNG DẪN SỬ DỤNG WEB

### 13.1. Trang "Tổng quan"
- Xem nhanh 4 chỉ số trạng thái: Mực nước hiện tại, Cường độ sóng WiFi ESP32, Chế độ hoạt động và Trạng thái Broker MQTT.
- Theo dõi đồ thị mực nước thời gian thực theo 5 mốc thời gian: 30 phút, 1 giờ, 6 giờ, 7 ngày, 30 ngày.
- **Widget Cảnh báo qua Email:** Nằm ở góc dưới bên phải, cho phép bật/tắt nhận email cảnh báo bằng nút gạt Toggle Switch, thay đổi nhanh địa chỉ email nhận thư, bấm **`💾 Lưu`** hoặc bấm **`✈️ Gửi thử`** để kiểm tra gửi mail tức thời.

### 13.2. Trang "Điều khiển"
- **Chuyển chế độ:** Bấm nút chuyển giữa chế độ `Tự động (AUTO)` và `Thủ công (MANUAL)`.
- **Đóng ngắt máy bơm:** Khi ở chế độ `MANUAL`, người dùng có thể chủ động bấm bật/tắt Bơm cấp (IN) và Bơm thoát (OUT). Giao diện có cơ chế khóa an toàn: không thể bật bơm này khi bơm kia đang hoạt động.
- **Theo dõi nhật ký lệnh:** Xem phản hồi xác nhận (ACK) từ vi điều khiển theo thời gian thực.

### 13.3. Trang "Cấu hình"
- Thiết lập ngưỡng đóng ngắt tự động của 2 bơm ($in_{On}, in_{Off}, out_{On}, out_{Off}$).
- Hiệu chỉnh cảm biến khoảng cách khi ao cạn ($d_{Empty}$) và khi ao đầy ($d_{Full}$).
- Cài đặt thời gian chạy bơm tối đa để chống cháy bơm và chu kỳ gửi dữ liệu MQTT.
- **Mục Cấu hình Cảnh báo Email:** Thêm, xóa, xem danh sách các địa chỉ email của kỹ thuật viên và chủ ao nhận cảnh báo.
- Nút *Xóa lỗi cảnh báo (Reset)* và *Khởi động lại ESP32 từ xa*.

### 13.4. Trang "Cảnh báo"
- Thống kê phân loại cảnh báo trong 24 giờ theo mức độ: *Nguy hiểm* (Màu đỏ), *Cảnh báo* (Màu vàng), *Thông tin* (Màu xanh).
- Lọc lịch sử sự cố theo khoảng ngày tháng và trạng thái đã xử lý hay chưa.

### 13.5. Trang "Lịch sử dữ liệu"
- Xem toàn bộ dữ liệu lịch sử đo đạc từ cơ sở dữ liệu.
- Lọc theo ngày tháng hoặc các mốc chọn nhanh (*Hôm nay*, *7 ngày*, *30 ngày*).
- Tải toàn bộ dữ liệu thống kê về máy qua 2 nút: **`Xuất CSV`** và **`Xuất Excel (.xlsx)`**.

### 13.6. Trang "Trợ lý AI (Chatbox)"
- Hỏi đáp bằng tiếng Việt tự nhiên:
  - *"Ao còn nước không?"* $\rightarrow$ Trả lời mực nước tức thời, khoảng cách cảm biến và trạng thái bơm.
  - *"Trong 30 phút qua nước tăng bao nhiêu?"* $\rightarrow$ Phân tích biến động, xu hướng tăng/giảm và Min/Max.
  - *"Bật bơm cấp nước vào ao"* $\rightarrow$ Xuất hiện hộp thoại xác nhận lệnh điều khiển an toàn có nút `Xác nhận thực hiện` và `Hủy bỏ`.
  - *"Nước ao có bị phèn không?"*, *"độ ẩm ao thế nào?"* $\rightarrow$ AI giải thích rõ ràng hệ thống chưa có cảm biến đo thông số này và hướng dẫn các câu hỏi đúng phạm vi.

---

## 14. API BACKEND

Tất cả các API đều giao tiếp qua định dạng JSON chuẩn:

### 14.1. Giám sát & Dữ liệu cảm biến
- `GET /api/status`: Lấy trạng thái tổng quan hệ thống, bản tin mới nhất, cấu hình runtime và tình trạng kết nối.
- `GET /api/sensor?minutes=30&limit=500`: Lấy chuỗi dữ liệu cảm biến phục vụ vẽ biểu đồ và phân tích biến động.
- `GET /api/chart?period=day`: Lấy dữ liệu tổng hợp Min, Max, Avg theo giờ hoặc ngày.

### 14.2. Cảnh báo & Nhật ký
- `GET /api/alerts?severity=DANGER&status=UNRESOLVED`: Lấy danh sách cảnh báo có phân trang và bộ lọc.
- `GET /api/logs?component=mqtt`: Tra cứu nhật ký sự kiện hệ thống.
- `GET /api/control_logs?limit=20`: Tra cứu nhật ký các lệnh điều khiển và thời gian nhận ACK.

### 14.3. Điều khiển & Cấu hình
- `POST /api/control`: Gửi lệnh điều khiển xuống ESP32.
  - Body: `{"command": "pump_in", "payload": "ON"}` hoặc `{"command": "mode", "payload": "AUTO"}`.
- `GET /api/config`: Đọc cấu hình hệ thống từ database và ESP32.
- `POST /api/config`: Lưu và phát cấu hình mới xuống ESP32 qua MQTT.

### 14.4. Trợ lý AI (Chatbox)
- `POST /api/chat`: Tiếp nhận câu hỏi ngôn ngữ tự nhiên từ người dùng.
  - Body: `{"message": "Ao còn nước không?"}`
- `POST /api/chat/confirm`: Xác nhận thực thi lệnh điều khiển từ hộp thoại chat.
  - Body: `{"action_id": "c98ab5ae"}`
- `POST /api/chat/cancel`: Hủy bỏ lệnh điều khiển đang chờ xác nhận.
- `GET /api/chat/health`: Kiểm tra sức khỏe dịch vụ chat và trạng thái LLM.

### 14.5. Cảnh báo qua Email (Rule Engine)
- `GET /api/notify/settings`: Đọc cấu hình bật/tắt gửi mail và email mặc định.
- `POST /api/notify/settings`: Cập nhật cấu hình gửi email (`mail_enabled`, `recipient_default`).
- `GET /api/notify/recipients`: Danh sách người nhận email cảnh báo.
- `POST /api/notify/recipients`: Thêm địa chỉ email người nhận mới.
- `DELETE /api/notify/recipients/<id>`: Xóa người nhận khỏi danh bạ.
- `POST /api/notify/test`: Gửi email thử nghiệm kết nối SMTP tới địa chỉ chỉ định.
- `GET /api/notify/logs`: Xem lịch sử hàng đợi và trạng thái gửi thư (PENDING/SENT/FAILED).

---

## 15. CẢNH BÁO VÀ ĐIỀU KHIỂN

### 15.1. Bảng quy tắc đóng ngắt tự động (Chế độ AUTO)
```text
  100% +---------------------------------------------+
       |   VÙNG NGUY CƠ TRÀN AO (limit_high: 95%)    | --> Kích hoạt Cảnh báo DANGER & Gửi Email
   90% + - - - - - - - - - - - - - - - - - - - - - - +
       |   BẬT BƠM THOÁT OUT (out_on_pct: 90%)       | --> Bơm thoát nước ra ngoài ao
   80% + - - - - - - - - - - - - - - - - - - - - - - +
       |   TẮT BƠM THOÁT OUT (out_off_pct: 80%)      | --> Dừng bơm thoát, nước ổn định
       |                                             |
       |             VÙNG NƯỚC AN TOÀN               | --> Cả hai bơm đều TẮT
       |                                             |
   50% + - - - - - - - - - - - - - - - - - - - - - - +
       |   TẮT BƠM CẤP IN (in_off_pct: 50%)          | --> Đạt ngưỡng mong muốn, dừng cấp
   30% + - - - - - - - - - - - - - - - - - - - - - - +
       |   BẬT BƠM CẤP IN (in_on_pct: 30%)           | --> Tự động bơm cấp nước vào ao
    5% + - - - - - - - - - - - - - - - - - - - - - - +
       |   VÙNG NGUY CƠ CẠN AO (limit_low: 5%)       | --> Kích hoạt Cảnh báo DANGER & Gửi Email
    0% +---------------------------------------------+
```

### 15.2. Các cơ chế an toàn và khóa bảo vệ thiết bị
1. **Khóa chéo liên động (Interlock):**
   Phần mềm firmware trên ESP32 và API backend kiểm tra khóa chéo: nếu Bơm cấp (IN) đang bật thì lệnh bật Bơm thoát (OUT) sẽ bị từ chối ngay lập tức và ngược lại.
2. **Thời gian trễ đổi trạng thái bơm (`switch_delay` = 3s):**
   Khi chuyển từ Bơm IN sang Bơm OUT, hệ thống bắt buộc tắt bơm cũ và nghỉ tối thiểu 3 giây trước khi kích hoạt bơm mới để triệt tiêu dòng phản kháng động cơ.
3. **Bảo vệ chạy quá giờ (`max_run` = 20 phút):**
   Nếu máy bơm chạy liên tục vượt quá 20 phút mà mực nước chưa đạt ngưỡng ngắt, ESP32 sẽ tự động ngắt bơm khẩn cấp, khóa chốt lỗi `pump_overrun` để bảo vệ chống cháy động cơ.
4. **Phát hiện bơm chạy không hiệu quả (`no_flow`):**
   Nếu bơm chạy liên tục $\ge 3$ phút nhưng độ biến thiên mực nước $< 0.3\%$, hệ thống tự động ghi nhận cảnh báo `NO_FLOW_IN` / `NO_FLOW_OUT` và gửi email thông báo sự cố nghẹt ống hoặc cạn nguồn cấp.
5. **Cơ chế an toàn 2 bước của Chatbox AI:**
   Mọi lệnh tác động đến máy bơm qua hội thoại AI đều không được thực thi ngay mà phải thông qua một bước tạo mã hành động tạm thời (`action_id`) và yêu cầu người dùng bấm nút **Xác nhận** rõ ràng trên màn hình.
