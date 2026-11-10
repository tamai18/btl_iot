// ============================================================================
//  api.js – Giao tiếp với Flask REST API
// ============================================================================
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:5000'
  : '';   // same origin khi deploy

const isDemoMode = () => {
  return new URLSearchParams(window.location.search).get('demo') === '1' || window.__DEMO_MODE__ === true;
};

const api = {
  async get(path) {
    const res = await fetch(`${API_BASE}${path}`);
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = (data && data.error) ? data.error : `HTTP ${res.status}`;
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  },
  async post(path, body = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = (data && data.error) ? data.error : `HTTP ${res.status}`;
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  },

  // ── Endpoints ──────────────────────────────────────────────────────────
  status:      ()       => api.get('/api/status'),
  sensor:      (p={})  => api.get('/api/sensor?'  + new URLSearchParams(p)),
  alerts:      (p={})  => api.get('/api/alerts?'  + new URLSearchParams(p)),
  chart:       (period)=> api.get('/api/chart?period=' + period),
  logs:        (p={})  => api.get('/api/logs?'    + new URLSearchParams(p)),
  controlLogs: (p={})  => api.get('/api/control_logs?' + new URLSearchParams(p)),
  config:      ()      => api.get('/api/config'),
  control:     (command, payload) => api.post('/api/control', { command, payload }),
  insights:    (demo=false) => api.get('/api/dashboard/insights' + (demo ? '?demo=1' : '')),
  saveConfig:  (data)  => api.post('/api/config', data),

  // ── Notify Endpoints ───────────────────────────────────────────────────
  notify: {
    getRecipients: () => api.get('/api/notify/recipients'),
    addRecipient: (email, name) => api.post('/api/notify/recipients', { email, name }),
    deleteRecipient: (id) => fetch(`${API_BASE}/api/notify/recipients/${id}`, { method: 'DELETE' }).then(r => r.json()),
    getSettings: () => api.get('/api/notify/settings'),
    saveSettings: (data) => api.post('/api/notify/settings', data),
    sendTest: (email) => api.post('/api/notify/test', { email }),
    getLogs: (p = {}) => api.get('/api/notify/logs?' + new URLSearchParams(p)),
    getIncidents: (p = {}) => api.get('/api/notify/incidents?' + new URLSearchParams(p)),
  },
};

