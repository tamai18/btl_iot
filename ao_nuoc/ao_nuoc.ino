// ============================================================================
//  GIAM SAT & DIEU KHIEN MUC NUOC AO
//  ESP32 (30 chan) + HC-SR04 + Relay 2 kenh (2 bom: vao / ra) + MQTT (Mosquitto)
//
//  Thu vien can cai (Library Manager): "PubSubClient" (Nick O'Leary)
//  Board: ESP32 Dev Module
//
//  P = "iot-ao-demo-123"; 
//  Topic (P = tien to):
//    ESP32 -> broker : P/data   (JSON, moi 2s hoac khi co thay doi)
//                      P/status (online/offline, retained, LWT)
//                      P/alert  (JSON {"code","msg"}, khi co canh bao)
//                      P/cfg    (JSON cau hinh hien tai, retained)
//                      P/ack    (ket qua xu ly lenh)
//    broker -> ESP32 : P/cmd/mode        AUTO | MANUAL
//                      P/cmd/pump_in     ON | OFF   (tu dong chuyen MANUAL)
//                      P/cmd/pump_out    ON | OFF   (tu dong chuyen MANUAL)
//                      P/cmd/threshold   "inOn,inOff,outOn,outOff"  vd: 30,50,90,80
//                      P/cmd/calib       "dEmpty,dFull" (cm)        vd: 100,10
//                      P/cmd/calib_empty [cm]  (de trong = dung khoang cach hien tai)
//                      P/cmd/calib_full  [cm]
//                      P/cmd/reset       xoa loi chot (fault) va canh bao
//                      P/cmd/get         gui lai cfg
//                      P/cmd/restart     khoi dong lai ESP32
// ============================================================================
#include <WiFi.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <esp_task_wdt.h>

// ===================== CAU HINH MANG =====================
const char* WIFI_SSID = "TEN_WIFI";
const char* WIFI_PASS = "MAT_KHAU";
const char* MQTT_HOST = "192.168.1.100";   // IP may chay Mosquitto (cung mang Wi-Fi)
const uint16_t MQTT_PORT = 1883;
const char* MQTT_USER = "esp32";
const char* MQTT_PASS = "esp32pass";       // trung voi tai khoan tren Mosquitto
const char* P = "iot-ao-demo-123";         // tien to topic: DOI thanh chuoi rieng

// ===================== CHAN KET NOI =====================
#define TRIG_PIN       26
#define ECHO_PIN       27                  // HC-SR04 echo 5V -> PHAI chia ap xuong 3.3V
#define RELAY_IN_PIN   32                  // bom vao
#define RELAY_OUT_PIN  33                  // bom ra
#define LED_PIN        2                   // LED tren board: sang khi co canh bao

const uint8_t RELAY_ON  = LOW;             // relay kich muc thap; doi thanh HIGH neu nguoc
const uint8_t RELAY_OFF = (RELAY_ON == LOW) ? HIGH : LOW;

// ===================== THAM SO MAC DINH (luu duoc vao flash) =====================
const float DEF_D_EMPTY = 100.0;           // cm: khoang cach cam bien -> mat nuoc khi ao can (0%)
const float DEF_D_FULL  = 10.0;            // cm: khi ao day (100%)
const float DEF_IN_ON   = 30, DEF_IN_OFF  = 50;   // % : bom vao bat < 30, tat >= 50
const float DEF_OUT_ON  = 90, DEF_OUT_OFF = 80;   // % : bom ra bat > 90, tat <= 80

// ===================== THAM SO AN TOAN =====================
const float LIMIT_HIGH = 95.0;             // % : >= thi cam / dung bom vao (chong tran)
const float LIMIT_LOW  = 5.0;              // % : <= thi cam / dung bom ra (chong chay can)
const unsigned long MAX_RUN_MS      = 20UL * 60UL * 1000UL;  // bom chay lien tuc toi da
const unsigned long SWITCH_DELAY_MS = 3000UL;                // nghi giua 2 bom khi doi chieu
const unsigned long MIN_REST_MS     = 10000UL;               // nghi toi thieu truoc khi bat lai (tu dong)
const unsigned long NOFLOW_MS       = 120000UL;              // sau 2 phut ma muc nuoc khong doi -> loi
const float         NOFLOW_MIN_PCT  = 0.5;                   // muc nuoc phai doi it nhat 0.5%
const unsigned long MANUAL_FAILSAFE_MS = 120000UL;           // mat MQTT 2 phut o che do tay -> ve AUTO
const unsigned long MEASURE_MS = 2000UL;
const unsigned long PUBLISH_MS = 2000UL;
const int SENSOR_FAIL_COUNT = 3;           // so lan do loi lien tiep de ket luan hong cam bien
const int SENSOR_OK_COUNT   = 3;           // so lan do tot lien tiep de het loi

