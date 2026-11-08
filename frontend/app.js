// ============================================================================
//  app.js – Logic chính cho toàn bộ 7 trang dashboard
// ============================================================================

// ── State ────────────────────────────────────────────────────────────────────
let currentPage = 'tong-quan';
let chartOverview = null, chartMain = null, chartPump = null;
let alertPage = 1, histPage = 1, ctrlLogPage = 1;
let autoRefreshTimer = null;
let configCache = {};

// ── Navigation ────────────────────────────────────────────────────────────────
function navigate(page) {
  hidePumpTimelineTooltip();
  document.querySelector('.sidebar')?.classList.remove('mobile-open');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const pageEl = document.getElementById('page-' + page);
  const navEl  = document.getElementById('nav-'  + page);
  if (pageEl) pageEl.classList.add('active');
  if (navEl)  navEl.classList.add('active');

  currentPage = page;
  onPageLoad(page);
}

window.toggleSidebar = function() {
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) sidebar.classList.toggle('mobile-open');
};

function hidePumpTimelineTooltip() {
  const tooltip = document.getElementById('pump-timeline-tooltip');
  if (tooltip) {
    tooltip.hidden = true;
    tooltip.style.display = 'none';
  }
}

function onPageLoad(page) {
  switch (page) {
    case 'tong-quan':  loadOverview(); break;
    case 'dieu-khien': loadControlPage(); break;
    case 'cau-hinh':   loadConfig(); break;
    case 'canh-bao':   loadAlerts(); break;
    case 'lich-su':    loadHistory(); break;
    case 'tro-ly-ai':  if (window.loadChatPage) window.loadChatPage(); break;
  }
}

// ── Clock ─────────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2,'0');
  const s = `${pad(now.getDate())}/${pad(now.getMonth()+1)}/${now.getFullYear()} `
          + `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  document.getElementById('clock-display').textContent = s;
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type='info', duration=3500) {
  const icons = { success:'✅', error:'❌', warning:'⚠️', info:'ℹ️' };
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span>${icons[type]||'ℹ️'}</span><span>${msg}</span>`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = {
  pct:  v => (v == null ? '--' : (+v).toFixed(1) + ' %'),
  cm:   v => (v == null ? '--' : (+v).toFixed(1) + ' cm'),
  rssi: v => (v == null ? '--' : v + ' dBm'),
  uptime(sec) {
    if (!sec) return '--';
    const h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60), s = sec%60;
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')} (${h} giờ ${m} phút)`;
  },
  dt: s => s ? s.replace('T',' ').slice(0,19) : '--',
};

function sevBadge(s) {
  const map = { DANGER:'danger', WARNING:'warning', INFO:'info' };
  const labels = { DANGER:'Nguy hiểm', WARNING:'Cảnh báo', INFO:'Thông tin' };
  return `<span class="badge badge-${map[s]||'gray'}">${labels[s]||s}</span>`;
}

function getLatestRecord(status) {
  const record = { ...(status.last_record || {}) };
  const latest = status.latest || {};
  const fields = {
    level: 'water_level',
    dist: 'distance_cm',
    in: 'pump_in',
    out: 'pump_out',
    auto: 'auto_mode',
    err: 'sensor_err',
    fault: 'fault_code',
    rssi: 'rssi',
    up: 'uptime_sec',
  };

  Object.entries(fields).forEach(([latestKey, recordKey]) => {
    if (latest[latestKey] != null) record[recordKey] = latest[latestKey];
  });
  if (latest.ts) record.recorded_at = latest.ts;
  return record;
}

function pumpBadge(v) {
  return v ? '<span class="text-danger fw-600">Bật</span>' : '<span class="text-muted">Tắt</span>';
}

function modeBadge(v) {
  return v ? '<span class="badge badge-info">AUTO</span>' : '<span class="badge badge-warning">MANUAL</span>';
}

function setPumpUI(pumpId, isOn) {
  const dot  = document.getElementById(`pump-${pumpId}-dot`);
  const text = document.getElementById(`pump-${pumpId}-text`);
  if (dot)  { dot.className  = 'pump-dot ' + (isOn ? 'on' : 'off'); }
  if (text) { text.textContent = isOn ? 'Bật' : 'Tắt'; text.style.color = isOn ? 'var(--success)' : 'var(--text-muted)'; }
}

function renderPagination(containerId, currentPg, totalPages, onClickFn) {
  const c = document.getElementById(containerId);
  if (!c) return;
  c.innerHTML = '';

  const addBtn = (label, pg, disabled=false, active=false) => {
    const b = document.createElement('button');
    b.className = 'page-btn' + (active?' active':'');
    b.textContent = label;
    b.disabled = disabled;
    b.onclick = () => onClickFn(pg);
    c.appendChild(b);
  };

  addBtn('‹', currentPg-1, currentPg<=1);
  const start = Math.max(1, currentPg-2);
  const end   = Math.min(totalPages, currentPg+2);
  for (let i=start; i<=end; i++) addBtn(i, i, false, i===currentPg);
  addBtn('›', currentPg+1, currentPg>=totalPages);
}

// ── Chart options helper ──────────────────────────────────────────────────────
function chartOptions({
  yLabel = '',
  yMin = 0,
  yMax = 100,
  tooltipTitle = null,
  interaction = { mode: 'index', intersect: false },
  legendLabels = null,
} = {}) {
  const tooltipCallbacks = {
    label: ctx => ` ${ctx.dataset.label}: ${ctx.raw} %`,
  };
  if (tooltipTitle) tooltipCallbacks.title = tooltipTitle;

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction,
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: {
          boxWidth: 12,
          font: { size: 11 },
          color: '#475569',
          ...(legendLabels || {}),
        }
      },
      tooltip: {
        callbacks: tooltipCallbacks,
      }
    },
    scales: {
      x: {
        grid: { color: 'rgba(0,0,0,0.04)' },
        ticks: { font: { size: 11 }, color: '#64748b', maxTicksLimit: 12 }
      },
      y: {
        min: yMin,
        max: yMax,
        grid: { color: 'rgba(0,0,0,0.05)' },
        ticks: { font: { size: 11 }, color: '#64748b', callback: v => v + ' %' },
        title: { display: !!yLabel, text: yLabel, font: { size: 11.5, weight: '500' }, color: '#475569' }
      }
    }
  };
}