// ── Demo / Fallback data (khi chưa có backend) ──────────────────────────────
const demo = {
  status() {
    const lvl = 45.5;
    return {
      ok: true,
      mqtt_connected: true, esp32_status: 'online',
      server_time: new Date().toISOString().slice(0,19),
      last_record: {
        water_level: lvl, distance_cm: 56.7,
        pump_in: 0, pump_out: 0,
        auto_mode: 1, sensor_err: 0, fault_code: 'none',
        rssi: -55, uptime_sec: 5280, recorded_at: new Date().toISOString().slice(0,19),
      },
      config: {
        d_empty:'18', d_full:'5', in_on_pct:'30', in_off_pct:'70',
        out_on_pct:'90', out_off_pct:'80', limit_high:'97', limit_low:'0',
        max_run_min:'20', publish_sec:'2', web_version:'1.0.0',
        mqtt_broker:'192.168.1.100', mqtt_port:'1883',
        topic_prefix:'iot', language:'vi',

      },
      firmware_defaults: {
        d_empty:'18', d_full:'5', in_on_pct:'30', in_off_pct:'70',
        out_on_pct:'90', out_off_pct:'80', limit_high:'97', limit_low:'0',
        max_run_min:'20', publish_sec:'2',
      },
      total_records: 1245,
    };
  },
  sensor(params = {}) {
    const minutes = Number(params.minutes || 30);
    const pointMap = { 30: 180, 60: 120, 360: 120, 10080: 168, 43200: 120 };
    const limit = Math.max(Number(params.limit) || 50, 1);
    const page = Math.max(Number(params.page) || 1, 1);
    const total = pointMap[minutes] || 500;
    const isPaginated = params.page != null || params.limit != null;
    const rangeMinutes = params.all ? 43200 : minutes;
    const points = isPaginated ? Math.min(limit, Math.max(total - (page - 1) * limit, 0)) : total;
    const startIndex = isPaginated ? (page - 1) * limit : 0;
    const rows = [];
    const now = Date.now();
    let lvl = 36.7;
    for (let i = 0; i < points; i++) {
      lvl += (Math.random() - 0.3) * 2.5;
      lvl  = Math.max(5, Math.min(95, lvl));
      const sampleIndex = startIndex + i;
      rows.push({
        recorded_at: new Date(now - (total - 1 - sampleIndex) * (rangeMinutes * 60000 / Math.max(total - 1, 1))).toISOString().slice(0,19),
        water_level: +lvl.toFixed(1),
        distance_cm: +(100 - lvl * 0.9).toFixed(1),
        pump_in:  lvl < 35 ? 1 : 0,
        pump_out: lvl > 85 ? 1 : 0,
        auto_mode: 1, sensor_err: 0, rssi: -55,
      });
    }
    return { ok:true, data:rows, total, page, limit };
  },
  alerts() {
    return {
      ok: true,
      stats_24h: { DANGER:1, WARNING:3, INFO:12 },
      total: 45, page:1, limit:20,
      data: [
        { id:1, created_at:'2025-10-22 21:40:12', alert_code:'high_level', message:'Mực nước đạt 92% (nguy cơ tràn ao)', severity:'DANGER', water_level:92, value_str:'92 %', status:'UNRESOLVED' },
        { id:2, created_at:'2025-10-22 21:35:08', alert_code:'pump_in_off', message:'Máy bơm cấp đã tắt', severity:'WARNING', water_level:null, value_str:null, status:'RESOLVED' },
        { id:3, created_at:'2025-10-22 21:20:15', alert_code:'mode', message:'Chế độ MANUAL được kích hoạt', severity:'INFO', water_level:null, value_str:null, status:'RESOLVED' },
        { id:4, created_at:'2025-10-22 20:40:12', alert_code:'high_trend', message:'Mực nước tăng nhanh', severity:'WARNING', water_level:65, value_str:'+5.2 %/h', status:'RESOLVED' },
        { id:5, created_at:'2025-10-22 18:30:25', alert_code:'sensor_error', message:'Cảm biến đo không ổn định', severity:'WARNING', water_level:40, value_str:null, status:'RESOLVED' },
        { id:6, created_at:'2025-10-22 16:10:08', alert_code:'pump_in', message:'Máy bơm cấp đã bật', severity:'INFO', water_level:28.5, value_str:null, status:'RESOLVED' },
      ],
    };
  },
  chart(period) {
    const labels=[], avg=[], mx=[], mn=[];
    const pts = period==='hour'?30: period==='day'?24: period==='week'?7*24: 30;
    let lvl=45;
    for(let i=pts;i>=0;i--) {
      lvl+=(Math.random()-.4)*3; lvl=Math.max(10,Math.min(90,lvl));
      const d=new Date(Date.now()-i*(period==='week'||period==='month'?3600000:60000)*
        (period==='hour'?1:period==='day'?60:period==='week'?60:240));
      labels.push(d.toLocaleTimeString('vi',{hour:'2-digit',minute:'2-digit'}));
      avg.push(+lvl.toFixed(1)); mx.push(+(lvl+3).toFixed(1)); mn.push(+(lvl-3).toFixed(1));
    }
    return {ok:true,labels,avg,max:mx,min:mn};
  },
  logs() {
    return {
      ok:true, total:10,
      data:[
        {id:1,logged_at:new Date().toISOString().slice(0,19),log_level:'INFO',component:'mqtt',event_type:'data_received',message:'Nhận dữ liệu từ ESP32: level=45.5%'},
        {id:2,logged_at:new Date(Date.now()-120000).toISOString().slice(0,19),log_level:'INFO',component:'mqtt',event_type:'keepalive',message:'MQTT keep alive – esp32-ao-demo'},
        {id:3,logged_at:new Date(Date.now()-2460000).toISOString().slice(0,19),log_level:'INFO',component:'flask',event_type:'cmd_sent',message:'Gửi lệnh bật bơm cấp'},
        {id:4,logged_at:new Date(Date.now()-2340000).toISOString().slice(0,19),log_level:'INFO',component:'mqtt',event_type:'ack_received',message:'Nhận ACK: bơm cấp ON'},
        {id:5,logged_at:new Date(Date.now()-2040000).toISOString().slice(0,19),log_level:'WARNING',component:'flask',event_type:'alert_triggered',message:'Cảnh báo: mực nước 92%'},
        {id:6,logged_at:new Date(Date.now()-1800000).toISOString().slice(0,19),log_level:'INFO',component:'mqtt',event_type:'connected',message:'Kết nối MQTT thành công'},
      ],
    };
  },
  config() {
    return { ok:true, config:{
      d_empty:'18', d_full:'5', in_on_pct:'30', in_off_pct:'70',
      out_on_pct:'90', out_off_pct:'80', limit_high:'97', limit_low:'0',
      max_run_min:'20', publish_sec:'2', mqtt_broker:'192.168.1.100',
      mqtt_port:'1883', topic_prefix:'iot',
      web_version:'1.0.0', language:'vi',
    }, firmware_defaults: {
      d_empty:'18', d_full:'5', in_on_pct:'30', in_off_pct:'70',
      out_on_pct:'90', out_off_pct:'80', limit_high:'97', limit_low:'0',
      max_run_min:'20', publish_sec:'2',
    }};
  },
  controlLogs() {
    return {
      ok: true, total: 45,
      data: [
        { id: 1, sent_at: '2025-10-22 21:45:30', acked_at: '2025-10-22 21:45:31', command: 'pump_in', payload: 'Bật', device: 'Bơm cấp (IN)', status: 'ACK_OK', ack_payload: 'Bơm cấp đã bật', initiated_by: 'Admin' },
        { id: 2, sent_at: '2025-10-22 21:40:12', acked_at: '2025-10-22 21:40:13', command: 'mode', payload: 'AUTO', device: 'Chế độ', status: 'ACK_OK', ack_payload: 'Chuyển sang AUTO', initiated_by: 'Admin' },
        { id: 3, sent_at: '2025-10-22 21:35:08', acked_at: '2025-10-22 21:35:09', command: 'pump_in', payload: 'Tắt', device: 'Bơm cấp (IN)', status: 'ACK_OK', ack_payload: 'Bơm cấp đã tắt', initiated_by: 'Admin' },
        { id: 4, sent_at: '2025-10-22 21:33:25', acked_at: '2025-10-22 21:33:26', command: 'pump_out', payload: 'Tắt', device: 'Bơm thoát (OUT)', status: 'ACK_OK', ack_payload: 'Bơm thoát đã tắt', initiated_by: 'Admin' },
        { id: 5, sent_at: '2025-10-22 21:20:15', acked_at: '2025-10-22 21:20:16', command: 'mode', payload: 'MANUAL', device: 'Chế độ', status: 'ACK_OK', ack_payload: 'Chuyển sang MANUAL', initiated_by: 'Admin' },
      ]
    };
  },
  insights() {
    return {
      ok: true,
      status: "NORMAL",
      data_quality: { level: "GOOD", reasons: [], window_seconds_used: 300, bins: 30, last_sample_age_s: 3 },
      current_level_pct: 40.8,
      trend: { state: "OK", direction: "INCREASING", strength: "SLOW", slope_pct_per_min: 0.12, slope_cm_per_min: 0.08, confidence: "HIGH", text: "tăng nhẹ" },
      prediction: {
        "10": { value: 42.0, state: "OK", error_margin: 0.4 },
        "20": { value: 43.2, state: "OK", error_margin: 0.8, reference_only: true },
        "30": { value: 44.4, state: "OK", error_margin: 1.3, reference_only: true }
      },
      eta: {
        high: { minutes: 451, state: "BEYOND_HORIZON", formatted: "≈ 7 giờ 31 phút nữa", limit: 95.0 },
        low: { minutes: null, state: "NOT_EXPECTED", formatted: "An toàn (> 24 giờ)", limit: 5.0 }
      },
      pumps: { pump_in: false, pump_out: false, auto_mode: true },
      insight: {
        title: "Tình hình hiện tại: Bình thường (NORMAL)",
        description: "Mực nước hiện tại là 40.8 %, có xu hướng tăng nhẹ với tốc độ khoảng +0.12%/phút (≈ 0.08 cm/phút). Hai máy bơm đang tắt, thiết bị ESP32 kết nối bình thường và chưa ghi nhận lỗi.",
        recommendation: "Tiếp tục theo dõi, chưa cần can thiệp."
      },
      data_as_of: "2026-11-10T02:05:22+07:00",
      updated_at: "2026-11-10T02:05:52+07:00"
    };
  },
};