// ===================== BIEN TOAN CUC =====================
WiFiClient net;
PubSubClient mqtt(net);
Preferences prefs;

struct Config {
  float dEmpty, dFull;
  float inOn, inOff, outOn, outOff;
} cfg;

enum { PUMP_IN = 0, PUMP_OUT = 1 };
const uint8_t RELAY_PIN[2] = { RELAY_IN_PIN, RELAY_OUT_PIN };
const char* PUMP_NAME[2]   = { "in", "out" };

bool pumpOn[2] = { false, false };
unsigned long pumpStart[2] = { 0, 0 }, pumpStop[2] = { 0, 0 };
unsigned long flowRefT[2] = { 0, 0 };
float flowRefL[2] = { 0, 0 };

bool autoMode = true;
bool haveLevel = false;
bool sensorErr = false;
bool fault = false;                        // loi chot, can lenh reset
const char* faultMsg = "none";
float level = 0, dist = 0;
int badCount = 0, goodCount = 0;

bool aSensor = false, aHigh = false, aLow = false;   // trang thai canh bao (de bao 1 lan)
bool dirty = true;                         // can gui data ngay
unsigned long lastMeasure = 0, lastPub = 0, lastMqttOk = 0;
const char* rejectReason = "";

// ===================== TIEN ICH MQTT =====================
void pub(const char* sub, const char* payload, bool retain = false) {
  if (!mqtt.connected()) return;
  char tp[96];
  snprintf(tp, sizeof(tp), "%s/%s", P, sub);
  mqtt.publish(tp, payload, retain);
}

void sendAlert(const char* code, const char* msg) {
  char b[160];
  snprintf(b, sizeof(b), "{\"code\":\"%s\",\"msg\":\"%s\"}", code, msg);
  pub("alert", b);
  Serial.print("[ALERT] "); Serial.println(b);
}

void ack(const char* s) { pub("ack", s); Serial.print("[ACK] "); Serial.println(s); }

// canh bao theo suon len: chi bao khi vua xuat hien
void edgeAlert(bool& flag, bool cond, const char* code, const char* msg) {
  if (cond && !flag) { flag = true; sendAlert(code, msg); dirty = true; }
  else if (!cond && flag) { flag = false; dirty = true; }
}

// ===================== LUU / DOC CAU HINH =====================
void loadCfg() {
  prefs.begin("ao", false);
  cfg.dEmpty = prefs.getFloat("dEmpty", DEF_D_EMPTY);
  cfg.dFull  = prefs.getFloat("dFull",  DEF_D_FULL);
  cfg.inOn   = prefs.getFloat("inOn",   DEF_IN_ON);
  cfg.inOff  = prefs.getFloat("inOff",  DEF_IN_OFF);
  cfg.outOn  = prefs.getFloat("outOn",  DEF_OUT_ON);
  cfg.outOff = prefs.getFloat("outOff", DEF_OUT_OFF);
}

void saveCfg() {
  prefs.putFloat("dEmpty", cfg.dEmpty);
  prefs.putFloat("dFull",  cfg.dFull);
  prefs.putFloat("inOn",   cfg.inOn);
  prefs.putFloat("inOff",  cfg.inOff);
  prefs.putFloat("outOn",  cfg.outOn);
  prefs.putFloat("outOff", cfg.outOff);
}

void publishCfg() {
  char b[220];
  snprintf(b, sizeof(b),
    "{\"dEmpty\":%.1f,\"dFull\":%.1f,\"inOn\":%.1f,\"inOff\":%.1f,\"outOn\":%.1f,\"outOff\":%.1f,"
    "\"maxRunMin\":%lu,\"limitHigh\":%.0f,\"limitLow\":%.0f}",
    cfg.dEmpty, cfg.dFull, cfg.inOn, cfg.inOff, cfg.outOn, cfg.outOff,
    MAX_RUN_MS / 60000UL, LIMIT_HIGH, LIMIT_LOW);
  pub("cfg", b, true);
}

