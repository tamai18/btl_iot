// ============================================================================
//  chat.js – Trợ lý AI (Chatbox) Frontend Logic
//  Xử lý tương tác gửi nhận tin nhắn, câu hỏi gợi ý, xác nhận điều khiển
// ============================================================================

(function () {
  'use strict';

  // Biến lưu trữ phiên hội thoại trong bộ nhớ
  let chatHistory = [];
  let isSending = false;

  // ── Helper: Escape HTML phòng chống XSS ──────────────────────────────────
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ── Helper: Lấy thời gian HH:MM:SS hiện tại ──────────────────────────────
  function getCurrentTimeStr() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  // ── Khởi tạo trang Chat ───────────────────────────────────────────────────
  window.loadChatPage = function () {
    const messagesEl = document.getElementById('chat-messages');
    if (!messagesEl) return;

    // Nếu khung chat chưa có tin nhắn nào thì hiển thị lời chào mẫu
    if (messagesEl.children.length === 0) {
      addInitialWelcomeMessage();
    }

    const inputEl = document.getElementById('chat-input-text');
    if (inputEl) {
      inputEl.focus();
    }
  };

  // ── Tin nhắn chào ban đầu ────────────────────────────────────────────────
  function addInitialWelcomeMessage() {
    const welcomeData = {
      status_icon: '👋',
      title: 'Xin chào! Tôi là Trợ lý AI của hệ thống ao nuôi cá.',
      description: 'Tôi có thể giúp bạn kiểm tra mực nước, theo dõi trạng thái hai máy bơm, phân tích biến động và hỗ trợ điều khiển thiết bị an toàn. Hãy chọn câu hỏi gợi ý bên trái hoặc gõ câu hỏi bên dưới nhé!',
      metrics: [
        { icon: '💧', label: 'Mực nước ao' },
        { icon: '🚰', label: 'Bơm IN & OUT' },
        { icon: '📈', label: 'Biến động 30p' },
        { icon: '📅', label: 'Tóm tắt hôm nay' },
      ],
      data_time: `Hệ thống sẵn sàng lúc ${getCurrentTimeStr()}`
    };
    renderBotMessage(welcomeData);
  }

  // ── Render tin nhắn User vào DOM ─────────────────────────────────────────
  function renderUserMessage(text) {
    const messagesEl = document.getElementById('chat-messages');
    if (!messagesEl) return;

    const timeStr = getCurrentTimeStr();
    const rowEl = document.createElement('div');
    rowEl.className = 'chat-msg-row-user';
    rowEl.innerHTML = `
      <div class="chat-bubble-user">
        <div class="chat-bubble-user-text">${escapeHtml(text)}</div>
        <div class="chat-bubble-user-time">${timeStr}</div>
      </div>
      <div class="chat-avatar-user" title="Bạn">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
        </svg>
      </div>
    `;

    messagesEl.appendChild(rowEl);
    scrollToBottom();
  }

  // ── Render tin nhắn Bot vào DOM ──────────────────────────────────────────
  function renderBotMessage(data) {
    const messagesEl = document.getElementById('chat-messages');
    if (!messagesEl) return;

    const rowEl = document.createElement('div');
    rowEl.className = 'chat-msg-row-bot';

    const statusIcon = data.status_icon || '🤖';
    const title = data.title || '';
    const description = (data.description || '').replace(/\n/g, '<br>');
    const dataTime = data.data_time || '';
    const metrics = data.metrics || [];

    // Tạo HTML cho metric chips
    let chipsHtml = '';
    if (metrics && metrics.length > 0) {
      chipsHtml = `<div class="chat-metric-chips">` +
        metrics.map(m => `
          <div class="chat-chip">
            ${m.icon ? `<span class="chat-chip-icon">${escapeHtml(m.icon)}</span>` : ''}
            <span>${escapeHtml(m.label)}</span>
          </div>
        `).join('') +
        `</div>`;
    }

    // Tạo HTML cho footer
    let footerHtml = '';
    if (dataTime) {
      footerHtml = `
        <div class="chat-card-bot-footer">
          <span>🕒</span>
          <span>${escapeHtml(dataTime)}</span>
        </div>
      `;
    }

    // Tạo HTML cho hộp thoại xác nhận nếu có
    let confirmBoxHtml = '';
    if (data.type === 'confirmation' && data.action_id) {
      const warningHtml = (data.warnings && data.warnings.length > 0)
        ? `<ul class="chat-confirm-warning-list">` +
          data.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('') +
          `</ul>`
        : '';

      confirmBoxHtml = `
        <div class="chat-confirm-box" id="confirm-box-${escapeHtml(data.action_id)}">
          <div style="font-weight:600;color:#92400e;font-size:13px;">⚠️ Xác nhận yêu cầu điều khiển:</div>
          ${warningHtml}
          <div class="chat-confirm-actions">
            <button class="chat-btn-confirm" onclick="chatConfirmAction('${escapeHtml(data.action_id)}')">
              ✅ Xác nhận thực hiện
            </button>
            <button class="chat-btn-cancel" onclick="chatCancelAction('${escapeHtml(data.action_id)}')">
              ❌ Hủy bỏ
            </button>
          </div>
        </div>
      `;
    }

    rowEl.innerHTML = `
      <div class="chat-avatar-bot" title="Trợ lý AI">🤖</div>
      <div class="chat-card-bot">
        <div class="chat-card-bot-title">
          <span class="chat-card-bot-title-icon">${escapeHtml(statusIcon)}</span>
          <span>${escapeHtml(title)}</span>
        </div>
        ${description ? `<div class="chat-card-bot-desc">${description}</div>` : ''}
        ${chipsHtml}
        ${confirmBoxHtml}
        ${footerHtml}
      </div>
    `;

    messagesEl.appendChild(rowEl);
    scrollToBottom();
  }

  // ── Hiển thị / Ẩn hiệu ứng đang trả lời (Typing Indicator) ──────────────
  let currentTypingEl = null;

  function showTypingIndicator() {
    removeTypingIndicator();
    const messagesEl = document.getElementById('chat-messages');
    if (!messagesEl) return;

    const rowEl = document.createElement('div');
    rowEl.className = 'chat-msg-row-bot';
    rowEl.id = 'chat-typing-row';
    rowEl.innerHTML = `
      <div class="chat-avatar-bot">🤖</div>
      <div class="chat-typing-indicator">
        <div class="chat-typing-dot"></div>
        <div class="chat-typing-dot"></div>
        <div class="chat-typing-dot"></div>
      </div>
    `;
    messagesEl.appendChild(rowEl);
    currentTypingEl = rowEl;
    scrollToBottom();
  }

  function removeTypingIndicator() {
    if (currentTypingEl && currentTypingEl.parentNode) {
      currentTypingEl.parentNode.removeChild(currentTypingEl);
    }
    currentTypingEl = null;
    const old = document.getElementById('chat-typing-row');
    if (old && old.parentNode) old.parentNode.removeChild(old);
  }

  function scrollToBottom() {
    const messagesEl = document.getElementById('chat-messages');
    if (messagesEl) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  // ── Gửi tin nhắn tới Backend API ──────────────────────────────────────────
  window.sendChatMessage = async function (presetText) {
    if (isSending) return;

    const inputEl = document.getElementById('chat-input-text');
    const text = presetText ? presetText.trim() : (inputEl ? inputEl.value.trim() : '');

    if (!text) return;

    if (inputEl && !presetText) {
      inputEl.value = '';
    }

    // Hiển thị câu hỏi của User
    renderUserMessage(text);
    isSending = true;
    showTypingIndicator();

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });

      const res = await resp.json();
      removeTypingIndicator();

      if (res && res.data) {
        renderBotMessage(res.data);
      } else {
        renderBotMessage({
          status_icon: '❌',
          title: 'Không thể xử lý yêu cầu',
          description: res.error || 'Đã xảy ra lỗi không xác định từ máy chủ.',
          data_time: getCurrentTimeStr()
        });
      }
    } catch (err) {
      removeTypingIndicator();
      renderBotMessage({
        status_icon: '🔌',
        title: 'Lỗi kết nối máy chủ',
        description: 'Không thể kết nối đến Backend Flask. Vui lòng kiểm tra lại dịch vụ!',
        data_time: getCurrentTimeStr()
      });
    } finally {
      isSending = false;
      if (inputEl) inputEl.focus();
    }
  };

  // ── Gửi câu hỏi gợi ý ────────────────────────────────────────────────────
  window.sendSuggestion = function (questionText) {
    sendChatMessage(questionText);
  };

  // ── Xác nhận lệnh điều khiển qua nút bấm ───────────────────────────────────
  window.chatConfirmAction = async function (actionId) {
    const box = document.getElementById(`confirm-box-${actionId}`);
    if (box) {
      box.innerHTML = `<div style="color:#2563eb;font-size:13px;font-weight:500;">⏳ Đang thực thi lệnh xuống ESP32...</div>`;
    }

    try {
      const resp = await fetch('/api/chat/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_id: actionId })
      });
      const res = await resp.json();
      if (res && res.data) {
        renderBotMessage(res.data);
      }
    } catch (err) {
      renderBotMessage({
        status_icon: '❌',
        title: 'Lỗi xác nhận lệnh',
        description: 'Không thể gửi lệnh xác nhận đến máy chủ: ' + err.message,
        data_time: getCurrentTimeStr()
      });
    }
  };

  // ── Hủy bỏ lệnh điều khiển qua nút bấm ────────────────────────────────────
  window.chatCancelAction = async function (actionId) {
    const box = document.getElementById(`confirm-box-${actionId}`);
    if (box) {
      box.innerHTML = `<div style="color:#64748b;font-size:13px;">🚫 Yêu cầu đã hủy bỏ.</div>`;
    }

    try {
      const resp = await fetch('/api/chat/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_id: actionId })
      });
      const res = await resp.json();
      if (res && res.data) {
        renderBotMessage(res.data);
      }
    } catch (err) {
      renderBotMessage({
        status_icon: '❌',
        title: 'Lỗi hủy lệnh',
        description: 'Không thể gửi yêu cầu hủy lệnh: ' + err.message,
        data_time: getCurrentTimeStr()
      });
    }
  };

  // ── Xóa hội thoại ────────────────────────────────────────────────────────
  window.clearChatHistory = function () {
    const messagesEl = document.getElementById('chat-messages');
    if (!messagesEl) return;
    messagesEl.innerHTML = '';
    addInitialWelcomeMessage();
  };

  // ── Ẩn / Hiện danh sách câu hỏi gợi ý ────────────────────────────────────
  window.toggleSuggestions = function () {
    const listEl = document.getElementById('chat-suggestions-list');
    const toggleBtn = document.getElementById('chat-suggestions-toggle-btn');
    if (!listEl) return;

    if (listEl.classList.contains('collapsed')) {
      listEl.classList.remove('collapsed');
      if (toggleBtn) toggleBtn.textContent = '▲';
    } else {
      listEl.classList.add('collapsed');
      if (toggleBtn) toggleBtn.textContent = '▼';
    }
  };

  // ── Khởi tạo sự kiện bàn phím khi DOM sẵn sàng ───────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    const inputEl = document.getElementById('chat-input-text');
    if (inputEl) {
      inputEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendChatMessage();
        }
      });
    }
  });

})();