// ── Try real API, fallback to demo only when ?demo=1 or explicitly set ──────
async function safeCall(apiFn, demoFn, ...args) {
  if (isDemoMode()) {
    return demoFn(...args);
  }
  try {
    return await apiFn(...args);
  } catch (err) {
    console.warn('[API Error]', err);
    throw err;
  }
}

window.isDemoMode = isDemoMode;
window.api = api;

window.safeAPI = {
  status:      ()      => safeCall(api.status,      demo.status),
  sensor:      (p)     => safeCall(api.sensor,      demo.sensor, p),
  alerts:      (p)     => safeCall(api.alerts,      demo.alerts, p),
  chart:       (period)=> safeCall(api.chart,       demo.chart,  period),
  logs:        (p)     => safeCall(api.logs,        demo.logs,   p),
  controlLogs: (p)     => safeCall(api.controlLogs, demo.controlLogs, p),
  config:      ()      => safeCall(api.config,      demo.config),
  insights:    (demo)  => safeCall(() => api.insights(demo), () => demo.insights()),
  control:     async (c, p) => {
    if (isDemoMode()) return { ok: true, command: c, payload: p, demo: true };
    return await api.control(c, p);
  },
  saveConfig:  async (d) => {
    if (isDemoMode()) return { ok: true, updated: Object.keys(d), demo: true };
    return await api.saveConfig(d);
  },
  notify: {
    getRecipients: () => safeCall(api.notify.getRecipients, () => ({ ok: true, recipients: [{ id: 1, email: 'nguoinuoi@example.com', name: 'Chủ ao nuôi cá', enabled: 1 }] })),
    addRecipient: (email, name) => safeCall(() => api.notify.addRecipient(email, name), () => ({ ok: true, id: 99 })),
    deleteRecipient: (id) => safeCall(() => api.notify.deleteRecipient(id), () => ({ ok: true })),
    getSettings: () => safeCall(api.notify.getSettings, () => ({ ok: true, settings: { mail_enabled: true, recipient_default: 'nguoinuoi@example.com', smtp_configured: true } })),
    saveSettings: (d) => safeCall(() => api.notify.saveSettings(d), () => ({ ok: true })),
    sendTest: (email) => safeCall(() => api.notify.sendTest(email), () => ({ ok: true, message: 'Đã gửi thử nghiệm thành công (Demo)' })),
    getLogs: (p) => safeCall(() => api.notify.getLogs(p), () => ({ ok: true, data: [], total: 0 })),
    getIncidents: (p) => safeCall(() => api.notify.getIncidents(p), () => ({ ok: true, incidents: [] })),
  },
};
