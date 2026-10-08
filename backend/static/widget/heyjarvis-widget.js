/**
 * HeyJarvis Chat Widget
 * A framework-independent chat widget for embedding on any website.
 *
 * Usage:
 *   <script src="https://your-domain.com/widget/heyjarvis-widget.js"
 *           data-practice="raleigh-comprehensive-cosmetic-dentistry"
 *           data-theme="light">
 *   </script>
 */

(function (global) {
  'use strict';

  // ─── Configuration ────────────────────────────────────────────────
  const CONFIG = {
    WIDGET_VERSION: '1.0.0',
    DEFAULT_API_URL: '', // Set via data-api-url attribute
    DEFAULT_THEME: 'light',
    DEFAULT_TITLE: 'HeyJarvis',
    DEFAULT_SUBTITLE: 'How can we help you today?',
    COLORS: {
      light: {
        primary: '#2563eb',
        primaryHover: '#1d4ed8',
        background: '#ffffff',
        text: '#1e293b',
        textSecondary: '#64748b',
        border: '#e2e8f0',
        bubblePatient: '#f1f5f9',
        bubbleConcierge: '#2563eb',
        bubbleConciergeText: '#ffffff',
        shadow: '0 4px 24px rgba(0, 0, 0, 0.12)',
      },
      dark: {
        primary: '#3b82f6',
        primaryHover: '#2563eb',
        background: '#1e293b',
        text: '#f1f5f9',
        textSecondary: '#94a3b8',
        border: '#334155',
        bubblePatient: '#334155',
        bubbleConcierge: '#3b82f6',
        bubbleConciergeText: '#ffffff',
        shadow: '0 4px 24px rgba(0, 0, 0, 0.3)',
      },
    },
  };

  // ─── State ────────────────────────────────────────────────────────
  let state = {
    practiceSlug: '',
    apiUrl: '',
    theme: 'light',
    title: CONFIG.DEFAULT_TITLE,
    subtitle: CONFIG.DEFAULT_SUBTITLE,
    sessionId: null,
    conversationId: null,
    messages: [],
    isOpen: false,
    isTyping: false,
    isSubmitting: false,
    error: null,
    initialized: false,
  };

  // ─── DOM Elements Cache ───────────────────────────────────────────
  let elements = {};

  // ─── Utility Functions ────────────────────────────────────────────
  function generateId() {
    return 'hj_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
  }

  function generateSessionId() {
    const stored = localStorage.getItem('heyjarvis_session_id');
    if (stored) return stored;
    const newId = generateId();
    localStorage.setItem('heyjarvis_session_id', newId);
    return newId;
  }

  function getColors() {
    return CONFIG.COLORS[state.theme] || CONFIG.COLORS.light;
  }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  // ─── CSS Injection ────────────────────────────────────────────────
  function injectStyles() {
    const colors = getColors();
    const style = document.createElement('style');
    style.id = 'heyjarvis-widget-styles';
    style.textContent = `
      /* HeyJarvis Widget v${CONFIG.WIDGET_VERSION} */

      #heyjarvis-widget-container * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
          'Helvetica Neue', Arial, sans-serif;
      }

      /* Launcher Button */
      #hj-launcher {
        position: fixed;
        bottom: 24px;
        right: 24px;
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: ${colors.primary};
        border: none;
        cursor: pointer;
        box-shadow: ${colors.shadow};
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 99998;
        transition: transform 0.2s ease, background 0.2s ease;
      }

      #hj-launcher:hover {
        transform: scale(1.05);
        background: ${colors.primaryHover};
      }

      #hj-launcher svg {
        width: 28px;
        height: 28px;
        fill: #ffffff;
        transition: transform 0.2s ease;
      }

      #hj-launcher.hj-open svg {
        transform: rotate(90deg);
      }

      /* Badge */
      #hj-badge {
        position: absolute;
        top: -2px;
        right: -2px;
        width: 18px;
        height: 18px;
        background: #ef4444;
        border-radius: 50%;
        border: 2px solid #ffffff;
        display: none;
      }

      #hj-badge.hj-visible {
        display: block;
      }

      /* Chat Window */
      #hj-chat-window {
        position: fixed;
        bottom: 96px;
        right: 24px;
        width: 380px;
        height: 520px;
        max-height: calc(100vh - 120px);
        background: ${colors.background};
        border-radius: 16px;
        box-shadow: ${colors.shadow};
        z-index: 99999;
        display: none;
        flex-direction: column;
        overflow: hidden;
        border: 1px solid ${colors.border};
      }

      #hj-chat-window.hj-open {
        display: flex;
      }

      /* Header */
      #hj-header {
        background: ${colors.primary};
        color: #ffffff;
        padding: 16px 20px;
        display: flex;
        align-items: center;
        gap: 12px;
        flex-shrink: 0;
      }

      #hj-header-avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.2);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }

      #hj-header-avatar svg {
        width: 22px;
        height: 22px;
        fill: #ffffff;
      }

      #hj-header-info h3 {
        font-size: 15px;
        font-weight: 600;
        line-height: 1.3;
      }

      #hj-header-info p {
        font-size: 12px;
        opacity: 0.85;
        line-height: 1.3;
      }

      #hj-close-btn {
        margin-left: auto;
        background: none;
        border: none;
        color: #ffffff;
        cursor: pointer;
        padding: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0.8;
        transition: opacity 0.15s;
      }

      #hj-close-btn:hover {
        opacity: 1;
      }

      #hj-close-btn svg {
        width: 18px;
        height: 18px;
        fill: currentColor;
      }

      /* Messages Area */
      #hj-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        scroll-behavior: smooth;
      }

      #hj-messages::-webkit-scrollbar {
        width: 6px;
      }

      #hj-messages::-webkit-scrollbar-thumb {
        background: ${colors.border};
        border-radius: 3px;
      }

      /* Message Bubbles */
      .hj-message {
        display: flex;
        flex-direction: column;
        max-width: 85%;
        animation: hj-fadeIn 0.2s ease;
      }

      @keyframes hj-fadeIn {
        from { opacity: 0; transform: translateY(4px); }
        to { opacity: 1; transform: translateY(0); }
      }

      .hj-message-patient {
        align-self: flex-end;
        align-items: flex-end;
      }

      .hj-message-concierge {
        align-self: flex-start;
        align-items: flex-start;
      }

      .hj-message-sender {
        font-size: 11px;
        font-weight: 600;
        color: ${colors.textSecondary};
        margin-bottom: 4px;
        padding: 0 4px;
      }

      .hj-message-bubble {
        padding: 10px 14px;
        border-radius: 16px;
        font-size: 14px;
        line-height: 1.5;
        word-wrap: break-word;
        white-space: pre-wrap;
      }

      .hj-message-patient .hj-message-bubble {
        background: ${colors.bubblePatient};
        color: ${colors.text};
        border-bottom-right-radius: 4px;
      }

      .hj-message-concierge .hj-message-bubble {
        background: ${colors.bubbleConcierge};
        color: ${colors.bubbleConciergeText};
        border-bottom-left-radius: 4px;
      }

      .hj-message-time {
        font-size: 10px;
        color: ${colors.textSecondary};
        margin-top: 4px;
        padding: 0 4px;
      }

      /* Typing Indicator */
      .hj-typing-indicator {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 10px 14px;
        background: ${colors.bubbleConcierge};
        border-radius: 16px;
        border-bottom-left-radius: 4px;
        width: fit-content;
      }

      .hj-typing-indicator span {
        width: 8px;
        height: 8px;
        background: rgba(255, 255, 255, 0.5);
        border-radius: 50%;
        animation: hj-bounce 1.4s infinite ease-in-out both;
      }

      .hj-typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
      .hj-typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
      .hj-typing-indicator span:nth-child(3) { animation-delay: 0s; }

      @keyframes hj-bounce {
        0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
        40% { transform: scale(1); opacity: 1; }
      }

      /* Quick Replies */
      .hj-quick-replies {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        padding: 0 16px 8px;
      }

      .hj-quick-reply {
        background: ${colors.primary};
        color: #ffffff;
        border: none;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 13px;
        cursor: pointer;
        transition: background 0.15s;
      }

      .hj-quick-reply:hover {
        background: ${colors.primaryHover};
      }

      /* Input Area */
      #hj-input-area {
        padding: 12px 16px;
        border-top: 1px solid ${colors.border};
        display: flex;
        gap: 8px;
        align-items: flex-end;
        flex-shrink: 0;
      }

      #hj-patient-name {
        display: none;
      }

      #hj-patient-name.hj-visible {
        display: block;
      }

      #hj-patient-name input {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid ${colors.border};
        border-radius: 8px;
        font-size: 13px;
        background: ${colors.background};
        color: ${colors.text};
        margin-bottom: 8px;
      }

      #hj-patient-name input:focus {
        outline: none;
        border-color: ${colors.primary};
      }

      #hj-message-input {
        flex: 1;
        padding: 10px 14px;
        border: 1px solid ${colors.border};
        border-radius: 20px;
        font-size: 14px;
        background: ${colors.background};
        color: ${colors.text};
        resize: none;
        max-height: 100px;
        min-height: 38px;
        line-height: 1.4;
      }

      #hj-message-input:focus {
        outline: none;
        border-color: ${colors.primary};
      }

      #hj-message-input::placeholder {
        color: ${colors.textSecondary};
      }

      #hj-send-btn {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: ${colors.primary};
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        transition: background 0.15s, opacity 0.15s;
      }

      #hj-send-btn:hover:not(:disabled) {
        background: ${colors.primaryHover};
      }

      #hj-send-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      #hj-send-btn svg {
        width: 18px;
        height: 18px;
        fill: #ffffff;
      }

      /* Footer */
      #hj-footer {
        text-align: center;
        padding: 6px;
        font-size: 10px;
        color: ${colors.textSecondary};
        border-top: 1px solid ${colors.border};
        flex-shrink: 0;
      }

      #hj-footer a {
        color: ${colors.primary};
        text-decoration: none;
      }

      /* Error State */
      .hj-error {
        background: #fef2f2;
        border: 1px solid #fecaca;
        color: #dc2626;
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 13px;
        margin: 8px 16px;
      }

      /* Disclaimer */
      .hj-disclaimer {
        background: ${colors.bubblePatient};
        border-radius: 12px;
        padding: 10px 14px;
        font-size: 11px;
        color: ${colors.textSecondary};
        text-align: center;
        margin: 8px 16px;
        line-height: 1.4;
      }

      /* Responsive */
      @media (max-width: 480px) {
        #hj-chat-window {
          width: 100vw;
          height: 100vh;
          max-height: 100vh;
          bottom: 0;
          right: 0;
          border-radius: 0;
        }

        #hj-launcher {
          bottom: 16px;
          right: 16px;
          width: 52px;
          height: 52px;
        }
      }

      /* Power Input (for date/time selection) */
      .hj-power-inputs {
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 8px 16px;
      }

      .hj-power-inputs label {
        font-size: 12px;
        color: ${colors.textSecondary};
        font-weight: 500;
      }

      .hj-power-inputs input[type="date"],
      .hj-power-inputs input[type="time"],
      .hj-power-inputs input[type="text"],
      .hj-power-inputs select {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid ${colors.border};
        border-radius: 8px;
        font-size: 14px;
        background: ${colors.background};
        color: ${colors.text};
      }

      .hj-power-inputs input:focus,
      .hj-power-inputs select:focus {
        outline: none;
        border-color: ${colors.primary};
      }

      .hj-submit-actions {
        display: flex;
        gap: 8px;
        padding: 8px 16px 12px;
      }

      .hj-submit-actions button {
        flex: 1;
        padding: 8px 16px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        border: none;
        transition: background 0.15s;
      }

      .hj-btn-primary {
        background: ${colors.primary};
        color: #ffffff;
      }

      .hj-btn-primary:hover {
        background: ${colors.primaryHover};
      }

      .hj-btn-secondary {
        background: ${colors.bubblePatient};
        color: ${colors.text};
      }

      .hj-btn-secondary:hover {
        background: ${colors.border};
      }
    `;

    if (!document.getElementById('heyjarvis-widget-styles')) {
      document.head.appendChild(style);
    }
  }

  // ─── DOM Creation ─────────────────────────────────────────────────
  function createWidgetDOM() {
    // Launcher
    const launcher = document.createElement('button');
    launcher.id = 'hj-launcher';
    launcher.setAttribute('aria-label', 'Open chat');
    launcher.innerHTML = `
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
        <path d="M7 9h10v2H7zm0-3h10v2H7z" style="display:none" class="hj-close-icon"/>
      </svg>
      <span id="hj-badge"></span>
    `;
    document.body.appendChild(launcher);

    // Chat Window
    const chatWindow = document.createElement('div');
    chatWindow.id = 'hj-chat-window';
    chatWindow.innerHTML = `
      <div id="hj-header">
        <div id="hj-header-avatar">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
          </svg>
        </div>
        <div id="hj-header-info">
          <h3>${escapeHtml(state.title)}</h3>
          <p>${escapeHtml(state.subtitle)}</p>
        </div>
        <button id="hj-close-btn" aria-label="Close chat">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </button>
      </div>
      <div id="hj-messages"></div>
      <div id="hj-quick-replies"></div>
      <div id="hj-input-area">
        <div id="hj-patient-name">
          <input type="text" id="hj-name-input" placeholder="Your name" />
        </div>
        <textarea id="hj-message-input" rows="1" placeholder="Type a message..." aria-label="Message input"></textarea>
        <button id="hj-send-btn" aria-label="Send message">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
          </svg>
        </button>
      </div>
      <div id="hj-footer">
        Powered by <a href="https://heyjarvis.ai" target="_blank" rel="noopener">HeyJarvis</a>
      </div>
    `;
    document.body.appendChild(chatWindow);

    // Cache elements
    elements = {
      launcher,
      badge: document.getElementById('hj-badge'),
      chatWindow,
      messages: document.getElementById('hj-messages'),
      quickReplies: document.getElementById('hj-quick-replies'),
      messageInput: document.getElementById('hj-message-input'),
      sendBtn: document.getElementById('hj-send-btn'),
      closeBtn: document.getElementById('hj-close-btn'),
      patientName: document.getElementById('hj-patient-name'),
      nameInput: document.getElementById('hj-name-input'),
    };
  }

  // ─── UI Helpers ───────────────────────────────────────────────────
  function toggleChat(open) {
    state.isOpen = open !== undefined ? open : !state.isOpen;
    elements.chatWindow.classList.toggle('hj-open', state.isOpen);
    elements.launcher.classList.toggle('hj-open', state.isOpen);
    if (state.isOpen) {
      elements.messageInput.focus();
      scrollToBottom();
    }
  }

  function scrollToBottom() {
    if (elements.messages) {
      elements.messages.scrollTop = elements.messages.scrollHeight;
    }
  }

  function showTyping() {
    state.isTyping = true;
    const indicator = document.createElement('div');
    indicator.className = 'hj-message hj-message-concierge';
    indicator.id = 'hj-typing';
    indicator.innerHTML = `
      <div class="hj-typing-indicator">
        <span></span><span></span><span></span>
      </div>
    `;
    elements.messages.appendChild(indicator);
    scrollToBottom();
  }

  function hideTyping() {
    state.isTyping = false;
    const typing = document.getElementById('hj-typing');
    if (typing) typing.remove();
  }

  function addMessage(role, text, meta = {}) {
    const colors = getColors();
    const isPatient = role === 'patient';

    const wrapper = document.createElement('div');
    wrapper.className = `hj-message hj-message-${role}`;

    let senderLabel = '';
    if (isPatient) {
      senderLabel = `<div class="hj-message-sender">You</div>`;
    }

    let extraContent = '';
    if (meta.powerInputs) {
      extraContent = `
        <div class="hj-power-inputs">
          <label>Preferred Date</label>
          <input type="date" id="hj-power-date" value="${escapeHtml(meta.preferredDate || '')}" />
          <label>Preferred Time</label>
          <input type="time" id="hj-power-time" value="${escapeHtml(meta.preferredTime || '')}" />
          <div class="hj-submit-actions">
            <button class="hj-btn-secondary" id="hj-power-cancel">Cancel</button>
            <button class="hj-btn-primary" id="hj-power-submit">Request Appointment</button>
          </div>
        </div>
      `;
    }

    wrapper.innerHTML = `
      ${senderLabel}
      <div class="hj-message-bubble">${escapeHtml(text)}</div>
      ${extraContent}
      <div class="hj-message-time">${formatTime(meta.timestamp || Date.now())}</div>
    `;

    elements.messages.appendChild(wrapper);

    // Wire up power inputs
    if (meta.powerInputs) {
      document.getElementById('hj-power-cancel')?.addEventListener('click', () => {
        wrapper.remove();
        removeQuickReplies();
      });
      document.getElementById('hj-power-submit')?.addEventListener('click', () => {
        const date = document.getElementById('hj-power-date').value;
        const time = document.getElementById('hj-power-time').value;
        submitAppointmentRequest(date, time);
      });
    }

    scrollToBottom();
  }

  function showQuickReplies(replies) {
    elements.quickReplies.innerHTML = '';
    replies.forEach((reply) => {
      const btn = document.createElement('button');
      btn.className = 'hj-quick-reply';
      btn.textContent = reply.label || reply;
      btn.addEventListener('click', () => {
        removeQuickReplies();
        sendMessage(reply.label || reply);
      });
      elements.quickReplies.appendChild(btn);
    });
  }

  function removeQuickReplies() {
    elements.quickReplies.innerHTML = '';
  }

  function showError(message) {
    state.error = message;
    const existing = elements.messages.querySelector('.hj-error');
    if (existing) existing.remove();

    const errorEl = document.createElement('div');
    errorEl.className = 'hj-error';
    errorEl.textContent = message;
    elements.messages.appendChild(errorEl);
    scrollToBottom();

    setTimeout(() => errorEl.remove(), 5000);
  }

  // ─── API Communication ────────────────────────────────────────────
  async function apiRequest(endpoint, data) {
    const url = state.apiUrl
      ? `${state.apiUrl}${endpoint}`
      : `https://api.heyjarvis.ai${endpoint}`;

    const headers = {
      'Content-Type': 'application/json',
      'X-Client-Key': state.clientKey || '',
      'X-Practice-Slug': state.practiceSlug || '',
      'X-Session-ID': state.sessionId,
      'X-Widget-Version': CONFIG.WIDGET_VERSION,
    };
    if (state.clientKey && !data.client_key) {
      data.client_key = state.clientKey;
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(data),
      credentials: 'omit',
    });


    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || errorData.error || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async function initializeConversation() {
    try {
      const result = await apiRequest('/api/v1/widget/conversation/', {
        session_id: state.sessionId,
        practice_slug: state.practiceSlug,
      });

      if (result.conversation_id) {
        state.conversationId = result.conversation_id;
      }

      const welcomeMsg = result.welcome_message || result.message || result.response;
      if (welcomeMsg) {
        addMessage('concierge', welcomeMsg, { timestamp: Date.now() });
        state.messages.push({
          role: 'concierge',
          content: welcomeMsg,
          timestamp: Date.now(),
        });
      }

      if (result.quick_replies && result.quick_replies.length > 0) {
        showQuickReplies(result.quick_replies);
      }

      if (result.ask_name) {
        elements.patientName.classList.add('hj-visible');
      }

      state.initialized = true;
    } catch (error) {
      console.error('HeyJarvis: Failed to initialize conversation:', error);
      addMessage(
        'concierge',
        "Hi! I'm the HeyJarvis AI concierge. I can help you request an appointment. "
        + 'Please tell me a bit about what you need, and our team will get back to you shortly.',
        { timestamp: Date.now() }
      );
      state.initialized = true;
    }
  }

  async function sendMessage(text) {
    if (!text.trim() || state.isSubmitting) return;

    state.isSubmitting = true;
    elements.sendBtn.disabled = true;
    removeQuickReplies();
    hideTyping();

    // Add patient message
    addMessage('patient', text, { timestamp: Date.now() });
    state.messages.push({
      role: 'patient',
      content: text,
      timestamp: Date.now(),
    });

    elements.messageInput.value = '';
    autoResizeInput();

    showTyping();

    try {
      const result = await apiRequest('/api/v1/widget/message/', {
        session_id: state.sessionId,
        conversation_id: state.conversationId || '',
        practice_slug: state.practiceSlug,
        message: text,
        patient_name: elements.nameInput?.value || '',
      });

      if (result.conversation_id) {
        state.conversationId = result.conversation_id;
      }

      hideTyping();

      const reply = result.response || result.message;
      if (reply) {
        addMessage('concierge', reply, {
          timestamp: Date.now(),
          powerInputs: result.power_inputs,
          preferredDate: result.preferred_date,
          preferredTime: result.preferred_time,
        });
        state.messages.push({
          role: 'concierge',
          content: reply,
          timestamp: Date.now(),
          powerInputs: result.power_inputs,
        });
      }

      if (result.quick_replies && result.quick_replies.length > 0) {
        showQuickReplies(result.quick_replies);
      }

      if (result.conversation_complete) {
        elements.sendBtn.disabled = true;
        elements.messageInput.disabled = true;
        elements.messageInput.placeholder = 'Conversation submitted. We\'ll be in touch!';
      }
    } catch (error) {
      hideTyping();
      console.error('HeyJarvis: Message send failed:', error);
      showError('Sorry, something went wrong. Please try again or contact us directly.');
    } finally {
      state.isSubmitting = false;
      elements.sendBtn.disabled = false;
      elements.messageInput.focus();
    }
  }

  async function submitAppointmentRequest(date, time) {
    const name = elements.nameInput?.value || 'Guest';
    addMessage(
      'patient',
      `Appointment request: ${name} — ${date ? date + ' at ' + time : 'flexible timing'}`,
      { timestamp: Date.now() }
    );

    showTyping();

    try {
      const result = await apiRequest('/api/v1/widget/submit/', {
        session_id: state.sessionId,
        practice_slug: state.practiceSlug,
        preferred_date: date,
        preferred_time: time,
        patient_name: name,
      });

      hideTyping();

      if (result.response) {
        addMessage('concierge', result.response, { timestamp: Date.now() });
      }

      elements.sendBtn.disabled = true;
      elements.messageInput.disabled = true;
      elements.messageInput.placeholder = 'Request submitted. We\'ll be in touch!';
      removeQuickReplies();
    } catch (error) {
      hideTyping();
      console.error('HeyJarvis: Submit failed:', error);
      showError('Sorry, something went wrong. Please try again or contact us directly.');
    }
  }

  // ─── Event Handlers ───────────────────────────────────────────────
  function autoResizeInput() {
    if (!elements.messageInput) return;
    elements.messageInput.style.height = 'auto';
    elements.messageInput.style.height = Math.min(elements.messageInput.scrollHeight, 100) + 'px';
  }

  function setupEventListeners() {
    // Launcher
    elements.launcher.addEventListener('click', () => toggleChat());

    // Close
    elements.closeBtn.addEventListener('click', () => toggleChat(false));

    // Send button
    elements.sendBtn.addEventListener('click', () => {
      sendMessage(elements.messageInput.value);
    });

    // Input
    elements.messageInput.addEventListener('input', autoResizeInput);
    elements.messageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(elements.messageInput.value);
      }
    });

    // Close on escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && state.isOpen) {
        toggleChat(false);
      }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (
        state.isOpen &&
        !elements.chatWindow.contains(e.target) &&
        !elements.launcher.contains(e.target)
      ) {
        toggleChat(false);
      }
    });
  }

  // ─── Initialization ───────────────────────────────────────────────
  function init() {
    if (document.getElementById('hj-chat-window')) {
      console.warn('HeyJarvis: Widget already initialized');
      return;
    }

    // Read config from script attributes
    const scriptTag = document.querySelector('script[data-heyjarvis-client], script[data-client-key], script[data-practice]');
    if (scriptTag) {
      state.clientKey = scriptTag.getAttribute('data-heyjarvis-client') || scriptTag.getAttribute('data-client-key') || '';
      state.practiceSlug = scriptTag.getAttribute('data-practice') || '';
      state.apiUrl = scriptTag.getAttribute('data-api-url') || '';
      if (!state.apiUrl && scriptTag.src) {
        try {
          const u = new URL(scriptTag.src, window.location.href);
          state.apiUrl = u.origin;
        } catch (e) {}
      }
      // If loaded from Vite dev port 3000 or file:// protocol, route API requests to backend port 8000
      if (!state.apiUrl || window.location.protocol === 'file:' || (state.apiUrl && state.apiUrl.includes(':3000'))) {
        if (!state.apiUrl || state.apiUrl.includes(':3000')) {
          if (state.apiUrl && state.apiUrl.includes(':3000')) {
            state.apiUrl = state.apiUrl.replace(':3000', ':8000');
          } else {
            state.apiUrl = 'http://localhost:8000';
          }
        } else if (window.location.protocol === 'file:') {
          state.apiUrl = 'http://localhost:8000';
        }
      }
      state.theme = scriptTag.getAttribute('data-theme') || CONFIG.DEFAULT_THEME;
      state.title = scriptTag.getAttribute('data-title') || CONFIG.DEFAULT_TITLE;
      state.subtitle = scriptTag.getAttribute('data-subtitle') || CONFIG.DEFAULT_SUBTITLE;
    }

    if (!state.clientKey && !state.practiceSlug) {
      console.warn('HeyJarvis: Missing data-heyjarvis-client or data-practice attribute');
    }


    state.sessionId = generateSessionId();

    injectStyles();
    createWidgetDOM();
    setupEventListeners();
    initializeConversation();

    // Expose API
    global.HeyJarvis = {
      open: () => toggleChat(true),
      close: () => toggleChat(false),
      toggle: () => toggleChat(),
      getState: () => ({ ...state }),
      destroy: destroy,
      version: CONFIG.WIDGET_VERSION,
    };
  }

  function destroy() {
    elements.launcher?.remove();
    elements.chatWindow?.remove();
    document.getElementById('heyjarvis-widget-styles')?.remove();
    delete global.HeyJarvis;
  }

  // ─── Auto-init ────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