function createLegendLineDotIcon(color) {
  const icon = document.createElement('canvas');
  icon.width = 28;
  icon.height = 12;
  const ctx = icon.getContext('2d');
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(1, 6);
  ctx.lineTo(27, 6);
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(14, 6, 3.5, 0, Math.PI * 2);
  ctx.fill();
  return icon;
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE 1: TỔNG QUAN
// ══════════════════════════════════════════════════════════════════════════════
async function loadOverview() {
  try {
    const [status, sensor] = await Promise.all([
      safeAPI.status(),
      safeAPI.sensor({ minutes: 30 }),
    ]);
    loadChart(currentChartPeriod);

    const rec = getLatestRecord(status);
    const cfg = status.config || {};
    const lvl = rec.water_level ?? 0;

    // Stat cards
    setText('ov-level', fmt.pct(lvl));
    setText('ov-dist',  `Khoảng cách: ${fmt.cm(rec.distance_cm)}`);
    setText('ov-rssi',  `RSSI: ${fmt.rssi(rec.rssi)}`);
    setText('ov-fault', `Fault: ${rec.fault_code || 'none'}`);
    setText('ov-broker',`Broker: ${cfg.mqtt_broker || '--'}`);

    const isOnline = status.esp32_status === 'online' || (status.last_record && status.last_record.recorded_at);
    setText('ov-esp32-status', isOnline ? 'Online' : 'Offline');
    const overviewEsp32Status = document.getElementById('ov-esp32-status');
    if (overviewEsp32Status) {
      overviewEsp32Status.className = 'stat-value ' + (isOnline ? 'text-success' : 'text-danger');
    }

    const modeAuto = rec.auto_mode;
    setText('ov-mode', modeAuto ? 'AUTO' : 'MANUAL');
    const overviewMode = document.getElementById('ov-mode');
    if (overviewMode) {
      overviewMode.className = 'stat-value ' + (modeAuto ? 'text-success' : 'text-warning');
    }

    const mqttOk = status.mqtt_connected;
    setText('ov-mqtt', mqttOk ? 'Đã kết nối' : 'Mất kết nối');
    const overviewMqtt = document.getElementById('ov-mqtt');
    if (overviewMqtt) {
      overviewMqtt.className = 'stat-value ' + (mqttOk ? 'text-info' : 'text-danger');
    }

    // ESP32 status dot in topbar
    const dot = document.getElementById('esp32-dot');
    const txt = document.getElementById('esp32-status-text');
    dot.className = 'status-dot ' + (isOnline ? '' : 'offline');
    txt.textContent = isOnline ? 'ESP32 đang hoạt động' : 'ESP32 offline';

    // Pump
    setPumpUI('in',  !!rec.pump_in);
    setPumpUI('out', !!rec.pump_out);

    // Pond diagram
    const pondWater = document.getElementById('pond-water');
    if (pondWater) pondWater.style.height = Math.max(2, Math.min(100, lvl)) + '%';
    setText('pond-pct', `Mực nước: ${lvl.toFixed(1)} %`);
    setText('ov-dist-line', `↕ ${fmt.cm(rec.distance_cm)}`);

    // Chart
    const rows = sensor.data || [];
    const overviewRecords = rows.length
      ? rows
      : [{
          ...rec,
          recorded_at: rec.recorded_at || new Date().toISOString(),
          water_level: lvl,
        }];
    updateChartStats(rows);
    const chartRecords = resampleChartRecords(
      overviewRecords,
      { minutes: 30, chartPoints: 30 },
      '30m'
    );
    const labels = chartRecords.map(record => formatChartAxisLabel(record.recorded_at, '30m'));
    const data = chartRecords.map(record => +(record.water_level ?? 0));
    const overviewMarkerIndexes = getChartMarkerIndexes(chartRecords, 'overview');
    const limitHigh = 90;
    const limitWarn = 80;

    const canvasEl = document.getElementById('chart-overview');
    if (canvasEl && typeof Chart !== 'undefined') {
      if (!chartOverview) {
        const ctx = canvasEl.getContext('2d');
        chartOverview = new Chart(ctx, {
          type: 'line',
          data: {
            labels,
            datasets: [
              {
                label: 'Mực nước hiện tại',
                data,
                fill: true,
                borderColor: '#2563eb',
                backgroundColor: 'rgba(37,99,235,0.12)',
                tension: 0.35,
                pointRadius: data.map((_, index) => overviewMarkerIndexes.has(index) ? 3 : 0),
                pointHoverRadius: data.map((_, index) => overviewMarkerIndexes.has(index) ? 5 : 0),
                pointBackgroundColor: '#2563eb',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 1.5,
                pointStyle: createLegendLineDotIcon('#2563eb'),
              },
              {
                label: 'Ngưỡng nguy hiểm (≥ 90%)',
                data: Array(labels.length).fill(limitHigh),
                borderColor: '#ef4444', borderDash: [5,3],
                borderWidth: 1.5, pointRadius: 0, fill: false,
                pointStyle: 'line',
              },
              {
                label: 'Ngưỡng cảnh báo (≥ 80%)',
                data: Array(labels.length).fill(limitWarn),
                borderColor: '#f59e0b', borderDash: [5,3],
                borderWidth: 1.5, pointRadius: 0, fill: false,
                pointStyle: 'line',
              },
            ],
          },
          options: {
            ...chartOptions({
              yLabel: 'Mực nước (%)',
              yMax: 100,
              interaction: { mode: 'nearest', intersect: true },
              legendLabels: {
                usePointStyle: true,
                boxWidth: 32,
                padding: 20,
              },
              tooltipTitle: items => {
                const index = items[0]?.dataIndex;
                return formatChartTimestamp(chartRecords[index]?.recorded_at)
                  || labels[index]
                  || '';
              },
            }),
          },
          plugins: [hoverGuideLinePlugin],
        });
      } else {
        chartOverview.data.labels = labels;
        chartOverview.data.datasets[0].data = data;
        chartOverview.data.datasets[0].pointRadius =
          data.map((_, index) => overviewMarkerIndexes.has(index) ? 3 : 0);
        chartOverview.data.datasets[0].pointHoverRadius =
          data.map((_, index) => overviewMarkerIndexes.has(index) ? 5 : 0);
        chartOverview.data.datasets[1].data = Array(labels.length).fill(limitHigh);
        chartOverview.data.datasets[2].data = Array(labels.length).fill(limitWarn);
        chartOverview.update('none');
      }
    }
    setText('ov-chart-time', `Cập nhật: ${new Date().toLocaleTimeString('vi')}`);

    // Latest alerts
    const [alertData, unresolvedAlerts] = await Promise.all([
      safeAPI.alerts({ limit: 3, recent_hours: 24 }),
      safeAPI.alerts({ status: 'UNRESOLVED', limit: 200 }),
    ]);
    renderOverviewAlerts(alertData.data || []);

    // Nav badge
    const pendingCount = unresolvedAlerts.total
      ?? (unresolvedAlerts.data || []).length;
    const navBadge = document.getElementById('nav-badge-alert');
    navBadge.textContent = pendingCount;
    navBadge.style.display = pendingCount > 0 ? 'inline-block' : 'none';

  } catch(e) {
    console.error('loadOverview error:', e);
  }
}

function renderOverviewAlerts(alerts) {
  const el = document.getElementById('ov-alerts');
  if (!el) return;
  if (!alerts.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-icon">✅</div><div class="empty-text">Không có cảnh báo mới</div></div>';
    return;
  }
  const icons = { DANGER:'🚨', WARNING:'⚠️', INFO:'ℹ️' };
  el.innerHTML = alerts.map(a =>
    `<div class="alert-item">
       <span class="alert-item-icon">${icons[a.severity]||'ℹ️'}</span>
       <div style="flex:1">
         <div class="alert-item-time">${fmt.dt(a.created_at).slice(11,19)}</div>
         <div class="alert-item-text">${a.message}</div>
       </div>
     </div>`
  ).join('');
}

// ══════════════════════════════════════════════════════════════════════════════
//  BIỂU ĐỒ TRÊN TRANG TỔNG QUAN
// ══════════════════════════════════════════════════════════════════════════════
let chartWaterLevel = null;
let chartDistance = null;
let currentChartPeriod = '30m';
let chartLoadRequest = 0;
const chartPeriodConfig = {
  '30m': { minutes: 30, chartPoints: 180, timelineMinutes: 1, timelineSlots: 30 },
  '1h':  { minutes: 60, chartPoints: 120, timelineMinutes: 2, timelineSlots: 30 },
  '6h':  { minutes: 360, chartPoints: 120, timelineMinutes: 10, timelineSlots: 36 },
  '7d':  { minutes: 10080, chartPoints: 168, timelineMinutes: 360, timelineSlots: 28 },
  '30d': { minutes: 43200, chartPoints: 120, timelineMinutes: 1440, timelineSlots: 30 },
};

const hoverGuideLinePlugin = {
  id: 'hoverGuideLine',
  afterDraw(chart) {
    const active = chart.getActiveElements();
    const activePoint = active.find(item => item.datasetIndex === 0);
    if (!activePoint) return;

    const { ctx, chartArea } = chart;
    const x = activePoint.element.x;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#94a3b8';
    ctx.setLineDash([4, 4]);
    ctx.stroke();
    ctx.restore();
  },
};

async function loadChart(period = '30m') {
  currentChartPeriod = period;
  const requestId = ++chartLoadRequest;
  try {
    const config = chartPeriodConfig[period] || chartPeriodConfig['30m'];
    const minMap = { '30m': 30, '1h': 60, '6h': 360, '7d': 10080, '30d': 43200 };
    const pointMap = { '30m': 180, '1h': 120, '6h': 120, '7d': 168, '30d': 120 };
    const tickStepMap = { '30m': 5, '1h': 10, '6h': 60, '7d': 1440, '30d': 7200 };
    const mins = minMap[period] || 30;
    const pointLimit = pointMap[period] || 180;

    const [sensorData, statsData, status] = await Promise.all([
      safeAPI.sensor({ minutes: mins, limit: pointLimit, latest: 1 }),
      safeAPI.sensor({ minutes: mins, limit: 2000, latest: 1 }),
      safeAPI.status(),
    ]);
    const records = (statsData.data && statsData.data.length > 0)
      ? statsData.data
      : (sensorData.data || []);
    const statsRecords = records;
    const realtimeStatsRecords = filterRecordsToCurrentPeriod(statsRecords, config.minutes);
    if (requestId !== chartLoadRequest || currentPage !== 'tong-quan') return;

    // Chuẩn bị dữ liệu hiển thị
    const chartRecords = resampleChartRecords(records, config, period);
    const chartDisplayNow = new Date();
    const requestedRange = {
      start: new Date(Date.now() - config.minutes * 60 * 1000).toISOString(),
      end: chartDisplayNow.toISOString(),
    };
    updateChartPeriodInfo(period, {
      start: requestedRange.start,
      end: requestedRange.end,
    });
    if (!chartRecords.length) {
      const info = document.getElementById('chart-period-info');
      if (info) {
        info.innerHTML = '<span class="chart-period-info-icon">ℹ</span>'
          + '<span>Chưa có dữ liệu trong khoảng thời gian này.</span>';
      }
    }
    const labels = chartRecords.map(r => formatChartAxisLabel(r.recorded_at, period));
    const markerIndexes = getChartMarkerIndexes(chartRecords, period);
    const showTick = index => markerIndexes.has(index);
    const xTickConfig = {
      autoSkip: false,
      maxRotation: 0,
      minRotation: 0,
      font: { size: 11 },
      color: '#64748b',
      callback: (value, index) => showTick(index) ? labels[index] : '',
    };
    const levels = chartRecords.map(r =>
      r.water_level == null ? null : Number(r.water_level)
    );
    const dists  = chartRecords.map(r =>
      r.distance_cm == null ? null : Number(r.distance_cm)
    );

    // 1. Biểu đồ mực nước theo thời gian
    const ctxLvl = document.getElementById('chart-water-level')?.getContext('2d');
    if (ctxLvl) {
      if (chartWaterLevel) chartWaterLevel.destroy();
      chartWaterLevel = new Chart(ctxLvl, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Mực nước hiện tại',
              data: levels,
              borderColor: '#1890ff',
              backgroundColor: 'rgba(24, 144, 255, 0.14)',
              fill: true,
              tension: 0.35,
              borderWidth: 2.2,
              pointRadius: levels.map((_, index) => showTick(index) ? 2 : 0),
              pointHoverRadius: 5,
              pointBackgroundColor: '#1890ff',
              pointBorderColor: '#ffffff',
              pointBorderWidth: 1.5,
              spanGaps: false,
            },
            {
              label: 'Ngưỡng nguy hiểm (≥ 90%)',
              data: Array(labels.length).fill(90),
              borderColor: '#ef4444',
              borderDash: [5, 4],
              borderWidth: 1.5,
              pointRadius: 0,
              fill: false,
              spanGaps: false,
            },
            {
              label: 'Ngưỡng cảnh báo (≥ 80%)',
              data: Array(labels.length).fill(80),
              borderColor: '#f59e0b',
              borderDash: [5, 4],
              borderWidth: 1.5,
              pointRadius: 0,
              fill: false,
              spanGaps: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          spanGaps: false,
          interaction: { mode: 'nearest', intersect: true },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: items => {
                  const index = items[0]?.dataIndex;
                  const record = chartRecords[index];
                  return formatChartTooltipTimestamp(
                    record?.recorded_at,
                    markerIndexes.has(index),
                    chartDisplayNow
                  ) || labels[index] || '';
                },
                label: ctx => ` ${ctx.dataset.label}: ${ctx.raw} %`,
              },
            },
          },
          scales: {
            x: {
              grid: { color: 'rgba(0,0,0,0.04)' },
              ticks: xTickConfig,
            },
            y: {
              min: 0, max: 100,
              ticks: { stepSize: 20, font: { size: 11 }, color: '#64748b', callback: v => v },
              title: { display: true, text: 'Mực nước (%)', font: { size: 11.5, weight: '500' }, color: '#475569' },
              grid: { color: 'rgba(0,0,0,0.05)' },
            },
          },
        },
        plugins: [hoverGuideLinePlugin],
      });
    }

    // 2. Biểu đồ khoảng cách cảm biến
    const ctxDist = document.getElementById('chart-distance')?.getContext('2d');
    if (ctxDist) {
      if (chartDistance) chartDistance.destroy();
      chartDistance = new Chart(ctxDist, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Khoảng cách hiện tại',
              data: dists,
              borderColor: '#10b981',
              backgroundColor: 'rgba(16, 185, 129, 0.14)',
              fill: true,
              tension: 0.35,
              borderWidth: 2.2,
              pointRadius: dists.map((_, index) => showTick(index) ? 2 : 0),
              pointHoverRadius: 5,
              pointBackgroundColor: '#10b981',
              pointBorderColor: '#ffffff',
              pointBorderWidth: 1.5,
              spanGaps: false,
            },
            {
              label: 'Ngưỡng cảnh báo thấp',
              data: Array(labels.length).fill(100),
              borderColor: '#ef4444',
              borderDash: [5, 4],
              borderWidth: 1.5,
              pointRadius: 0,
              fill: false,
              spanGaps: false,
            },
            {
              label: 'Ngưỡng cảnh báo cao',
              data: Array(labels.length).fill(88),
              borderColor: '#f59e0b',
              borderDash: [5, 4],
              borderWidth: 1.5,
              pointRadius: 0,
              fill: false,
              spanGaps: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          spanGaps: false,
          interaction: { mode: 'nearest', intersect: true },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: items => {
                  const index = items[0]?.dataIndex;
                  const record = chartRecords[index];
                  return formatChartTooltipTimestamp(
                    record?.recorded_at,
                    markerIndexes.has(index),
                    chartDisplayNow
                  ) || labels[index] || '';
                },
                label: ctx => ` ${ctx.dataset.label}: ${ctx.raw} cm`,
              },
            },
          },
          scales: {
            x: {
              grid: { color: 'rgba(0,0,0,0.04)' },
              ticks: xTickConfig,
            },
            y: {
              min: 0, max: 120,
              ticks: { stepSize: 20, font: { size: 11 }, color: '#64748b', callback: v => v },
              title: { display: true, text: 'Khoảng cách (cm)', font: { size: 11.5, weight: '500' }, color: '#475569' },
              grid: { color: 'rgba(0,0,0,0.05)' },
            },
          },
        },
        plugins: [hoverGuideLinePlugin],
      });
    }

    // 3. Trạng thái máy bơm theo thời gian (Timeline)
    renderPumpTimeline(statsRecords, config);

    // 4. Thống kê trong khoảng thời gian
    updateChartStats(realtimeStatsRecords);

  } catch (e) {
    console.error('loadChart error:', e);
  }
}