bool thresholdValid(float a, float b, float c, float d) {
  // inOn < inOff < outOff < outOn, nam trong 0..100
  return a >= 0 && d <= 100 && c <= 100 && a < b && b < d && d < c;
}

// ===================== DO KHOANG CACH =====================
float readDist() {
  digitalWrite(TRIG_PIN, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long t = pulseIn(ECHO_PIN, HIGH, 30000UL);
  if (t == 0) return -1;
  float d = t * 0.0343f / 2.0f;
  return (d < 2.0f || d > 400.0f) ? -1 : d;
}

// trung vi 5 lan do, bo qua lan do loi; can it nhat 3 mau hop le
float median5() {
  float m[5]; int n = 0;
  for (int i = 0; i < 5; i++) {
    float d = readDist();
    if (d > 0) m[n++] = d;
    delay(30);
  }
  if (n < 3) return -1;
  for (int i = 0; i < n - 1; i++)
    for (int j = i + 1; j < n; j++)
      if (m[j] < m[i]) { float x = m[i]; m[i] = m[j]; m[j] = x; }
  return m[n / 2];
}

// ===================== DIEU KHIEN BOM =====================
// tra ve nullptr neu duoc phep bat, nguoc lai tra ve ly do tu choi
const char* canStart(int p) {
  int o = 1 - p;
  if (fault)                 return "fault";
  if (sensorErr)             return "sensor_error";
  if (!haveLevel)            return "no_level";
  if (pumpOn[o])             return "interlock";
  if (millis() - pumpStop[o] < SWITCH_DELAY_MS) return "switch_delay";
  if (p == PUMP_IN  && level >= LIMIT_HIGH) return "high_limit";
  if (p == PUMP_OUT && level <= LIMIT_LOW)  return "low_limit";
  return nullptr;
}

bool setPump(int p, bool on) {
  if (on == pumpOn[p]) return true;
  if (on) {
    const char* r = canStart(p);
    if (r) { rejectReason = r; return false; }
  }
  pumpOn[p] = on;
  digitalWrite(RELAY_PIN[p], on ? RELAY_ON : RELAY_OFF);
  unsigned long now = millis();
  if (on) { pumpStart[p] = now; flowRefT[p] = now; flowRefL[p] = level; }
  else    { pumpStop[p] = now; }
  dirty = true;
  Serial.printf("[PUMP] %s -> %s\n", PUMP_NAME[p], on ? "ON" : "OFF");
  return true;
}

void stopAll() { setPump(PUMP_IN, false); setPump(PUMP_OUT, false); }

void setFault(const char* code, const char* msg) {
  stopAll();
  fault = true; faultMsg = code;
  sendAlert(code, msg);
  dirty = true;
}

// ===================== XU LY LENH TU WEB =====================
bool isOn(const String& m) { return m == "ON" || m == "1" || m == "on"; }

void onMsg(char* t, byte* b, unsigned int n) {
  String m; m.reserve(n);
  for (unsigned int i = 0; i < n; i++) m += (char)b[i];
  m.trim();
  String s(t);

  if (s.endsWith("/cmd/mode")) {
    if (m == "AUTO")        { autoMode = true;  ack("ok:mode=AUTO"); }
    else if (m == "MANUAL") { autoMode = false; stopAll(); ack("ok:mode=MANUAL"); }
    else ack("err:mode");
    dirty = true;
  }
  else if (s.endsWith("/cmd/pump_in") || s.endsWith("/cmd/pump_out")) {
    int p = s.endsWith("/cmd/pump_in") ? PUMP_IN : PUMP_OUT;
    bool want = isOn(m);
    autoMode = false;                        // lenh tay -> chuyen sang MANUAL
    if (setPump(p, want)) ack(want ? "ok:pump=ON" : "ok:pump=OFF");
    else { char b2[48]; snprintf(b2, sizeof(b2), "rejected:%s", rejectReason); ack(b2); }
    dirty = true;
  }
  else if (s.endsWith("/cmd/threshold")) {
    float a, b2, c, d;
    if (sscanf(m.c_str(), "%f,%f,%f,%f", &a, &b2, &c, &d) == 4 && thresholdValid(a, b2, c, d)) {
      cfg.inOn = a; cfg.inOff = b2; cfg.outOn = c; cfg.outOff = d;
      saveCfg(); publishCfg(); ack("ok:threshold");
    } else ack("err:threshold (can inOn<inOff<outOff<outOn, 0..100)");
  }
  else if (s.endsWith("/cmd/calib_empty") || s.endsWith("/cmd/calib_full")) {
    bool isEmpty = s.endsWith("/cmd/calib_empty");
    float v = m.length() ? m.toFloat() : dist;
    if (v < 2 || v > 400 || (!m.length() && (!haveLevel || sensorErr))) { ack("err:calib"); return; }
    float e = isEmpty ? v : cfg.dEmpty, f = isEmpty ? cfg.dFull : v;
    if (e - f < 5) { ack("err:calib (dEmpty phai > dFull it nhat 5cm)"); return; }
    cfg.dEmpty = e; cfg.dFull = f; saveCfg(); publishCfg(); ack("ok:calib");
  }
  else if (s.endsWith("/cmd/calib")) {
    float e, f;
    if (sscanf(m.c_str(), "%f,%f", &e, &f) == 2 && f >= 2 && e <= 400 && e - f >= 5) {
      cfg.dEmpty = e; cfg.dFull = f; saveCfg(); publishCfg(); ack("ok:calib");
    } else ack("err:calib");
  }
  else if (s.endsWith("/cmd/reset")) {
    fault = false; faultMsg = "none"; badCount = 0;
    aSensor = aHigh = aLow = false;
    ack("ok:reset"); dirty = true;
  }
  else if (s.endsWith("/cmd/get")) { publishCfg(); dirty = true; }
  else if (s.endsWith("/cmd/restart")) { ack("ok:restart"); mqtt.loop(); delay(300); ESP.restart(); }
}

// ===================== MANG =====================
void mqttConnect() {
  char willTp[96], cmdTp[96];
  snprintf(willTp, sizeof(willTp), "%s/status", P);
  snprintf(cmdTp, sizeof(cmdTp), "%s/cmd/#", P);
  String id = "esp32-ao-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  if (mqtt.connect(id.c_str(), MQTT_USER, MQTT_PASS, willTp, 0, true, "offline")) {
    mqtt.publish(willTp, "online", true);
    mqtt.subscribe(cmdTp);
    publishCfg();
    dirty = true;
    Serial.println("[MQTT] connected");
  } else {
    Serial.printf("[MQTT] failed rc=%d\n", mqtt.state());
  }
}

