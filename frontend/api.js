// ============================================================================
//  api.js – Giao tiếp với Flask REST API
// ============================================================================
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:5000'
  : '';   // same origin khi deploy

const api = {
  async get(path) {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },
  async post(path, body = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // ── Endpoints ──────────────────────────────────────────────────────────
  status:      ()       => api.get('/api/status'),
  sensor:      (p={})  => api.get('/api/sensor?'  + new URLSearchParams(p)),
  alerts:      (p={})  => api.get('/api/alerts?'  + new URLSearchParams(p)),
  chart:       (period)=> api.get('/api/chart?period=' + period),
  logs:        (p={})  => api.get('/api/logs?'    + new URLSearchParams(p)),
  controlLogs: (p={})  => api.get('/api/control_logs?' + new URLSearchParams(p)),
  config:      ()      => api.get('/api/config'),
  resolveAlert:(id, note='') => api.post(`/api/alerts/${id}/resolve`, { note }),
  control:     (command, payload) => api.post('/api/control', { command, payload }),
  saveConfig:  (data)  => api.post('/api/config', data),
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
        d_empty:'100', d_full:'10', in_on_pct:'30', in_off_pct:'50',
        out_on_pct:'90', out_off_pct:'80', limit_high:'95', limit_low:'5',
        max_run_min:'20', publish_sec:'2', web_version:'1.0.0',
        mqtt_broker:'192.168.1.100', mqtt_port:'1883',
        topic_prefix:'iot-ao-demo-123', language:'vi',
        alert_buzzer:'1', alert_led:'1',
      },
      total_records: 1245,
    };
  },
  sensor(minutes = 30) {
    const rows = [];
    const now = Date.now();
    let lvl = 36.7;
    for (let i = minutes; i >= 0; i -= 2) {
      lvl += (Math.random() - 0.3) * 2.5;
      lvl  = Math.max(5, Math.min(95, lvl));
      rows.push({
        recorded_at: new Date(now - i * 60000).toISOString().slice(0,19),
        water_level: +lvl.toFixed(1),
        distance_cm: +(100 - lvl * 0.9).toFixed(1),
        pump_in:  lvl < 35 ? 1 : 0,
        pump_out: lvl > 85 ? 1 : 0,
        auto_mode: 1, sensor_err: 0, rssi: -55,
      });
    }
    return { ok:true, data:rows, total:rows.length, page:1, limit:500 };
  },
  alerts() {
    return {
      ok: true,
      stats_24h: { DANGER:1, WARNING:3, INFO:12 },
      total: 45, page:1, limit:20,
      data: [
        { id:1, created_at:'2025-10-22 21:40:12', alert_code:'HIGH_LEVEL', message:'Mực nước đạt 92% (nguy cơ tràn ao)', severity:'DANGER', water_level:92, value_str:'92 %', status:'PENDING' },
        { id:2, created_at:'2025-10-22 21:35:08', alert_code:'PUMP_IN_OFF', message:'Máy bơm cấp đã tắt', severity:'WARNING', water_level:null, value_str:null, status:'RESOLVED' },
        { id:3, created_at:'2025-10-22 21:20:15', alert_code:'MODE', message:'Chế độ MANUAL được kích hoạt', severity:'INFO', water_level:null, value_str:null, status:'RESOLVED' },
        { id:4, created_at:'2025-10-22 20:40:12', alert_code:'HIGH_TREND', message:'Mực nước tăng nhanh', severity:'WARNING', water_level:65, value_str:'+5.2 %/h', status:'RESOLVED' },
        { id:5, created_at:'2025-10-22 18:30:25', alert_code:'SENSOR', message:'Cảm biến đo không ổn định', severity:'WARNING', water_level:40, value_str:null, status:'RESOLVED' },
        { id:6, created_at:'2025-10-22 16:10:08', alert_code:'PUMP_IN', message:'Máy bơm cấp đã bật', severity:'INFO', water_level:28.5, value_str:null, status:'RESOLVED' },
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
      d_empty:'100', d_full:'10', in_on_pct:'30', in_off_pct:'50',
      out_on_pct:'90', out_off_pct:'80', limit_high:'95', limit_low:'5',
      max_run_min:'20', publish_sec:'2', mqtt_broker:'192.168.1.100',
      mqtt_port:'1883', topic_prefix:'iot-ao-demo-123',
      alert_buzzer:'1', alert_led:'1', web_version:'1.0.0', language:'vi',
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
};

// ── Try real API, fallback to demo ──────────────────────────────────────────
async function safeCall(apiFn, demoFn, ...args) {
  try {
    return await apiFn(...args);
  } catch {
    return demoFn(...args);
  }
}

window.safeAPI = {
  status:      ()      => safeCall(api.status,      demo.status),
  sensor:      (p)     => safeCall(api.sensor,      demo.sensor, p),
  alerts:      (p)     => safeCall(api.alerts,      demo.alerts, p),
  chart:       (period)=> safeCall(api.chart,       demo.chart,  period),
  logs:        (p)     => safeCall(api.logs,        demo.logs,   p),
  controlLogs: (p)     => safeCall(api.controlLogs, demo.controlLogs, p),
  config:      ()      => safeCall(api.config,      demo.config),
  resolveAlert:(id,n)  => safeCall(()=>api.resolveAlert(id,n), ()=>({ok:true})),
  control:     (c,p)   => safeCall(()=>api.control(c,p), ()=>({ok:true,command:c,payload:p})),
  saveConfig:  (d)     => safeCall(()=>api.saveConfig(d), ()=>({ok:true})),
};