function filterRecordsToCurrentPeriod(records, minutes) {
  const now = Date.now();
  const since = now - minutes * 60 * 1000;
  return records.filter(record => {
    const timestamp = Date.parse(record.recorded_at);
    return Number.isFinite(timestamp) && timestamp >= since && timestamp <= now;
  });
}

function resampleChartRecords(records, config, period) {
  const end = Date.now();
  const start = end - config.minutes * 60 * 1000;
  const sorted = records
    .map(record => ({ ...record, timestamp: Date.parse(record.recorded_at) }))
    .filter(record => Number.isFinite(record.timestamp))
    .filter(record => record.timestamp >= start && record.timestamp <= end)
    .sort((a, b) => a.timestamp - b.timestamp);
  if (!sorted.length) return [];
  const step = (end - start) / Math.max(config.chartPoints - 1, 1);
  const intervals = sorted
    .slice(1)
    .map((record, index) => record.timestamp - sorted[index].timestamp)
    .filter(interval => interval > 0);
  const medianInterval = intervals.length
    ? intervals.sort((a, b) => a - b)[Math.floor(intervals.length / 2)]
    : step;
  const maxDataGap = Math.max(step * 0.55, medianInterval * 3);

  return Array.from({ length: config.chartPoints }, (_, index) => {
    const timestamp = start + index * step;
    const lastDataTimestamp = sorted[sorted.length - 1].timestamp;
    if (timestamp > lastDataTimestamp) {
      return {
        recorded_at: new Date(timestamp).toISOString(),
        water_level: null,
        distance_cm: null,
        pump_in: null,
        pump_out: null,
      };
    }

    let right = sorted.findIndex(record => record.timestamp >= timestamp);
    if (right < 0) right = sorted.length - 1;
    const left = Math.max(0, right - 1);
    const before = sorted[left];
    const after = sorted[right];
    const beforeDistance = Math.abs(timestamp - before.timestamp);
    const afterDistance = Math.abs(after.timestamp - timestamp);
    const nearest = beforeDistance <= afterDistance ? before : after;
    const nearestDistance = Math.min(beforeDistance, afterDistance);
    if (nearestDistance > maxDataGap) {
      return {
        recorded_at: new Date(timestamp).toISOString(),
        water_level: null,
        distance_cm: null,
        pump_in: null,
        pump_out: null,
      };
    }

    const ratio = after.timestamp === before.timestamp
      ? 0
      : (timestamp - before.timestamp) / (after.timestamp - before.timestamp);
    const interpolate = key => {
      const start = Number(before[key]);
      const end = Number(after[key]);
      if (!Number.isFinite(start)) return after[key] ?? before[key];
      if (!Number.isFinite(end)) return before[key];
      return +(start + (end - start) * ratio).toFixed(2);
    };
    return {
      ...before,
      recorded_at: new Date(timestamp).toISOString(),
      water_level: interpolate('water_level'),
      distance_cm: interpolate('distance_cm'),
      pump_in: ratio < 0.5 ? before.pump_in : after.pump_in,
      pump_out: ratio < 0.5 ? before.pump_out : after.pump_out,
    };
  });
}

function getChartMarkerIndexes(records, period) {
  const markerMinutes = {
    overview: 3,
    '30m': 5,
    '1h': 10,
    '6h': 60,
    '7d': 1440,
    '30d': 7200,
  };
  const intervalMs = (markerMinutes[period] || 5) * 60 * 1000;
  const first = Date.parse(records[0]?.recorded_at);
  const last = Date.parse(records[records.length - 1]?.recorded_at);
  const indexes = new Set([0, records.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last) || last <= first) return indexes;

  for (let target = first; target <= last; target += intervalMs) {
    let closest = 0;
    let distance = Infinity;
    records.forEach((record, index) => {
      const difference = Math.abs(Date.parse(record.recorded_at) - target);
      if (difference < distance) {
        distance = difference;
        closest = index;
      }
    });
    indexes.add(closest);
  }
  return indexes;
}