void netLoop() {
  static unsigned long lastWifi = 0, lastMq = 0;
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWifi > 10000UL) {
      lastWifi = millis();
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASS);
    }
    return;
  }
  if (!mqtt.connected() && millis() - lastMq > 5000UL) {
    lastMq = millis();
    mqttConnect();
  }
  mqtt.loop();
  if (mqtt.connected()) lastMqttOk = millis();
}

// ===================== DO + AN TOAN + TU DONG =====================
void measure() {
  float d = median5();
  if (d > 0) {
    dist = d; goodCount++; badCount = 0;
    if (goodCount >= SENSOR_OK_COUNT) sensorErr = false;
    level = constrain((cfg.dEmpty - dist) / (cfg.dEmpty - cfg.dFull) * 100.0f, 0.0f, 100.0f);
    haveLevel = true;
  } else {
    badCount++; goodCount = 0;
    if (badCount >= SENSOR_FAIL_COUNT) sensorErr = true;
  }
}

void safetyChecks() {
  edgeAlert(aSensor, sensorErr, "sensor_error", "Loi cam bien HC-SR04");
  if (sensorErr) { stopAll(); return; }
  if (!haveLevel) return;

  edgeAlert(aHigh, level >= LIMIT_HIGH, "high_level", "Muc nuoc qua cao");
  edgeAlert(aLow,  level <= LIMIT_LOW,  "low_level",  "Muc nuoc qua thap");

  // chong tran / chong chay can (ap dung ca che do tay)
  if (pumpOn[PUMP_IN]  && level >= LIMIT_HIGH) setPump(PUMP_IN,  false);
  if (pumpOn[PUMP_OUT] && level <= LIMIT_LOW)  setPump(PUMP_OUT, false);

  unsigned long now = millis();
  for (int p = 0; p < 2; p++) {
    if (!pumpOn[p]) continue;
    // chay qua thoi gian cho phep
    if (now - pumpStart[p] > MAX_RUN_MS) {
      setFault("pump_overrun", "Bom chay qua thoi gian cho phep"); return;
    }
    // khong co dong chay: muc nuoc khong thay doi sau NOFLOW_MS
    if (now - flowRefT[p] >= NOFLOW_MS) {
      float delta = (p == PUMP_IN) ? (level - flowRefL[p]) : (flowRefL[p] - level);
      if (delta < NOFLOW_MIN_PCT) {
        setFault(p == PUMP_IN ? "no_flow_in" : "no_flow_out",
                 "Bom chay nhung muc nuoc khong doi (kiem tra bom/ong/nguon nuoc)");
        return;
      }
      flowRefT[p] = now; flowRefL[p] = level;
    }
  }
}

