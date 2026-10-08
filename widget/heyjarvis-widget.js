/**
 * HeyJarvis Dental AI Concierge Chat Widget
 * Framework-independent standalone widget for dental clinic websites.
 * Features:
 *   - High-converting modern dental clinic aesthetic
 *   - Automatic practice branding & doctor presence
 *   - Natural conversational appointment triage & lead capture
 *   - Interactive quick-reply pills & power scheduling inputs
 *   - Celebration cards upon appointment submission
 *   - Responsive mobile & desktop presentation
 */

(function (global) {
  'use strict';

  // ─── Configuration ────────────────────────────────────────────────
  const CONFIG = {
    WIDGET_VERSION: '2.0.0',
    DEFAULT_API_URL: '',
    DEFAULT_THEME: 'light',
    DEFAULT_TITLE: 'Raleigh Comprehensive Dentistry',
    DEFAULT_SUBTITLE: 'Dr. Neal Patel, DDS • Instant AI Concierge',
    COLORS: {
      light: {
        primary: '#0d9488',
        primaryHover: '#0f766e',
        headerBg: 'linear-gradient(135deg, #0f172a 0%, #134e4a 100%)',
        headerText: '#ffffff',
        background: '#ffffff',
        messagesBg: '#f8fafc',
        text: '#0f172a',
        textSecondary: '#64748b',
        border: '#e2e8f0',
        bubblePatient: 'linear-gradient(135deg, #0d9488 0%, #0f766e 100%)',
        bubblePatientText: '#ffffff',
        bubbleConcierge: '#ffffff',
        bubbleConciergeText: '#0f172a',
        bubbleConciergeBorder: '#e2e8f0',
        inputBg: '#f8fafc',
        inputBorder: '#e2e8f0',
        shadow: '0 20px 45px -10px rgba(15, 23, 42, 0.22), 0 0 0 1px rgba(15, 23, 42, 0.08)',
      },
      dark: {
        primary: '#14b8a6',
        primaryHover: '#0d9488',
        headerBg: 'linear-gradient(135deg, #020617 0%, #042f2e 100%)',
        headerText: '#ffffff',
        background: '#0f172a',
        messagesBg: '#090d16',
        text: '#f8fafc',
        textSecondary: '#94a3b8',
        border: '#1e293b',
        bubblePatient: 'linear-gradient(135deg, #0d9488 0%, #0f766e 100%)',
        bubblePatientText: '#ffffff',
        bubbleConcierge: '#1e293b',
        bubbleConciergeText: '#f8fafc',
        bubbleConciergeBorder: '#334155',
        inputBg: '#1e293b',
        inputBorder: '#334155',
        shadow: '0 20px 45px -10px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.08)',
      },
    },
  };

  // ─── State ────────────────────────────────────────────────────────
  let state = {
    clientKey: '',
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
    isComplete: false,
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

  function formatMessageText(text) {
    if (!text) return '';
    let safe = escapeHtml(text);
    // Bold **text**
    safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Bullets • or *
    const lines = safe.split('\n');
    let formatted = [];
    let inList = false;

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('• ') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        if (!inList) {
          formatted.push('<ul class="hj-message-list">');
          inList = true;
        }
        formatted.push(`<li>${trimmed.substring(2)}</li>`);
      } else {
        if (inList) {
          formatted.push('</ul>');
          inList = false;
        }
        if (trimmed) {
          formatted.push(`<p class="hj-message-p">${trimmed}</p>`);
        }
      }
    });

    if (inList) {
      formatted.push('</ul>');
    }

    return formatted.join('') || safe;
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
      /* HeyJarvis Dental Concierge Widget v${CONFIG.WIDGET_VERSION} */

      #heyjarvis-widget-container,
      #heyjarvis-widget-container * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
      }

      /* Floating Launcher Button */
      #hj-launcher {
        position: fixed;
        bottom: 24px;
        right: 24px;
        width: 62px;
        height: 62px;
        border-radius: 50%;
        background: ${colors.primary};
        background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
        border: none;
        cursor: pointer;
        box-shadow: 0 8px 24px rgba(13, 148, 136, 0.4), 0 2px 6px rgba(0, 0, 0, 0.1);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 999998;
        transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
      }

      #hj-launcher:hover {
        transform: scale(1.08);
        box-shadow: 0 12px 30px rgba(13, 148, 136, 0.5), 0 4px 10px rgba(0, 0, 0, 0.15);
      }

      #hj-launcher svg {
        width: 30px;
        height: 30px;
        fill: #ffffff;
        transition: transform 0.25s ease;
      }

      #hj-launcher.hj-open svg.hj-chat-icon {
        display: none;
      }

      #hj-launcher.hj-open svg.hj-close-icon {
        display: block !important;
        transform: rotate(90deg);
      }

      #hj-badge {
        position: absolute;
        top: 2px;
        right: 2px;
        width: 14px;
        height: 14px;
        background: #10b981;
        border-radius: 50%;
        border: 2.5px solid #ffffff;
        box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
        animation: hj-pulse-ring 2s infinite;
      }

      @keyframes hj-pulse-ring {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
      }

      /* Chat Window */
      #hj-chat-window {
        position: fixed;
        bottom: 98px;
        right: 24px;
        width: 390px;
        height: 550px;
        max-height: calc(100vh - 120px);
        background: ${colors.background};
        border-radius: 20px;
        box-shadow: ${colors.shadow};
        z-index: 999999;
        display: none;
        flex-direction: column;
        overflow: hidden;
        border: 1px solid ${colors.border};
        transform: translateY(12px) scale(0.98);
        opacity: 0;
        transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.22s ease;
      }

      #hj-chat-window.hj-open {
        display: flex;
        transform: translateY(0) scale(1);
        opacity: 1;
      }

      /* Header */
      #hj-header {
        background: ${colors.headerBg};
        color: ${colors.headerText};
        padding: 16px 18px;
        display: flex;
        align-items: center;
        gap: 12px;
        flex-shrink: 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      }

      #hj-header-avatar {
        width: 42px;
        height: 42px;
        border-radius: 12px;
        background: linear-gradient(135deg, rgba(20, 184, 166, 0.25) 0%, rgba(13, 148, 136, 0.4) 100%);
        border: 1.5px solid rgba(20, 184, 166, 0.4);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
      }

      #hj-header-avatar svg {
        width: 22px;
        height: 22px;
        fill: #2dd4bf;
      }

      #hj-header-info {
        flex: 1;
        min-width: 0;
      }

      #hj-header-info h3 {
        font-size: 14.5px;
        font-weight: 700;
        letter-spacing: -0.2px;
        color: #ffffff;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        line-height: 1.3;
      }

      .hj-header-status {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 11.5px;
        color: #94a3b8;
        margin-top: 2px;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .hj-status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #10b981;
        box-shadow: 0 0 6px #10b981;
        flex-shrink: 0;
      }

      #hj-close-btn {
        background: rgba(255, 255, 255, 0.1);
        border: none;
        color: #cbd5e1;
        cursor: pointer;
        width: 28px;
        height: 28px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.15s, color 0.15s;
        flex-shrink: 0;
      }

      #hj-close-btn:hover {
        background: rgba(255, 255, 255, 0.2);
        color: #ffffff;
      }

      #hj-close-btn svg {
        width: 14px;
        height: 14px;
        fill: currentColor;
      }

      /* Messages Area */
      #hj-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px 14px;
        background: ${colors.messagesBg};
        display: flex;
        flex-direction: column;
        gap: 12px;
        scroll-behavior: smooth;
      }

      #hj-messages::-webkit-scrollbar {
        width: 5px;
      }

      #hj-messages::-webkit-scrollbar-thumb {
        background: ${colors.border};
        border-radius: 4px;
      }

      /* Message Bubbles */
      .hj-message {
        display: flex;
        flex-direction: column;
        max-width: 88%;
        animation: hj-fadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      }

      @keyframes hj-fadeIn {
        from { opacity: 0; transform: translateY(6px); }
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
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: ${colors.textSecondary};
        margin-bottom: 3px;
        padding: 0 4px;
      }

      .hj-message-bubble {
        padding: 11px 15px;
        font-size: 13.5px;
        line-height: 1.5;
        word-wrap: break-word;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
      }

      .hj-message-patient .hj-message-bubble {
        background: ${colors.bubblePatient};
        color: ${colors.bubblePatientText};
        border-radius: 18px;
        border-bottom-right-radius: 4px;
      }

      .hj-message-concierge .hj-message-bubble {
        background: ${colors.bubbleConcierge};
        color: ${colors.bubbleConciergeText};
        border: 1px solid ${colors.bubbleConciergeBorder};
        border-radius: 18px;
        border-bottom-left-radius: 4px;
      }

      .hj-message-bubble p.hj-message-p {
        margin-bottom: 6px;
      }

      .hj-message-bubble p.hj-message-p:last-child {
        margin-bottom: 0;
      }

      .hj-message-list {
        margin: 6px 0;
        padding-left: 18px;
        list-style-type: disc;
      }

      .hj-message-list li {
        margin-bottom: 4px;
      }

      .hj-message-time {
        font-size: 10px;
        color: ${colors.textSecondary};
        margin-top: 3px;
        padding: 0 4px;
      }

      /* Typing Indicator */
      .hj-typing-indicator {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 10px 14px;
        background: ${colors.bubbleConcierge};
        border: 1px solid ${colors.bubbleConciergeBorder};
        border-radius: 18px;
        border-bottom-left-radius: 4px;
        width: fit-content;
      }

      .hj-typing-indicator span {
        width: 6px;
        height: 6px;
        background: ${colors.primary};
        border-radius: 50%;
        animation: hj-bounce 1.4s infinite ease-in-out both;
      }

      .hj-typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
      .hj-typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
      .hj-typing-indicator span:nth-child(3) { animation-delay: 0s; }

      @keyframes hj-bounce {
        0%, 80%, 100% { transform: scale(0.6); opacity: 0.3; }
        40% { transform: scale(1); opacity: 1; }
      }

      /* Quick Replies Container */
      .hj-quick-replies {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        padding: 0 14px 10px;
        background: ${colors.messagesBg};
      }

      .hj-quick-reply {
        background: #ffffff;
        color: #0f766e;
        border: 1.5px solid #0d9488;
        padding: 6px 13px;
        border-radius: 20px;
        font-size: 12.5px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.15s ease;
        box-shadow: 0 1px 2px rgba(13, 148, 136, 0.1);
      }

      .hj-quick-reply:hover {
        background: #0d9488;
        color: #ffffff;
        transform: translateY(-1px);
        box-shadow: 0 3px 8px rgba(13, 148, 136, 0.25);
      }

      /* Completion Card */
      .hj-completion-card {
        background: #ffffff;
        border: 1.5px solid #10b981;
        border-radius: 16px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.12);
        margin: 6px 0;
        animation: hj-fadeIn 0.3s ease;
      }

      .hj-completion-badge {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: #ecfdf5;
        color: #059669;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 8px;
        box-shadow: 0 2px 6px rgba(16, 185, 129, 0.2);
      }

      .hj-completion-badge svg {
        width: 20px;
        height: 20px;
        fill: currentColor;
      }

      .hj-completion-card h4 {
        font-size: 14.5px;
        font-weight: 700;
        color: #065f46;
        margin-bottom: 4px;
      }

      .hj-completion-card p {
        font-size: 12.5px;
        color: #475569;
        line-height: 1.45;
        margin-bottom: 12px;
      }

      .hj-restart-btn {
        background: #0d9488;
        color: #ffffff;
        border: none;
        padding: 7px 16px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 700;
        cursor: pointer;
        transition: background 0.15s;
      }

      .hj-restart-btn:hover {
        background: #0f766e;
      }

      /* Input Area (Clean single-line expanding input) */
      #hj-input-area {
        padding: 10px 14px;
        border-top: 1px solid ${colors.border};
        background: #ffffff;
        display: flex;
        align-items: flex-end;
        gap: 8px;
        flex-shrink: 0;
      }

      #hj-input-wrapper {
        flex: 1;
        display: flex;
        align-items: center;
        background: ${colors.inputBg};
        border: 1.5px solid ${colors.inputBorder};
        border-radius: 22px;
        padding: 7px 14px;
        transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
      }

      #hj-input-wrapper:focus-within {
        border-color: ${colors.primary};
        background: #ffffff;
        box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.12);
      }

      #hj-message-input {
        width: 100%;
        border: none;
        background: transparent;
        font-size: 13.5px;
        line-height: 1.45;
        color: ${colors.text};
        resize: none;
        max-height: 90px;
        min-height: 22px;
        outline: none;
        padding: 1px 0;
        font-family: inherit;
      }

      #hj-message-input::placeholder {
        color: ${colors.textSecondary};
      }

      #hj-send-btn {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: linear-gradient(135deg, #0d9488 0%, #0891b2 100%);
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        transition: transform 0.15s, opacity 0.15s, box-shadow 0.15s;
        box-shadow: 0 2px 6px rgba(13, 148, 136, 0.3);
      }

      #hj-send-btn:hover:not(:disabled) {
        transform: scale(1.05);
        box-shadow: 0 4px 10px rgba(13, 148, 136, 0.4);
      }

      #hj-send-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
        box-shadow: none;
        transform: none;
      }

      #hj-send-btn svg {
        width: 17px;
        height: 17px;
        fill: #ffffff;
      }

      /* Completion Banner in Input Area */
      #hj-completed-banner {
        display: none;
        flex: 1;
        align-items: center;
        justify-content: space-between;
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
        border-radius: 12px;
        padding: 8px 12px;
        font-size: 12px;
        color: #065f46;
        font-weight: 600;
      }

      #hj-completed-banner.hj-visible {
        display: flex;
      }

      /* Footer */
      #hj-footer {
        text-align: center;
        padding: 5px 8px;
        font-size: 10px;
        color: ${colors.textSecondary};
        background: #ffffff;
        border-top: 1px solid ${colors.border};
        flex-shrink: 0;
      }

      #hj-footer a {
        color: ${colors.primary};
        text-decoration: none;
        font-weight: 600;
      }

      /* Error Banner */
      .hj-error {
        background: #fef2f2;
        border: 1px solid #fecaca;
        color: #dc2626;
        padding: 8px 12px;
        border-radius: 10px;
        font-size: 12px;
        margin: 4px 14px;
        animation: hj-fadeIn 0.2s ease;
      }

      /* Power Inputs for Scheduling */
      .hj-power-inputs {
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 10px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        margin-top: 8px;
      }

      .hj-power-inputs label {
        font-size: 11px;
        color: ${colors.textSecondary};
        font-weight: 600;
      }

      .hj-power-inputs input[type="date"],
      .hj-power-inputs input[type="time"],
      .hj-power-inputs select {
        width: 100%;
        padding: 7px 10px;
        border: 1px solid ${colors.border};
        border-radius: 8px;
        font-size: 13px;
        background: #ffffff;
        color: ${colors.text};
        outline: none;
      }

      .hj-power-inputs input:focus,
      .hj-power-inputs select:focus {
        border-color: ${colors.primary};
      }

      .hj-submit-actions {
        display: flex;
        gap: 8px;
        margin-top: 4px;
      }

      .hj-submit-actions button {
        flex: 1;
        padding: 7px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        border: none;
      }

      .hj-btn-primary {
        background: ${colors.primary};
        color: #ffffff;
      }

      .hj-btn-secondary {
        background: #e2e8f0;
        color: ${colors.text};
      }

      /* Mobile Full Screen */
      @media (max-width: 480px) {
        #hj-chat-window {
          width: 100vw;
          height: 100vh;
          max-height: 100vh;
          bottom: 0;
          right: 0;
          border-radius: 0;
          border: none;
        }

        #hj-launcher {
          bottom: 16px;
          right: 16px;
          width: 56px;
          height: 56px;
        }
      }
    `;

    const existing = document.getElementById('heyjarvis-widget-styles');
    if (existing) existing.remove();
    document.head.appendChild(style);
  }

  // ─── DOM Creation ─────────────────────────────────────────────────
  function createWidgetDOM() {
    // Launcher
    const launcher = document.createElement('button');
    launcher.id = 'hj-launcher';
    launcher.setAttribute('aria-label', 'Open dental concierge chat');
    launcher.innerHTML = `
      <svg class="hj-chat-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-3 9H7v-2h10v2zm-4 4H7v-2h6v2zm4-8H7V5h10v2z"/>
      </svg>
      <svg class="hj-close-icon" style="display:none;" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
      </svg>
      <span id="hj-badge" title="Concierge is online"></span>
    `;
    document.body.appendChild(launcher);

    // Chat Window
    const chatWindow = document.createElement('div');
    chatWindow.id = 'hj-chat-window';
    chatWindow.innerHTML = `
      <div id="hj-header">
        <div id="hj-header-avatar">
          <!-- Dental tooth / shield sparkle icon -->
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C8.5 2 6 4.5 6 7.5c0 2.2 1.1 4.2 2 6.5.9 2.3 1.5 5 2.5 5s1.2-3 1.5-4c.3 1 1 4 1.5 4s1.6-2.7 2.5-5c.9-2.3 2-4.3 2-6.5C18 4.5 15.5 2 12 2zm0 4c1.1 0 2 .9 2 2s-.9 2-2 2-2-.9-2-2 .9-2 2-2z"/>
          </svg>
        </div>
        <div id="hj-header-info">
          <h3 id="hj-header-title">${escapeHtml(state.title)}</h3>
          <div class="hj-header-status">
            <span class="hj-status-dot"></span>
            <span id="hj-header-subtitle">${escapeHtml(state.subtitle)}</span>
          </div>
        </div>
        <button id="hj-close-btn" aria-label="Close concierge chat">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </button>
      </div>

      <div id="hj-messages"></div>
      <div id="hj-quick-replies"></div>

      <div id="hj-input-area">
        <div id="hj-input-wrapper">
          <textarea id="hj-message-input" rows="1" placeholder="Type a message or request an appointment..." aria-label="Message input"></textarea>
        </div>
        <button id="hj-send-btn" aria-label="Send message">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
          </svg>
        </button>
        <div id="hj-completed-banner">
          <span>✓ Appointment Request Submitted</span>
          <button class="hj-restart-btn" id="hj-banner-restart">New Chat</button>
        </div>
      </div>

      <div id="hj-footer">
        Powered by <a href="https://heyjarvis.ai" target="_blank" rel="noopener">HeyJarvis Dental Cloud</a>
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
      inputWrapper: document.getElementById('hj-input-wrapper'),
      messageInput: document.getElementById('hj-message-input'),
      sendBtn: document.getElementById('hj-send-btn'),
      closeBtn: document.getElementById('hj-close-btn'),
      completedBanner: document.getElementById('hj-completed-banner'),
      bannerRestart: document.getElementById('hj-banner-restart'),
      titleEl: document.getElementById('hj-header-title'),
      subtitleEl: document.getElementById('hj-header-subtitle'),
    };
  }

  // ─── UI Helpers ───────────────────────────────────────────────────
  function toggleChat(open) {
    state.isOpen = open !== undefined ? open : !state.isOpen;
    elements.chatWindow.classList.toggle('hj-open', state.isOpen);
    elements.launcher.classList.toggle('hj-open', state.isOpen);
    if (state.isOpen) {
      if (!state.isComplete) {
        elements.messageInput.focus();
      }
      scrollToBottom();
    }
  }

  function scrollToBottom() {
    if (elements.messages) {
      setTimeout(() => {
        elements.messages.scrollTop = elements.messages.scrollHeight;
      }, 30);
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
            <button class="hj-btn-primary" id="hj-power-submit">Submit Request</button>
          </div>
        </div>
      `;
    }

    const formattedBody = isPatient ? escapeHtml(text) : formatMessageText(text);

    wrapper.innerHTML = `
      ${senderLabel}
      <div class="hj-message-bubble">${formattedBody}</div>
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
        const date = document.getElementById('hj-power-date')?.value;
        const time = document.getElementById('hj-power-time')?.value;
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
      const label = typeof reply === 'object' ? (reply.label || reply.text) : reply;
      btn.textContent = label;
      btn.addEventListener('click', () => {
        removeQuickReplies();
        sendMessage(label);
      });
      elements.quickReplies.appendChild(btn);
    });
    scrollToBottom();
  }

  function removeQuickReplies() {
    elements.quickReplies.innerHTML = '';
  }

  function showCompletionCard(summaryText) {
    state.isComplete = true;
    removeQuickReplies();

    const card = document.createElement('div');
    card.className = 'hj-completion-card';
    card.innerHTML = `
      <div class="hj-completion-badge">
        <svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
      </div>
      <h4>Appointment Request Submitted!</h4>
      <p>${escapeHtml(summaryText || 'Our front desk has received your request and will follow up shortly to confirm.')}</p>
      <button class="hj-restart-btn" id="hj-restart-chat">Start New Request</button>
    `;

    elements.messages.appendChild(card);
    document.getElementById('hj-restart-chat')?.addEventListener('click', resetConversation);

    // Swap input area to completed banner
    if (elements.inputWrapper && elements.sendBtn && elements.completedBanner) {
      elements.inputWrapper.style.display = 'none';
      elements.sendBtn.style.display = 'none';
      elements.completedBanner.classList.add('hj-visible');
    }

    scrollToBottom();
  }

  function resetConversation() {
    state.isComplete = false;
    state.sessionId = generateId();
    localStorage.setItem('heyjarvis_session_id', state.sessionId);
    state.conversationId = null;
    state.messages = [];
    elements.messages.innerHTML = '';
    removeQuickReplies();

    if (elements.inputWrapper && elements.sendBtn && elements.completedBanner) {
      elements.inputWrapper.style.display = 'flex';
      elements.sendBtn.style.display = 'flex';
      elements.completedBanner.classList.remove('hj-visible');
      elements.messageInput.disabled = false;
      elements.messageInput.value = '';
    }

    initializeConversation();
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

    setTimeout(() => errorEl.remove(), 6000);
  }

  // ─── API Communication ────────────────────────────────────────────
  async function apiRequest(endpoint, data) {
    const url = state.apiUrl
      ? `${state.apiUrl}${endpoint}`
      : `http://localhost:8000${endpoint}`;

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

      if (result.practice_name && elements.titleEl) {
        elements.titleEl.textContent = result.practice_name;
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

      state.initialized = true;
    } catch (error) {
      console.warn('HeyJarvis: Fallback to local concierge intro:', error);
      const defaultIntro = "Hello! I'm the AI patient concierge for Raleigh Comprehensive & Cosmetic Dentistry. How can we help you today? Feel free to ask about our services, insurance, or request an appointment.";
      addMessage('concierge', defaultIntro, { timestamp: Date.now() });
      showQuickReplies([
        'Book Appointment',
        'Toothache / Emergency',
        'Office Hours & Location',
        'Accepted Insurances',
      ]);
      state.initialized = true;
    }
  }

  async function sendMessage(text) {
    if (!text || !text.trim() || state.isSubmitting || state.isComplete) return;

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
        showCompletionCard(result.summary);
      }
    } catch (error) {
      hideTyping();
      console.error('HeyJarvis: Message send failed:', error);
      showError('Unable to connect to the front desk service. Please try again or call our clinic.');
    } finally {
      state.isSubmitting = false;
      if (!state.isComplete) {
        elements.sendBtn.disabled = false;
        elements.messageInput.focus();
      }
    }
  }

  async function submitAppointmentRequest(date, time) {
    addMessage(
      'patient',
      `Requested appointment date: ${date || 'Flexible'} (${time || 'Flexible'})`,
      { timestamp: Date.now() }
    );

    showTyping();

    try {
      const result = await apiRequest('/api/v1/widget/submit/', {
        session_id: state.sessionId,
        practice_slug: state.practiceSlug,
        preferred_date: date,
        preferred_time: time,
      });

      hideTyping();

      if (result.response) {
        addMessage('concierge', result.response, { timestamp: Date.now() });
      }

      showCompletionCard(result.summary || 'Your appointment request has been scheduled with our front desk.');
    } catch (error) {
      hideTyping();
      console.error('HeyJarvis: Submit appointment failed:', error);
      showError('Could not submit request at this time. Please try again.');
    }
  }

  // ─── Event Handlers ───────────────────────────────────────────────
  function autoResizeInput() {
    if (!elements.messageInput) return;
    elements.messageInput.style.height = 'auto';
    elements.messageInput.style.height = Math.min(elements.messageInput.scrollHeight, 90) + 'px';
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

    // Reset button in completed banner
    elements.bannerRestart?.addEventListener('click', resetConversation);

    // Input keyboard handling
    elements.messageInput.addEventListener('input', autoResizeInput);
    elements.messageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(elements.messageInput.value);
      }
    });

    // Close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && state.isOpen) {
        toggleChat(false);
      }
    });

    // Close on click outside (desktop only)
    document.addEventListener('click', (e) => {
      if (
        state.isOpen &&
        window.innerWidth > 480 &&
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

    // Read config from script tag attributes
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

      // If loaded from Vite port 3000 or file:// protocol, route API requests to backend port 8000
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

    state.sessionId = generateSessionId();

    injectStyles();
    createWidgetDOM();
    setupEventListeners();
    initializeConversation();

    // Global API
    global.HeyJarvis = {
      open: () => toggleChat(true),
      close: () => toggleChat(false),
      toggle: () => toggleChat(),
      reset: resetConversation,
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

  // Auto-init
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