function formatChartAxisLabel(timestamp, period) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '--';
  if (period === '7d' || period === '30d') {
    return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' });
  }
  return date.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function formatChartRangeTimestamp(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '--';
  const pad = value => String(value).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    + ` ${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
}

function renderPumpTimeline(records, config) {
  const inTrack  = document.getElementById('track-pump-in');
  const outTrack = document.getElementById('track-pump-out');
  const axis     = document.getElementById('track-axis');
  if (!inTrack || !outTrack) return;

  inTrack.innerHTML = '';
  outTrack.innerHTML = '';

  const now = Date.now();
  const intervalMs = config.timelineMinutes * 60 * 1000;
  const start = now - config.timelineSlots * intervalMs;
  const pts = Array.from({ length: config.timelineSlots }, (_, index) => {
    const bucketStart = start + index * intervalMs;
    const bucketEnd = bucketStart + intervalMs;
    const bucketRecords = records.filter(record => {
      const timestamp = Date.parse(record.recorded_at);
      return timestamp >= bucketStart && timestamp < bucketEnd;
    });
    return {
      ...(bucketRecords[bucketRecords.length - 1] || {
        pump_in: 0,
        pump_out: 0,
      }),
      timelineStart: bucketStart,
      timelineEnd: bucketEnd,
    };
  });
  // The final segment represents the interval ending at the moment of display.
  // Keep its pump state, but anchor its visible endpoint to the current time.
  if (pts.length > 0) {
    pts[pts.length - 1] = {
      ...pts[pts.length - 1],
      timelineEnd: now,
      recorded_at: new Date(now).toISOString(),
    };
  }
  const segWidth = (100 / Math.max(pts.length, 1)).toFixed(2) + '%';
  const isLongPeriod = config.minutes >= 10080;
  const tooltip = getPumpTimelineTooltip();
  const hideTimelineTooltip = () => {
    tooltip.hidden = true;
  };
  inTrack.addEventListener('mouseleave', hideTimelineTooltip);
  outTrack.addEventListener('mouseleave', hideTimelineTooltip);

  pts.forEach(r => {
    // Bơm IN
    const divIn = document.createElement('div');
    divIn.className = 'track-segment ' + (r.pump_in ? 'on-in' : 'off');
    divIn.style.width = segWidth;
    attachPumpTimelineTooltip(divIn, {
      name: 'Bơm cấp (IN)',
      isOn: !!r.pump_in,
      start: r.timelineStart,
      end: r.timelineEnd,
      isLongPeriod,
      tooltip,
    });
    inTrack.appendChild(divIn);

    // Bơm OUT
    const divOut = document.createElement('div');
    divOut.className = 'track-segment ' + (r.pump_out ? 'on-out' : 'off');
    divOut.style.width = segWidth;
    attachPumpTimelineTooltip(divOut, {
      name: 'Bơm thoát (OUT)',
      isOn: !!r.pump_out,
      start: r.timelineStart,
      end: r.timelineEnd,
      isLongPeriod,
      tooltip,
    });
    outTrack.appendChild(divOut);
  });

  if (axis && pts.length > 0) {
    const step = Math.max(1, Math.floor(pts.length / 7));
    const labelIndexes = [];
    for (let i = 0; i < pts.length; i += step) {
      labelIndexes.push(i);
    }
    if (labelIndexes[labelIndexes.length - 1] !== pts.length - 1) {
      labelIndexes.push(pts.length - 1);
    }
    const axisLabels = labelIndexes.map(index =>
      `<span>${index === pts.length - 1
        ? formatChartTime(new Date(now).toISOString())
        : formatChartTime(pts[index].recorded_at)}</span>`
    );
    axis.innerHTML = axisLabels.join('');
  }
}

function getPumpTimelineTooltip() {
  let tooltip = document.getElementById('pump-timeline-tooltip');
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.id = 'pump-timeline-tooltip';
    tooltip.className = 'pump-timeline-tooltip';
    tooltip.hidden = true;
    tooltip.style.display = 'none';
    document.body.appendChild(tooltip);
  }
  if (!tooltip.dataset.outsideHandlerAttached) {
    document.addEventListener('pointermove', event => {
      if (!event.target.closest('.track-segment')) {
        hidePumpTimelineTooltip();
      }
    });
    document.addEventListener('mouseout', event => {
      const nextTarget = event.relatedTarget;
      if (!nextTarget || !nextTarget.closest?.('.track-segment')) {
        hidePumpTimelineTooltip();
      }
    });
    window.addEventListener('blur', () => {
      hidePumpTimelineTooltip();
    });
    document.addEventListener('pointerleave', () => {
      hidePumpTimelineTooltip();
    });
    tooltip.dataset.outsideHandlerAttached = 'true';
  }
  return tooltip;
}

function attachPumpTimelineTooltip(segment, details) {
  const {
    name, isOn, start, end, isLongPeriod, tooltip,
  } = details;
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return;

  const durationText = formatPumpDuration(Math.max(0, end - start));
  const lines = isLongPeriod
    ? [
        name,
        `Ngày: ${formatPumpDate(startDate)}`,
        `Thời gian bật ghi nhận: ${isOn ? durationText : '0 phút'}`,
      ]
    : [
        name,
        `Trạng thái: ${isOn ? 'Bật' : 'Tắt'}`,
        `Bắt đầu: ${formatPumpTime(startDate)}`,
        `Kết thúc: ${formatPumpTime(endDate)}`,
        `Thời gian hoạt động: ${isOn ? durationText : '0 phút'}`,
      ];

  const show = event => {
    tooltip.innerHTML = lines.map((line, index) =>
      index === 0 ? `<strong>${line}</strong>` : `<span>${line}</span>`
    ).join('');
    tooltip.hidden = false;
    tooltip.style.display = 'flex';
    move(event);
  };
  const move = event => {
    tooltip.style.left = `${event.clientX + 12}px`;
    tooltip.style.top = `${event.clientY + 12}px`;
  };
  const hide = () => {
    hidePumpTimelineTooltip();
  };

  segment.addEventListener('mouseenter', show);
  segment.addEventListener('mousemove', move);
  segment.addEventListener('mouseleave', hide);
  segment.addEventListener('pointerleave', hide);
}

function formatPumpTime(date) {
  return date.toLocaleTimeString('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function formatPumpDate(date) {
  return date.toLocaleDateString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function formatPumpDuration(durationMs) {
  const totalSeconds = Math.floor(durationMs / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts = [];
  if (days) parts.push(`${days} ngày`);
  if (hours) parts.push(`${hours} giờ`);
  if (minutes || !parts.length) parts.push(`${minutes} phút`);
  if (seconds && !days) parts.push(`${seconds} giây`);
  return parts.join(' ');
}

function formatChartTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatChartTimestamp(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return String(timestamp).replace('T', ' ').replace(/\.\d{3}Z?$/, '').replace(/Z$/, '');
  }
  const pad = value => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + ` ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatChartTooltipTimestamp(timestamp, isMarker, displayNow) {
  return formatChartTimestamp(timestamp);
}

function updateChartStats(records) {
  if (!records || !records.length) {
    setText('chart-stat-max', '--');
    setText('chart-stat-max-time', '--');
    setText('chart-stat-min', '--');
    setText('chart-stat-min-time', '--');
    setText('chart-stat-avg', '--');
    setText('chart-stat-dist', '--');
    return;
  }
  const validRecords = records.filter(record =>
    Number.isFinite(Number(record.water_level))
    && Number.isFinite(Number(record.distance_cm))
  );
  if (!validRecords.length) {
    updateChartStats([]);
    return;
  }
  const levels = validRecords.map(r => +r.water_level);
  const dists  = validRecords.map(r => +r.distance_cm);

  let maxLvl = levels[0], minLvl = levels[0];
  let maxIdx = 0, minIdx = 0;
  let sumLvl = 0, sumDist = 0;

  levels.forEach((l, i) => {
    if (l > maxLvl) { maxLvl = l; maxIdx = i; }
    if (l < minLvl) { minLvl = l; minIdx = i; }
    sumLvl += l;
    sumDist += (dists[i] || 0);
  });

  const avgLvl  = (sumLvl / levels.length).toFixed(1);
  const avgDist = (sumDist / levels.length).toFixed(1);
  const maxTime = validRecords[maxIdx]?.recorded_at
    ? formatChartTimestamp(validRecords[maxIdx].recorded_at).slice(11, 19)
    : '--';
  const minTime = validRecords[minIdx]?.recorded_at
    ? formatChartTimestamp(validRecords[minIdx].recorded_at).slice(11, 19)
    : '--';

  setText('chart-stat-max', `${maxLvl.toFixed(1)} %`);
  setText('chart-stat-max-time', maxTime === '--' ? '--' : `(${maxTime})`);
  setText('chart-stat-min', `${minLvl.toFixed(1)} %`);
  setText('chart-stat-min-time', minTime === '--' ? '--' : `(${minTime})`);
  setText('chart-stat-avg', `${avgLvl} %`);
  setText('chart-stat-dist', `${avgDist} cm`);
}

function generateMockChartSeries(period) {
  const pointMap = { '30m': 180, '1h': 120, '6h': 120, '7d': 168, '30d': 120 };
  const minutesMap = { '30m': 30, '1h': 60, '6h': 360, '7d': 10080, '30d': 43200 };
  const pts = pointMap[period] || 180;
  const totalMinutes = minutesMap[period] || 30;
  const out = [];
  const now = Date.now();
  for (let i = 0; i < pts; i++) {
    const progress = i / Math.max(pts - 1, 1);
    const t = new Date(now - (pts - 1 - i) * (totalMinutes * 60000 / Math.max(pts - 1, 1)));
    const level = Math.max(5, Math.min(95,
      45 + Math.sin(progress * Math.PI * 3) * 10 + (Math.random() - 0.5) * 3
    ));
    out.push({
      recorded_at: t.toISOString(),
      water_level: +level.toFixed(1),
      distance_cm: +(100 - level * 0.9).toFixed(1),
      pump_in: level < 35 ? 1 : 0,
      pump_out: level > 85 ? 1 : 0,
    });
  }
  return out;
}

function changeChartPeriod(period, btn) {
  document.querySelectorAll('#chart-period-tabs .period-pill').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  updateChartPeriodInfo(period);
  loadChart(period);
}

function updateChartPeriodInfo(period, range = null) {
  const periodInfo = {
    '30m': { range: '30 phút gần nhất', interval: '5 giây' },
    '1h': { range: '1 giờ gần nhất', interval: '10 giây' },
    '6h': { range: '6 giờ gần nhất', interval: '1 giờ' },
    '7d': { range: '7 ngày gần nhất', interval: '1 ngày' },
    '30d': { range: '30 ngày gần nhất', interval: '5 ngày' },
  };
  const selected = periodInfo[period] || periodInfo['30m'];
  const info = document.getElementById('chart-period-info');
  if (!info) return;
  const rangeText = range?.start && range?.end
    ? ` · ${formatChartRangeTimestamp(range.start)} → ${formatChartRangeTimestamp(range.end)}`
    : '';
  const intervalText = period === '7d' || period === '30d'
    ? `<br>Mỗi điểm trên biểu đồ là giá trị trung bình trong ${selected.interval}.`
    : '';
  info.innerHTML = `<span class="chart-period-info-icon">◷</span>
    <span>Đang xem: <strong>${selected.range}</strong>${rangeText}${intervalText}</span>`;
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE 3: ĐIỀU KHIỂN (Control Page)
// ══════════════════════════════════════════════════════════════════════════════
let currentControlLogFilter = '';
let pendingMode = null;
let pendingModeAt = 0;

async function loadControlPage() {
  try {
    const status = await safeAPI.status();
    const rec = getLatestRecord(status);
    if (pendingMode && rec.auto_mode === (pendingMode === 'AUTO' ? 1 : 0)) {
      pendingMode = null;
    } else if (pendingMode && Date.now() - pendingModeAt > 5000) {
      pendingMode = null;
    }
    if (pendingMode) rec.auto_mode = pendingMode === 'AUTO' ? 1 : 0;

    // 1. Cập nhật 4 thẻ trạng thái trên cùng
    setText('ctrl-ov-level', fmt.pct(rec.water_level != null ? rec.water_level : 45.5));
    setText('ctrl-ov-dist', `Khoảng cách: ${rec.distance_cm != null ? rec.distance_cm.toFixed(1) : '56.7'} cm`);
    const deviceOnline = status.device_online === true;
    setText('ctrl-ov-esp32', deviceOnline ? (rec.sensor_err ? 'Error' : 'Online') : 'Offline');
    setText('ctrl-ov-rssi', `RSSI: ${rec.rssi != null ? rec.rssi : -55} dBm`);
    setText('ctrl-ov-mqtt', status.mqtt_connected ? 'Đã kết nối' : 'Đã kết nối');
    setText('ctrl-ov-mode', deviceOnline && rec.auto_mode != null
      ? (rec.auto_mode ? 'AUTO' : 'MANUAL')
      : '--');

    // 2. Cập nhật 2 thẻ chế độ AUTO / MANUAL
    const isAuto = deviceOnline && rec.auto_mode !== 0;
    const cardAuto = document.getElementById('mode-card-auto');
    const cardMan  = document.getElementById('mode-card-manual');
    if (cardAuto && cardMan) {
      if (!deviceOnline) {
        cardAuto.className = 'mode-select-card';
        cardMan.className  = 'mode-select-card';
      } else if (isAuto) {
        cardAuto.className = 'mode-select-card active';
        cardMan.className  = 'mode-select-card';
      } else {
        cardAuto.className = 'mode-select-card';
        cardMan.className  = 'mode-select-card active manual-active';
      }
    }

    // 3. Cập nhật trạng thái máy bơm
    const pInOn  = !!rec.pump_in;
    const pOutOn = !!rec.pump_out;

    setText('ctrl-p-in-txt',  pInOn  ? 'Bật' : 'Tắt');
    setText('ctrl-p-in-dot',  pInOn  ? '🟢' : '🔴');
    setText('ctrl-p-out-txt', pOutOn ? 'Bật' : 'Tắt');
    setText('ctrl-p-out-dot', pOutOn ? '🟢' : '🔴');

    // 4. Hiển thị phản hồi mới nhất từ cùng nguồn dữ liệu với lịch sử
    const latestLogs = await safeAPI.controlLogs({ page: 1, limit: 1 });
    updateLatestFeedback(latestLogs.data?.[0]);
    await loadControlLogsTable();

  } catch (e) {
    console.error('loadControlPage error:', e);
  }

  function updateLatestFeedback(log) {
    const icon = document.getElementById('feedback-icon');
    if (!log) {
      setText('feedback-time', '--');
      setText('feedback-cmd', 'Chưa có lệnh điều khiển');
      setText('feedback-result', 'Chưa có phản hồi');
      const emptyResult = document.getElementById('feedback-result');
      if (emptyResult) emptyResult.className = 'feedback-result text-muted';
      return;
    }

    const device = log.device
      || (log.command === 'pump_in' ? 'Bơm cấp (IN)'
        : log.command === 'pump_out' ? 'Bơm thoát (OUT)' : 'Chế độ');
    const payload = log.payload || '--';
    const result = log.ack_payload || (
      log.status === 'ACK_OK' ? 'Thành công'
        : log.status === 'ACK_ERR' ? 'Bị từ chối'
          : log.status === 'TIMEOUT' ? 'Hết hạn' : 'Đang chờ phản hồi...'
    );
    const statusClass = log.status === 'ACK_OK' ? 'text-success'
      : log.status === 'ACK_ERR' || log.status === 'TIMEOUT' ? 'text-danger'
        : 'text-muted';

    setText('feedback-time', fmt.dt(log.sent_at).slice(11, 19) || '--');
    setText('feedback-cmd', `Nhận lệnh: ${log.command === 'pump_in' || log.command === 'pump_out'
      ? `${payload === 'ON' || payload === 'Bật' ? 'Bật' : 'Tắt'} ${device}`
      : `${device} ${payload}`}`);
    setText('feedback-result', `Kết quả: ${result}`);
    const resultEl = document.getElementById('feedback-result');
    if (resultEl) resultEl.className = `feedback-result ${statusClass}`;
    if (icon) icon.textContent = log.status === 'ACK_OK' ? '✓' : '!';
  }
}

async function setMode(mode) {
  try {
    toast(`Đang gửi lệnh chuyển sang chế độ ${mode}...`, 'info', 1500);
    const res = await safeAPI.control('mode', mode);
    if (!res || !res.ok) {
      toast(`❌ Lỗi gửi lệnh chế độ: ${res?.error || 'Thao tác không thành công'}`, 'error');
      return;
    }
    pendingMode = mode;
    pendingModeAt = Date.now();
    const isAuto = mode === 'AUTO';
    const cardAuto = document.getElementById('mode-card-auto');
    const cardManual = document.getElementById('mode-card-manual');
    if (cardAuto && cardManual) {
      cardAuto.className = `mode-select-card${isAuto ? ' active' : ''}`;
      cardManual.className = `mode-select-card${isAuto ? '' : ' active manual-active'}`;
    }
    setText('ctrl-ov-mode', mode);
    updateFeedback('mode', mode, 'Đã gửi lệnh (chờ ESP32 xác nhận)');
    toast(`Đã gửi lệnh chuyển sang chế độ ${mode}`, 'success');
    setTimeout(loadControlPage, 1500);
  } catch (e) {
    toast(`❌ Lỗi gửi lệnh chế độ: ${e.message || 'Mất kết nối'}`, 'error');
  }
}

async function sendPumpCmd(pump, state) {
  try {
    const pumpName = pump === 'pump_in' ? 'bơm cấp (IN)' : 'bơm thoát (OUT)';
    toast(`Đang gửi lệnh ${state === 'ON' ? 'Bật' : 'Tắt'} ${pumpName}...`, 'info', 1500);
    const res = await safeAPI.control(pump, state);
    if (!res || !res.ok) {
      toast(`❌ Lỗi gửi lệnh bơm: ${res?.error || 'Thao tác không thành công'}`, 'error');
      return;
    }
    updateFeedback(pump, state, 'Đã gửi lệnh (chờ ESP32 xác nhận)');
    if (res.warning) {
      toast(`⚠️ ${res.warning}`, 'warning', 6000);
    } else {
      toast(`Đã gửi lệnh: ${state === 'ON' ? 'Bật' : 'Tắt'} ${pumpName}`, 'success');
    }
    setTimeout(loadControlPage, 1500);
  } catch (e) {
    toast(`❌ Lỗi khi gửi lệnh bơm: ${e.message || 'Mất kết nối'}`, 'error');
  }
}

function showControlWarning(result) {
  if (result?.warning) toast(`⚠️ ${result.warning}`, 'warning', 6000);
  return result;
}

async function quickAction(action) {
  try {
    let desc = '';
    if (action === 'both_on') {
      showControlWarning(await safeAPI.control('pump_in', 'ON'));
      showControlWarning(await safeAPI.control('pump_out', 'ON'));
      desc = 'Bật cả hai bơm';
    } else if (action === 'both_off') {
      showControlWarning(await safeAPI.control('pump_in', 'OFF'));
      showControlWarning(await safeAPI.control('pump_out', 'OFF'));
      desc = 'Tắt cả hai bơm';
    } else if (action === 'in_on') {
      showControlWarning(await safeAPI.control('pump_in', 'ON'));
      showControlWarning(await safeAPI.control('pump_out', 'OFF'));
      desc = 'Chỉ bật bơm cấp (IN)';
    } else if (action === 'out_on') {
      showControlWarning(await safeAPI.control('pump_out', 'ON'));
      showControlWarning(await safeAPI.control('pump_in', 'OFF'));
      desc = 'Chỉ bật bơm thoát (OUT)';
    }

    updateFeedback('quick', desc);
    toast(`Đã thực hiện thao tác nhanh: ${desc}`, 'success');
    setTimeout(loadControlPage, 600);
  } catch (e) {
    toast('Lỗi khi thực hiện thao tác nhanh', 'error');
  }
}

function updateFeedback(cmdType, val, resultStatus = 'Đã gửi (đang chờ ACK)') {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('vi');
  setText('feedback-time', timeStr);

  let cmdLabel = '';
  if (cmdType === 'mode') {
    cmdLabel = `Lệnh: Chuyển sang chế độ ${val}`;
  } else if (cmdType === 'pump_in') {
    cmdLabel = `Lệnh: ${val === 'ON' ? 'Bật' : 'Tắt'} bơm cấp (IN)`;
  } else if (cmdType === 'pump_out') {
    cmdLabel = `Lệnh: ${val === 'ON' ? 'Bật' : 'Tắt'} bơm thoát (OUT)`;
  } else {
    cmdLabel = `Lệnh: ${val}`;
  }

  setText('feedback-cmd', cmdLabel);
  setText('feedback-result', `Kết quả: ${resultStatus}`);
}

async function loadControlLogsTable(page = ctrlLogPage) {
  const tbody = document.getElementById('ctrl-log-tbody');
  if (!tbody) return;

  ctrlLogPage = page;
  const dateFrom = document.getElementById('ctrl-log-date-from')?.value || '';
  const dateTo = document.getElementById('ctrl-log-date-to')?.value || '';
  const devFilter = document.getElementById('ctrl-log-device')?.value || '';
  const data = await safeAPI.controlLogs({
    page,
    limit: 10,
    from: dateFrom,
    to: dateTo,
    device: devFilter,
  });
  let rows = data.data || [];

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px" class="text-muted">Chưa có bản ghi nào</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(r => {
    const isRed = r.payload === 'Bật' || r.payload === 'ON';
    const payloadHtml = isRed
      ? `<span class="text-danger fw-600">${escapeHtml(r.payload)}</span>`
      : `<span>${escapeHtml(r.payload)}</span>`;

    const devLabel = r.device || (r.command === 'pump_in' ? 'Bơm cấp (IN)' : r.command === 'pump_out' ? 'Bơm thoát (OUT)' : 'Chế độ');
    const timeFormatted = fmt.dt(r.sent_at);

    let statusHtml = '';
    if (r.status === 'ACK_OK') {
      statusHtml = '<span class="badge badge-success">Thành công</span>';
    } else if (r.status === 'ACK_ERR') {
      statusHtml = '<span class="badge badge-danger">Bị từ chối</span>';
    } else if (r.status === 'TIMEOUT') {
      statusHtml = '<span class="badge badge-warning">Hết hạn</span>';
    } else {
      statusHtml = '<span class="badge badge-info">Đang chờ ACK</span>';
    }

    const ackDesc = r.ack_payload
      ? escapeHtml(r.ack_payload)
      : (r.status === 'SENT' ? '<span class="text-muted">Đang chờ phản hồi...</span>' : '--');

    return `<tr>
      <td style="font-size:12.5px;color:#334155">${timeFormatted}</td>
      <td style="font-weight:500">${escapeHtml(devLabel)}</td>
      <td>${payloadHtml}</td>
      <td>${statusHtml}</td>
      <td style="color:#475569">${ackDesc}</td>
      <td style="color:#64748b">${escapeHtml(r.initiated_by || 'Admin')}</td>
    </tr>`;
  }).join('');

  setText('ctrl-log-total-info', `Tổng: ${data.total || rows.length} bản ghi`);

  // Render pagination controls
  renderPagination(
    'ctrl-log-pages',
    ctrlLogPage,
    Math.ceil((data.total || rows.length) / 10) || 1,
    loadControlLogsTable
  );
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE 4: CẤU HÌNH
// ══════════════════════════════════════════════════════════════════════════════
async function loadConfig(showToast = false) {
  try {
    const data = await safeAPI.config();
    const cfg = data.config || {};
    const runtimeConfig = data.runtime_config || {};
    configCache = cfg;

    setVal('cfg-in-on',      cfg.in_on_pct   || 30);
    setVal('cfg-in-off',     cfg.in_off_pct  || 50);
    setVal('cfg-out-on',     cfg.out_on_pct  || 90);
    setVal('cfg-out-off',    cfg.out_off_pct || 80);
    setVal('cfg-d-empty',    cfg.d_empty     || 100);
    setVal('cfg-d-full',     cfg.d_full      || 10);
    setVal('cfg-limit-high', cfg.limit_high  || 95);
    setVal('cfg-limit-low',  cfg.limit_low   || 5);
    setVal('cfg-max-run',    cfg.max_run_min || 20);
    setVal('cfg-publish-sec',cfg.publish_sec || 2);
    setVal('cfg-mqtt-broker',runtimeConfig.mqtt_broker || cfg.mqtt_broker || '192.168.1.100');
    setVal('cfg-mqtt-port',  runtimeConfig.mqtt_port   || cfg.mqtt_port   || 1883);
    setVal('cfg-topic-prefix',runtimeConfig.topic_prefix || cfg.topic_prefix || 'iot');

    // Config table: hiển thị cấu hình từ ESP32 nếu có phản hồi, kết hợp cấu hình đã lưu
    const tbody = document.getElementById('cfg-table-body');
    if (tbody) {
      const desc = {
        d_empty:'Khoảng cách khi ao cạn (cm)', d_full:'Khoảng cách khi ao đầy (cm)',
        in_on_pct:'Ngưỡng bật bơm cấp (%)', in_off_pct:'Ngưỡng tắt bơm cấp (%)',
        out_on_pct:'Ngưỡng bật bơm thoát (%)', out_off_pct:'Ngưỡng tắt bơm thoát (%)',
        limit_high:'Ngưỡng cảnh báo cao (%)', limit_low:'Ngưỡng cảnh báo thấp (%)',
        max_run_min:'Bơm chạy tối đa (phút)', publish_sec:'Chu kỳ MQTT (giây)',
        mqtt_broker:'MQTT Broker IP', mqtt_port:'MQTT Port',
        topic_prefix:'Topic Prefix', web_version:'Phiên bản',
      };

      const reported = data.esp32_reported || null;
      const hiddenConfigKeys = new Set(['alert_led', 'alert_buzzer']);
      let rowsHtml = Object.entries(cfg)
        .filter(([k]) => !hiddenConfigKeys.has(k))
        .map(([k,v]) => {
          let espVal = '';
          if (reported) {
            if (k === 'in_on_pct' && reported.inOn != null) espVal = ` <span class="badge badge-info" title="ESP32 phản hồi">ESP32: ${reported.inOn}%</span>`;
            else if (k === 'in_off_pct' && reported.inOff != null) espVal = ` <span class="badge badge-info" title="ESP32 phản hồi">ESP32: ${reported.inOff}%</span>`;
            else if (k === 'out_on_pct' && reported.outOn != null) espVal = ` <span class="badge badge-info" title="ESP32 phản hồi">ESP32: ${reported.outOn}%</span>`;
            else if (k === 'out_off_pct' && reported.outOff != null) espVal = ` <span class="badge badge-info" title="ESP32 phản hồi">ESP32: ${reported.outOff}%</span>`;
            else if (k === 'd_empty' && reported.dEmpty != null) espVal = ` <span class="badge badge-info" title="ESP32 phản hồi">ESP32: ${reported.dEmpty}cm</span>`;
            else if (k === 'd_full' && reported.dFull != null) espVal = ` <span class="badge badge-info" title="ESP32 phản hồi">ESP32: ${reported.dFull}cm</span>`;
          }
          return `<tr><td><code>${escapeHtml(k)}</code></td><td><strong>${escapeHtml(v)}</strong>${espVal}</td><td style="color:var(--text-secondary);font-size:12px">${desc[k]||''}</td></tr>`;
        }).join('');

      tbody.innerHTML = rowsHtml;
    }

    if (showToast) {
      toast('🔄 Đã tải lại cấu hình từ server!', 'info');
    }

  } catch(e) {
    console.error('loadConfig error:', e);
    if (showToast) toast('❌ Không thể tải cấu hình từ server', 'error');
  }
}

async function saveAndSendConfig() {
  const data = {
    in_on_pct:   getVal('cfg-in-on'),
    in_off_pct:  getVal('cfg-in-off'),
    out_on_pct:  getVal('cfg-out-on'),
    out_off_pct: getVal('cfg-out-off'),
    d_empty:     getVal('cfg-d-empty'),
    d_full:      getVal('cfg-d-full'),
    limit_high:  getVal('cfg-limit-high'),
    limit_low:   getVal('cfg-limit-low'),
    max_run_min: getVal('cfg-max-run'),
    publish_sec: getVal('cfg-publish-sec'),
    mqtt_broker: getVal('cfg-mqtt-broker'),
    mqtt_port:   getVal('cfg-mqtt-port'),
    topic_prefix:getVal('cfg-topic-prefix'),
  };

  // Validate
  if (+data.in_on_pct >= +data.in_off_pct) {
    toast('Ngưỡng bật bơm cấp (inOn) phải nhỏ hơn ngưỡng tắt (inOff)', 'warning');
    return;
  }
  if (+data.in_off_pct >= +data.out_off_pct) {
    toast('Ngưỡng tắt bơm cấp (inOff) phải nhỏ hơn ngưỡng tắt bơm thoát (outOff)', 'warning');
    return;
  }
  if (+data.out_off_pct >= +data.out_on_pct) {
    toast('Ngưỡng tắt bơm thoát (outOff) phải nhỏ hơn ngưỡng bật (outOn)', 'warning');
    return;
  }
  if (+data.d_full >= +data.d_empty - 5) {
    toast('dFull phải nhỏ hơn dEmpty ít nhất 5cm', 'warning');
    return;
  }

  try {
    toast('Đang lưu cấu hình và gửi xuống ESP32...', 'info', 2000);
    const r = await safeAPI.saveConfig(data);
    if (!r || !r.ok) {
      toast(`❌ Lỗi lưu cấu hình: ${r?.error || 'Thao tác không thành công'}`, 'error');
      return;
    }
    if (r.warning) {
      toast(`⚠️ ${r.warning}`, 'warning', 6000);
    } else {
      toast('✅ Đã lưu và ESP32 xác nhận cập nhật cấu hình', 'success');
    }
    loadConfig();
  } catch (err) {
    toast(`❌ Lỗi kết nối: ${err.message || 'Mất kết nối máy chủ'}`, 'error');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE 5: CẢNH BÁO
// ══════════════════════════════════════════════════════════════════════════════
async function loadAlerts(page = alertPage) {
  alertPage = page;
  const sev    = document.getElementById('alert-filter-sev')?.value || '';
  const status = document.getElementById('alert-filter-status')?.value || '';
  const from   = document.getElementById('alert-date-from')?.value || '';
  const to     = document.getElementById('alert-date-to')?.value || '';

  const params = { page, limit:20 };
  if (sev)    params.severity = sev;
  if (status) params.status   = status;
  if (from)   params.from     = from;
  if (to)     params.to       = to;

  try {
    const data = await safeAPI.alerts(params);
    const stats = data.stats_24h || {};

    setText('alert-cnt-danger',  stats.DANGER  || 0);
    setText('alert-cnt-warning', stats.WARNING || 0);
    setText('alert-cnt-info',    stats.INFO    || 0);

    const rows = data.data || [];
    const tbody = document.getElementById('alert-tbody');
    if (!tbody) return;

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:30px" class="text-muted">Không có cảnh báo nào</td></tr>';
    } else {
      tbody.innerHTML = rows.map(a =>
        `<tr>
           <td style="font-size:12px;white-space:nowrap">${fmt.dt(a.created_at)}</td>
           <td>${sevBadge(a.severity)}</td>
           <td><code style="font-size:12px">${a.alert_code}</code></td>
           <td>${a.message}</td>
           <td>${a.value_str || '<span class="text-muted">–</span>'}</td>
           <td>${a.status === 'UNRESOLVED'
               ? '<span class="badge badge-danger">Chưa xử lý</span>'
               : '<span class="badge badge-success">Đã xử lý</span>'}</td>
           <td>
             <button class="btn btn-outline btn-sm" onclick="viewAlert(${a.id},'${escapeHtml(a.message)}')">Xem</button>
           </td>
         </tr>`
      ).join('');
    }

    const total = data.total || 0;
    const totalPages = Math.ceil(total / 20) || 1;
    setText('alert-info', `Tổng: ${total} bản ghi`);
    renderPagination('alert-pages', alertPage, totalPages, loadAlerts);

  } catch(e) { console.error('loadAlerts error:', e); }
}

function viewAlert(id, msg) {
  setText('alert-modal-title', `Cảnh báo #${id}`);
  setText('alert-modal-message', msg || 'Không có nội dung cảnh báo.');
  const modal = document.getElementById('alert-modal');
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add('modal-open');
}

function closeAlertModal(event) {
  if (event && event.target !== event.currentTarget) return;
  const modal = document.getElementById('alert-modal');
  if (modal) modal.hidden = true;
  document.body.classList.remove('modal-open');
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE 6: LỊCH SỬ DỮ LIỆU
// ══════════════════════════════════════════════════════════════════════════════
let histPreset = 'today';
let historyTab = 'sensor';
let logPage = 1;

function switchHistoryTab(tab, btn) {
  historyTab = tab;
  document.querySelectorAll('.history-tab').forEach(item => item.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const sensorPanel = document.getElementById('history-sensor-panel');
  const logsPanel = document.getElementById('history-logs-panel');
  if (sensorPanel) sensorPanel.style.display = tab === 'sensor' ? '' : 'none';
  if (logsPanel) logsPanel.style.display = tab === 'logs' ? '' : 'none';
  if (tab === 'logs') loadSystemLogs();
  else loadHistory();
}

function getLocalDateString(date = new Date()) {
  const pad = value => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function setHistoryPreset(preset, btn) {
  histPreset = preset;
  document.querySelectorAll('#history-sensor-panel .tab-bar .tab-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  const today = getLocalDateString();
  const pastN = days => getLocalDateString(new Date(Date.now() - days * 86400000));

  const fromEl = document.getElementById('hist-from');
  const toEl   = document.getElementById('hist-to');
  if (!fromEl || !toEl) return;

  if (preset === 'today')  { fromEl.value = today;    toEl.value = today; }
  else if (preset === '7d'){ fromEl.value = pastN(7); toEl.value = today; }
  else if (preset==='30d') { fromEl.value = pastN(30);toEl.value = today; }
  else                     { fromEl.value = '';        toEl.value = ''; }

  histPage = 1;
  loadHistory();
}

function applyHistoryFilter() {
  histPage = 1;
  loadHistory();
}

function changeHistoryLimit() {
  histPage = 1;
  loadHistory();
}

async function loadHistory(page = histPage) {
  histPage = page;
  const from  = document.getElementById('hist-from')?.value;
  const to    = document.getElementById('hist-to')?.value;
  const limit = parseInt(document.getElementById('hist-limit')?.value || 20);

  const params = { page, limit };
  if (histPreset === 'all' && !from && !to) {
    // Dùng khoảng ngày mở rộng để tương thích với backend cũ chưa hỗ trợ
    // tham số `all`; sau khi backend mới chạy, `all=1` vẫn được hỗ trợ.
    params.from = '1970-01-01';
    params.to = getLocalDateString();
    params.all = 1;
  } else {
    if (from) params.from = from;
    if (to)   params.to   = to;
  }

  try {
    const data = await safeAPI.sensor(params);
    const rows = data.data || [];
    const tbody = document.getElementById('hist-tbody');
    if (!tbody) return;

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:30px" class="text-muted">Không có dữ liệu</td></tr>';
    } else {
      tbody.innerHTML = rows.map(r =>
        `<tr>
           <td style="font-size:12px;color:var(--accent)">${fmt.dt(r.recorded_at)}</td>
           <td><strong>${fmt.pct(r.water_level)}</strong></td>
           <td>${fmt.cm(r.distance_cm)}</td>
           <td>${pumpBadge(r.pump_in)}</td>
           <td>${pumpBadge(r.pump_out)}</td>
           <td>${modeBadge(r.auto_mode)}</td>
           <td>${r.sensor_err ? '<span class="text-danger">Lỗi</span>' : '<span class="text-success">OK</span>'}</td>
         </tr>`
      ).join('');
    }

    const total = data.total || 0;
    const totalPages = Math.ceil(total / limit) || 1;
    setText('hist-info', `Hiển thị ${rows.length} / Tổng: ${total} bản ghi`);
    renderPagination('hist-pages', histPage, totalPages, loadHistory);

  } catch(e) { console.error('loadHistory error:', e); }
}

function exportCSV() {
  const rows = document.querySelectorAll('#hist-tbody tr');
  if (!rows.length) { toast('Không có dữ liệu để xuất', 'warning'); return; }
  const headers = ['Thời gian','Mực nước (%)','Khoảng cách (cm)','Bơm cấp','Bơm thoát','Chế độ','Lỗi'];
  let csv = headers.join(',') + '\n';
  rows.forEach(row => {
    const cells = [...row.querySelectorAll('td')].map(td => `"${td.innerText.trim().replace(/"/g, '""')}"`);
    csv += cells.join(',') + '\n';
  });
  const blob = new Blob(['\uFEFF' + csv], { type:'text/csv;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = `ao_nuoi_data_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  toast('Đã xuất CSV', 'success');
}

function exportExcel() {
  const rows = document.querySelectorAll('#hist-tbody tr');
  if (!rows.length) { toast('Không có dữ liệu để xuất', 'warning'); return; }
  const headers = ['Thời gian','Mực nước (%)','Khoảng cách (cm)','Bơm cấp','Bơm thoát','Chế độ','Lỗi'];
  let tableHtml = '<table border="1"><tr>' + headers.map(h => `<th style="background:#2563eb;color:#fff;font-weight:bold">${h}</th>`).join('') + '</tr>';
  rows.forEach(row => {
    const cells = [...row.querySelectorAll('td')].map(td => `<td>${td.innerText.trim()}</td>`);
    tableHtml += '<tr>' + cells.join('') + '</tr>';
  });
  tableHtml += '</table>';
  const template = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="UTF-8"><!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet><x:Name>DuLieuAoNuoi</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]--></head><body>${tableHtml}</body></html>`;
  const blob = new Blob(['\uFEFF' + template], { type: 'application/vnd.ms-excel;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = `ao_nuoi_data_${new Date().toISOString().slice(0,10)}.xls`;
  a.click();
  URL.revokeObjectURL(url);
  toast('Đã xuất Excel thành công', 'success');
}

function logLevelBadge(level) {
  const normalized = String(level || 'INFO').toUpperCase();
  const classes = { INFO: 'info', SUCCESS: 'success', WARNING: 'warning', ERROR: 'danger' };
  return `<span class="badge badge-${classes[normalized] || 'gray'}">${normalized}</span>`;
}

function logComponentName(component) {
  const names = { mqtt: 'MQTT', flask: 'Hệ thống', esp32: 'ESP32', sensor: 'Cảm biến', system: 'Hệ thống' };
  return names[String(component || '').toLowerCase()] || component || '--';
}

function applyLogFilter() {
  logPage = 1;
  loadSystemLogs();
}

function changeLogLimit() {
  logPage = 1;
  loadSystemLogs();
}

async function loadSystemLogs(page = logPage) {
  logPage = page;
  const params = {
    page,
    limit: parseInt(document.getElementById('log-limit')?.value || 15),
  };
  const from = document.getElementById('log-from')?.value;
  const to = document.getElementById('log-to')?.value;
  const level = document.getElementById('log-level')?.value;
  const component = document.getElementById('log-component')?.value;
  if (from) params.from = from;
  if (to) params.to = to;
  if (level) params.level = level;
  if (component) params.component = component;

  try {
    const data = await safeAPI.logs(params);
    const rows = data.data || [];
    const tbody = document.getElementById('log-tbody');
    if (!tbody) return;
    tbody.innerHTML = rows.length
      ? rows.map(log => `<tr>
          <td style="font-size:12px;color:var(--accent);white-space:nowrap">${fmt.dt(log.logged_at)}</td>
          <td>${logLevelBadge(log.log_level)}</td>
          <td>${logComponentName(log.component)}</td>
          <td>${log.message || '--'}</td>
        </tr>`).join('')
      : '<tr><td colspan="4" style="text-align:center;padding:30px" class="text-muted">Không có nhật ký trong khoảng thời gian này</td></tr>';

    const limit = params.limit;
    const total = data.total || 0;
    setText('log-info', `Hiển thị ${rows.length} / Tổng: ${total} bản ghi`);
    renderPagination('log-pages', logPage, Math.ceil(total / limit) || 1, loadSystemLogs);
  } catch (e) {
    console.error('loadSystemLogs error:', e);
  }
}

function exportLogsCSV() {
  const rows = document.querySelectorAll('#log-tbody tr');
  if (!rows.length) { toast('Không có nhật ký để xuất', 'warning'); return; }
  const headers = ['Thời gian', 'Mức độ', 'Thành phần', 'Nội dung'];
  let csv = headers.join(',') + '\n';
  rows.forEach(row => {
    csv += [...row.querySelectorAll('td')].map(td => `"${td.innerText.trim().replaceAll('"', '""')}"`).join(',') + '\n';
  });
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `nhat_ky_he_thong_${getLocalDateString()}.csv`; a.click();
  URL.revokeObjectURL(url);
  toast('Đã xuất nhật ký CSV', 'success');
}

function exportLogsExcel() {
  const rows = document.querySelectorAll('#log-tbody tr');
  if (!rows.length) { toast('Không có nhật ký để xuất', 'warning'); return; }
  const headers = ['Thời gian', 'Mức độ', 'Thành phần', 'Nội dung'];
  const body = [...rows].map(row => '<tr>' + [...row.querySelectorAll('td')].map(td => `<td>${td.innerText.trim()}</td>`).join('') + '</tr>').join('');
  const html = `<table border="1"><tr>${headers.map(h => `<th style="background:#2563eb;color:#fff">${h}</th>`).join('')}</tr>${body}</table>`;
  const blob = new Blob(['\uFEFF' + html], { type: 'application/vnd.ms-excel;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `nhat_ky_he_thong_${getLocalDateString()}.xls`; a.click();
  URL.revokeObjectURL(url);
  toast('Đã xuất nhật ký Excel', 'success');
}

// ── DOM helpers ───────────────────────────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}
function getVal(id) {
  return document.getElementById(id)?.value || '';
}
function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

window.sendCmd = async function(command, payload = '1') {
  if (command === 'restart') {
    if (!confirm('⚡ Bạn có chắc chắn muốn khởi động lại vi điều khiển ESP32 không?')) return;
  } else if (command === 'reset') {
    if (!confirm('⚠ Bạn có chắc chắn muốn xóa lỗi chốt và đặt lại trạng thái cảnh báo?')) return;
  }

  try {
    toast(`Đang gửi lệnh ${command}...`, 'info', 2000);
    const res = await safeAPI.control(command, payload);
    if (res && res.ok) {
      if (command === 'restart') {
        toast('✅ Đã gửi lệnh khởi động lại ESP32 thành công!', 'success');
      } else if (command === 'reset') {
        toast('✅ Đã gửi yêu cầu xóa lỗi chốt (ESP32 đang kiểm tra an toàn)...', 'info');
        setTimeout(async () => {
          try {
            const logs = await safeAPI.controlLogs({ limit: 5 });
            const resetLog = (logs.data || []).find(l => l.command === 'reset');
            if (resetLog) {
              if (resetLog.status === 'ACK_OK') {
                toast('✅ ESP32 xác nhận đủ điều kiện an toàn: Đã xóa lỗi chốt (chuyển sang MANUAL)!', 'success', 5000);
              } else if (resetLog.status === 'ACK_ERR' && (resetLog.ack_payload || '').includes('reset_unsafe')) {
                toast(`⛔ ESP32 từ chối xóa lỗi: Điều kiện chưa an toàn (${resetLog.ack_payload})! Vui lòng khắc phục sự cố vật lý trước.`, 'error', 7000);
              }
            }
          } catch (_) {}
          loadAlerts();
          loadControlPage();
        }, 1200);
      } else if (command === 'get') {
        toast('✅ Đã yêu cầu ESP32 gửi lại cấu hình!', 'success');
        setTimeout(loadConfig, 1500);
      } else {
        toast(`✅ Lệnh ${command} đã gửi thành công!`, 'success');
      }
      setTimeout(loadControlPage, 800);
    } else {
      toast(`❌ Lỗi gửi lệnh: ${res?.error || 'Thao tác không thành công'}`, 'error');
    }
  } catch (err) {
    toast(`❌ Lỗi gửi lệnh: ${err.message || 'Mất kết nối máy chủ'}`, 'error');
  }
};

// ── Auto-refresh ──────────────────────────────────────────────────────────────
function startAutoRefresh() {
  autoRefreshTimer = setInterval(() => {
    if (currentPage === 'tong-quan') {
      loadOverview();
    } else if (currentPage === 'dieu-khien') {
      loadControlPage();
    }
  }, 5000);
}

// ── Init ──────────────────────────────────────────────────────────────────────
(function init() {
  updateClock();
  setInterval(updateClock, 1000);

  // Set today's dates for history filters
  const today = getLocalDateString();
  const histFrom = document.getElementById('hist-from');
  const histTo   = document.getElementById('hist-to');
  if (histFrom) histFrom.value = today;
  if (histTo)   histTo.value   = today;
  const logFrom = document.getElementById('log-from');
  const logTo   = document.getElementById('log-to');
  if (logFrom) logFrom.value = today;
  if (logTo) logTo.value = today;

  loadOverview();
  startAutoRefresh();
})();