void autoControl() {
  if (!autoMode || fault || sensorErr || !haveLevel) return;
  unsigned long now = millis();

  if (!pumpOn[PUMP_IN]) {
    if (level < cfg.inOn && now - pumpStop[PUMP_IN] >= MIN_REST_MS) setPump(PUMP_IN, true);
  } else if (level >= cfg.inOff) setPump(PUMP_IN, false);

  if (!pumpOn[PUMP_OUT]) {
    if (level > cfg.outOn && now - pumpStop[PUMP_OUT] >= MIN_REST_MS) setPump(PUMP_OUT, true);
  } else if (level <= cfg.outOff) setPump(PUMP_OUT, false);
}

// mat ket noi MQTT qua lau khi dang o che do tay -> tat bom, tro ve AUTO
void commFailsafe() {
  if (!autoMode && !mqtt.connected() && millis() - lastMqttOk > MANUAL_FAILSAFE_MS) {
    stopAll();
    autoMode = true;
    dirty = true;
    Serial.println("[FAILSAFE] mat MQTT -> ve AUTO");
  }
}

void publishData() {
  lastPub = millis(); dirty = false;
  char buf[260];
  snprintf(buf, sizeof(buf),
    "{\"level\":%.1f,\"dist\":%.1f,\"in\":%d,\"out\":%d,\"auto\":%d,\"err\":%d,"
    "\"fault\":\"%s\",\"rssi\":%d,\"up\":%lu}",
    level, dist, pumpOn[PUMP_IN], pumpOn[PUMP_OUT], autoMode, sensorErr,
    faultMsg, WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0, millis() / 1000UL);
  pub("data", buf);
  Serial.println(buf);
}

// ===================== SETUP / LOOP =====================
void setup() {
  Serial.begin(115200);

  // dat relay ve OFF TRUOC khi bat che do OUTPUT de tranh bom nhay luc khoi dong
  for (int i = 0; i < 2; i++) { digitalWrite(RELAY_PIN[i], RELAY_OFF); pinMode(RELAY_PIN[i], OUTPUT); }
  pinMode(TRIG_PIN, OUTPUT); pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  for (int i = 0; i < 2; i++) pumpStop[i] = millis() - 60000UL;

  loadCfg();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMsg);
  mqtt.setBufferSize(512);
  mqtt.setSocketTimeout(5);
  lastMqttOk = millis();

  // watchdog 30s: tu khoi dong lai neu chuong trinh bi treo
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t wdt = { .timeout_ms = 30000, .idle_core_mask = 0, .trigger_panic = true };
  esp_task_wdt_reconfigure(&wdt);
#else
  esp_task_wdt_init(30, true);
#endif
  esp_task_wdt_add(NULL);
}

void loop() {
  esp_task_wdt_reset();
  netLoop();

  if (millis() - lastMeasure >= MEASURE_MS) {
    lastMeasure = millis();
    measure();
    safetyChecks();
    autoControl();
    dirty = true;
  }

  commFailsafe();
  if (dirty || millis() - lastPub >= PUBLISH_MS) publishData();

  digitalWrite(LED_PIN, (fault || sensorErr || aHigh || aLow) ? HIGH : LOW);
}
