/* HeyJarvis Concierge — Production Embeddable Widget v2
 *
 * Embed on any site:
 *   <script async src="https://YOUR-HOST/widget.js"
 *           data-heyjarvis-client="pk_xxx"
 *           data-heyjarvis-form="false"
 *           data-heyjarvis-auto-open="false"></script>
 *
 * Hosted full-screen mode (server-rendered shell):
 *   Set window.__HJ_CONFIG = { clientKey: 'pk_xxx', hosted: true } before loading widget.js
 *   Provide mount elements with ids: hj-title, hj-body, hj-msg, hj-send, hj-reset
 *
 * Modes:  conversational (default) | form (data-heyjarvis-form="true")
 * Isolated via Shadow DOM for embed mode; direct DOM for hosted mode.
 * IIFE — no global pollution.
 */
(function () {
  'use strict';
  try {
    var script = document.currentScript;
    if (!script) return;

    var cfg = window.__HJ_CONFIG || {};
    var clientKey = (script.getAttribute('data-heyjarvis-client') || cfg.clientKey || '').trim();
    if (!clientKey) return;

    // API lives on the same host that serves widget.js (works for /widget.js and /static/widget.js).
    var scriptOrigin = '';
    try { scriptOrigin = new URL(script.src, location.href).origin; } catch (e) {}
    var apiBase = (window.__HJ_API_BASE__ || scriptOrigin || '').replace(/\/+$/, '');
    if (!apiBase) return;

    var formMode = (script.getAttribute('data-heyjarvis-form') || '').toLowerCase() === 'true';
    var hosted = !!(script.getAttribute('data-heyjarvis-hosted') || cfg.hosted);

    if (hosted) {
      initHosted(clientKey, apiBase, formMode);
      return;
    }

    // ── Hosted mode ───────────────────────────────────────────────────────────
    function initHosted(clientKey, apiBase, formMode) {
      var bodyEl = document.getElementById('hj-body') || document.getElementById('body');
      var msgEl = document.getElementById('hj-msg') || document.getElementById('msg');
      var sendEl = document.getElementById('hj-send') || document.getElementById('send');
      var resetEl = document.getElementById('hj-reset') || document.getElementById('resetBtn');
      var titleEl = document.getElementById('hj-title') || document.getElementById('title');
      if (!bodyEl || !msgEl || !sendEl) return;

      var conversationId = null;
      var submitted = false;
      var emergencyDetected = false;
      var fields = {};
      var config = null;

      function esc(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }

      function bubble(html, isUser) {
        var el = document.createElement('div');
        el.className = 'bubble ' + (isUser ? 'user' : 'bot');
        el.innerHTML = html;
        bodyEl.appendChild(el);
        bodyEl.scrollTop = bodyEl.scrollHeight;
      }

      function clearEmpty() {
        var empty = document.getElementById('empty');
        if (empty) empty.remove();
      }

      function appendBubble(html, isUser) {
        clearEmpty();
        bubble(html, isUser);
      }

      function showTyping() {
        clearEmpty();
        var el = document.createElement('div');
        el.className = 'typing';
        el.id = 'hj-typing';
        el.innerHTML = '<span></span><span></span><span></span>';
        bodyEl.appendChild(el);
        bodyEl.scrollTop = bodyEl.scrollHeight;
      }

      function hideTyping() {
        var el = document.getElementById('hj-typing');
        if (el) el.remove();
      }

      function setDisabled(state) {
        msgEl.disabled = state;
        sendEl.disabled = state;
      }

      function api(path, options) {
        return fetch(apiBase + path, {
          method: options && options.method || 'GET',
          headers: { 'Content-Type': 'application/json' },
          body: options && options.body ? JSON.stringify(options.body) : undefined,
        }).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        });
      }

      function loadConfig() {
        return api('/api/v1/public/config?client_key=' + encodeURIComponent(clientKey))
          .then(function (c) {
            config = c;
            if (titleEl && c.tenant_name) titleEl.textContent = c.tenant_name + ' — Concierge';
            if (c.greeting) {
              appendBubble(esc(c.greeting));
            }
            if (c.form_mode === true || c.form_mode === 'true') {
              switchToForm();
            }
            return c;
          });
      }

      function startConversation() {
        return api('/api/v1/public/conversations?client_key=' + encodeURIComponent(clientKey), {
          method: 'POST',
          body: {},
        }).then(function (data) {
          conversationId = data.conversation_id;
          if (data.reply) appendBubble(esc(data.reply));
          return data;
        });
      }

      function sendMessage(text) {
        if (!text || !conversationId) return Promise.resolve({});
        return api('/api/v1/public/conversations/' + conversationId + '/messages?client_key=' + encodeURIComponent(clientKey), {
          method: 'POST',
          body: { message: text },
        }).then(function (data) {
          return data;
        });
      }

      function initSession() {
        showTyping();
        loadConfig().then(function () {
          hideTyping();
          return startConversation();
        }).catch(function () {
          hideTyping();
          appendBubble("We're having trouble connecting right now. Please try again later, or call us directly.");
        });
      }

      function switchToForm() {
        // For now, keep hosted page in conversational mode.
        // If form mode is enabled, host should serve a form-oriented shell.
      }

      function resetChat() {
        bodyEl.innerHTML = '<div class="empty-state" id="empty"><div class="icon">&#128172;</div><div><strong>Chat Reset</strong></div><div>Starting a new conversation...</div></div>';
        submitted = false;
        conversationId = null;
        fields = {};
        setDisabled(false);
        initSession();
      }

      sendEl.addEventListener('click', function () {
        var text = msgEl.value.trim();
        if (!text || submitted) return;
        appendBubble(esc(text), true);
        msgEl.value = '';
        showTyping();
        sendMessage(text).then(function (data) {
          hideTyping();
          if (!data) return;
          if (data.reply) appendBubble(esc(data.reply));
          if (data.state === 'submitted' || data.state === 'complete') {
            markSubmitted(data);
          }
        }).catch(function () {
          hideTyping();
          appendBubble('Connection issue. Please try again or call us directly.');
        });
      });

      msgEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendEl.click();
        }
      });

      if (resetEl) {
        resetEl.addEventListener('click', resetChat);
      }

      function markSubmitted(data) {
        submitted = true;
        setDisabled(true);
        var tenant = config && config.tenant_name ? config.tenant_name : 'us';
        setTimeout(function () {
          clearEmpty();
          bodyEl.innerHTML =
            '<div class="empty-state">' +
              '<div class="icon">&#9989;</div>' +
              '<div><strong>Message Sent!</strong></div>' +
              '<div>Thank you for reaching out to ' + esc(tenant) + '. We\'ll get back to you shortly.</div>' +
            '</div>';
        }, 400);
      }

      initSession();
    }

    // ── Embed mode ────────────────────────────────────────────────────────────
    var hosted = !!(script.getAttribute('data-heyjarvis-hosted') || cfg.hosted);

    if (hosted) {
      initHosted(clientKey, apiBase, formMode);
      return;
    }

    // ── CSS (all rules scoped via Shadow DOM) ────────────────────────────────
    var css = [
      ':host { all: initial; }',
      '.hj-root {',
      '  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;',
      '  color: #1a1a1a;',
      '  -webkit-text-size-adjust: 100%;',
      '}',
      '/* ── Launcher ── */',
      '.hj-launcher, .hj-frame { pointer-events: auto; }',
      '.hj-launcher {',
      '  position: fixed; right: 16px; bottom: 16px; z-index: 2147483647;',
      '  display: flex; flex-direction: column; align-items: flex-end; gap: 8px;',
      '}',
      '.hj-launcher-btn {',
      '  border: none; border-radius: 999px; cursor: pointer;',
      '  background: linear-gradient(135deg, #1a3c2a 0%, #2d6a4f 100%);',
      '  color: #fff; font-weight: 700; font-size: 15px; font-family: inherit;',
      '  padding: 14px 22px;',
      '  box-shadow: 0 6px 24px rgba(0,0,0,.22);',
      '  display: flex; align-items: center; gap: 8px;',
      '  transition: transform .15s ease, box-shadow .15s ease;',
      '  user-select: none; -webkit-tap-highlight-color: transparent;',
      '}',
      '.hj-launcher-btn:hover { transform: translateY(-1px); box-shadow: 0 8px 28px rgba(0,0,0,.28); }',
      '.hj-launcher-btn:active { transform: translateY(0); }',
      '.hj-launcher-icon { font-size: 20px; line-height: 1; }',
      '.hj-launcher-label { display: none; }',
      '@media (min-width: 400px) { .hj-launcher-label { display: inline; } }',
      '.hj-badge {',
      '  background: #e74c3c; color: #fff; font-size: 11px; font-weight: 700;',
      '  border-radius: 999px; padding: 2px 7px; min-width: 18px; text-align: center;',
      '  line-height: 1.4;',
      '}',
      '/* ── Frame ── */',
      '.hj-frame {',
      '  position: fixed; right: 16px; bottom: 80px; z-index: 2147483647;',
      '  width: 390px; max-width: calc(100vw - 32px); height: 580px; max-height: calc(100vh - 100px);',
      '  background: #fff; border-radius: 18px; border: 1px solid #e8e8e8;',
      '  box-shadow: 0 24px 60px rgba(0,0,0,.18);',
      '  display: none; flex-direction: column; overflow: hidden;',
      '  transform: translateY(12px) scale(.97); opacity: 0;',
      '  transition: transform .22s cubic-bezier(.2,.8,.2,1), opacity .18s ease;',
      '}',
      '.hj-frame.open {',
      '  display: flex;',
      '  transform: translateY(0) scale(1); opacity: 1;',
      '}',
      '@media (max-width: 420px) {',
      '  .hj-frame {',
      '    right: 0; bottom: 0; width: 100vw; max-width: 100vw;',
      '    height: 100dvh; max-height: 100dvh; border-radius: 0;',
      '  }',
      '}',
      '/* ── Header ── */',
      '.hj-head {',
      '  padding: 14px 16px; border-bottom: 1px solid #eee;',
      '  font-weight: 700; font-size: 15px; display: flex;',
      '  justify-content: space-between; align-items: center; gap: 8px;',
      '  background: linear-gradient(135deg, #1a3c2a 0%, #2d6a4f 100%);',
      '  color: #fff; flex-shrink: 0;',
      '}',
      '.hj-head-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }',
      '.hj-head-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }',
      '.hj-mode-toggle {',
      '  background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.25);',
      '  color: #fff; font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 8px;',
      '  cursor: pointer; font-family: inherit; white-space: nowrap;',
      '  transition: background .15s;',
      '}',
      '.hj-mode-toggle:hover { background: rgba(255,255,255,.28); }',
      '.hj-head-close {',
      '  background: none; border: none; color: #fff; font-size: 22px;',
      '  cursor: pointer; width: 30px; height: 30px; border-radius: 8px;',
      '  display: flex; align-items: center; justify-content: center;',
      '  transition: background .15s; line-height: 1;',
      '}',
      '.hj-head-close:hover { background: rgba(255,255,255,.15); }',
      '/* ── Body ── */',
      '.hj-body {',
      '  flex: 1; overflow-y: auto; padding: 14px 14px;',
      '  display: flex; flex-direction: column; gap: 10px;',
      '  overscroll-behavior: contain;',
      '}',
      '/* ── Bubbles ── */',
      '.hj-bubble {',
      '  background: #f2f6f4; border-radius: 16px; padding: 10px 15px;',
      '  max-width: 88%; align-self: flex-start;',
      '  word-wrap: break-word; overflow-wrap: break-word;',
      '  font-size: 14px; line-height: 1.55;',
      '  animation: hj-fadeIn .2s ease;',
      '}',
      '.hj-user-bubble {',
      '  background: linear-gradient(135deg, #1a3c2a, #2d6a4f); color: #fff;',
      '  border-radius: 16px; padding: 10px 15px;',
      '  max-width: 88%; align-self: flex-end;',
      '  word-wrap: break-word; overflow-wrap: break-word;',
      '  font-size: 14px; line-height: 1.55;',
      '  animation: hj-fadeIn .2s ease;',
      '}',
      '@keyframes hj-fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }',
      '/* ── Typing indicator ── */',
      '.hj-typing {',
      '  display: flex; gap: 5px; padding: 6px 4px; align-self: flex-start;',
      '}',
      '.hj-typing span {',
      '  width: 8px; height: 8px; background: #bbb; border-radius: 50%;',
      '  animation: hj-bounce 1.4s ease-in-out infinite;',
      '}',
      '.hj-typing span:nth-child(2) { animation-delay: .18s; }',
      '.hj-typing span:nth-child(3) { animation-delay: .36s; }',
      '@keyframes hj-bounce {',
      '  0%, 60%, 100% { transform: translateY(0); }',
      '  30% { transform: translateY(-7px); }',
      '}',
      '/* ── Quick options (chips) ── */',
      '.hj-options { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 6px; }',
      '.hj-opt {',
      '  border: 1.5px solid #d0d8d4; border-radius: 10px; padding: 7px 13px;',
      '  cursor: pointer; background: #f8fbfa; font-size: 13px; font-family: inherit;',
      '  transition: all .15s; color: #1a3c2a;',
      '}',
      '.hj-opt:hover { border-color: #2d6a4f; background: #eaf2ec; }',
      '.hj-opt.picked { border-color: #2d6a4f; background: #d4ead9; }',
      '/* ── Summary card ── */',
      '.hj-summary {',
      '  background: #f0f5f2; border: 1px solid #d4e4da; border-radius: 12px;',
      '  padding: 12px 14px; margin: 4px 0;',
      '}',
      '.hj-summary-title { font-weight: 700; font-size: 13px; color: #1a3c2a; margin-bottom: 6px; }',
      '.hj-summary-row { font-size: 13px; color: #333; line-height: 1.6; }',
      '.hj-summary-row strong { color: #1a3c2a; }',
      '.hj-summary-edit {',
      '  background: none; border: none; color: #2d6a4f; font-size: 12px;',
      '  cursor: pointer; text-decoration: underline; font-family: inherit; margin-top: 6px; padding: 0;',
      '}',
      '/* ── Success message ── */',
      '.hj-success {',
      '  background: #eaf5ee; border: 1px solid #b2d9be; border-radius: 14px;',
      '  padding: 16px; text-align: center; animation: hj-fadeIn .3s ease;',
      '}',
      '.hj-success-icon { font-size: 36px; margin-bottom: 6px; }',
      '.hj-success-title { font-weight: 700; font-size: 16px; color: #1a3c2a; margin-bottom: 4px; }',
      '.hj-success-body { font-size: 13px; color: #555; line-height: 1.5; }',
      '/* ── Emergency banner ── */',
      '.hj-emergency {',
      '  background: #fff5f5; border: 2px solid #e74c3c; border-radius: 14px;',
      '  padding: 14px 16px; text-align: center; animation: hj-fadeIn .25s ease;',
      '}',
      '.hj-emergency-icon { font-size: 28px; margin-bottom: 4px; }',
      '.hj-emergency-title { font-weight: 700; font-size: 15px; color: #c0392b; }',
      '.hj-emergency-body { font-size: 13px; color: #555; margin-top: 4px; line-height: 1.5; }',
      '/* ── Form mode ── */',
      '.hj-form { padding: 4px 2px; display: flex; flex-direction: column; gap: 11px; }',
      '.hj-field label {',
      '  display: block; font-weight: 600; font-size: 13px; color: #333; margin-bottom: 4px;',
      '}',
      '.hj-field input, .hj-field select, .hj-field textarea {',
      '  width: 100%; font: 14px/1.5 inherit; padding: 10px 13px;',
      '  border: 1.5px solid #d5d5d5; border-radius: 10px; outline: none;',
      '  background: #fafafa; color: #1a1a1a; box-sizing: border-box;',
      '  transition: border-color .15s;',
      '}',
      '.hj-field input:focus, .hj-field select:focus, .hj-field textarea:focus {',
      '  border-color: #2d6a4f; background: #fff;',
      '}',
      '.hj-field textarea { resize: vertical; min-height: 70px; }',
      '.hj-form-actions { display: flex; gap: 8px; margin-top: 4px; }',
      '.hj-submit-btn {',
      '  flex: 1; border: none; border-radius: 10px;',
      '  background: linear-gradient(135deg, #1a3c2a, #2d6a4f); color: #fff;',
      '  padding: 11px 20px; font-weight: 700; font-size: 14px; font-family: inherit;',
      '  cursor: pointer; transition: opacity .15s;',
      '}',
      '.hj-submit-btn:disabled { opacity: .5; cursor: not-allowed; }',
      '.hj-submit-btn:not(:disabled):hover { opacity: .88; }',
      '/* ── Input area (chat mode) ── */',
      '.hj-input-area {',
      '  padding: 10px 12px; border-top: 1px solid #eee;',
      '  display: flex; gap: 8px; align-items: center; flex-shrink: 0;',
      '}',
      '.hj-input-area input {',
      '  flex: 1; font: 14px/1.4 inherit; padding: 10px 14px;',
      '  border: 1.5px solid #ddd; border-radius: 12px; outline: none;',
      '  background: #f7f7f7; color: #1a1a1a; min-width: 0;',
      '}',
      '.hj-input-area input:focus { border-color: #2d6a4f; background: #fff; }',
      '.hj-input-area input:disabled { opacity: .5; }',
      '.hj-send-btn {',
      '  border: none; border-radius: 12px;',
      '  background: linear-gradient(135deg, #1a3c2a, #2d6a4f); color: #fff;',
      '  padding: 10px 16px; font-weight: 700; cursor: pointer; font-size: 14px; font-family: inherit;',
      '  transition: opacity .15s; flex-shrink: 0;',
      '}',
      '.hj-send-btn:disabled { opacity: .4; cursor: not-allowed; }',
      '/* ── Error / Offline ── */',
      '.hj-error {',
      '  color: #c0392b; font-size: 13px; text-align: center; padding: 10px 8px;',
      '  background: #fdf0f0; border-radius: 10px;',
      '}',
      '.hj-offline { color: #777; font-size: 13px; text-align: center; padding: 20px 12px; line-height: 1.6; }',
      '/* ── Loading ── */',
      '.hj-loading {',
      '  display: flex; align-items: center; justify-content: center; gap: 10px;',
      '  padding: 28px; color: #888; font-size: 13px;',
      '}',
      '.hj-spinner {',
      '  width: 20px; height: 20px; border: 2.5px solid #e0e0e0;',
      '  border-top-color: #2d6a4f; border-radius: 50%;',
      '  animation: hj-spin .7s linear infinite;',
      '}',
      '@keyframes hj-spin { to { transform: rotate(360deg); } }',
      '/* ── Chat / Form switcher ── */',
      '.hj-chat-panel, .hj-form-panel { display: none; flex-direction: column; flex: 1; min-height: 0; }',
      '.hj-chat-panel.active, .hj-form-panel.active { display: flex; }',
      '.hj-form-panel { overflow-y: auto; padding: 14px; }',
      '/* ── Scrollbar ── */',
      '.hj-body::-webkit-scrollbar, .hj-form-panel::-webkit-scrollbar { width: 5px; }',
      '.hj-body::-webkit-scrollbar-thumb, .hj-form-panel::-webkit-scrollbar-thumb { background: #d0d0d0; border-radius: 3px; }',
    ].join('\n');

    // ── State ────────────────────────────────────────────────────────────────
    var conversationId = null;
    var conversationState = null;
    var isOpen = false;
    var started = false;
    var config = null;
    var unreadCount = 0;
    var isSubmitting = false;
    var submitted = false;
    var emergencyDetected = false;
    var fields = {};
    var fieldHistory = [];
    var errorCount = 0;
    var formEditMode = false;
    var isFormActive = !formMode;

    // ── DOM Construction ────────────────────────────────────────────────────
    var mount = document.createElement('div');
    // The zero-size host lets clicks pass through to the page; the launcher and chat window opt back in.
    // Max z-index so the clinic site's own headers/overlays can't cover the button.
    mount.style.cssText = 'position:fixed;top:0;left:0;width:0;height:0;pointer-events:none;z-index:2147483647;';
    document.documentElement.appendChild(mount);

    var shadow = mount.attachShadow({ mode: 'open' });
    var styleEl = document.createElement('style');
    styleEl.textContent = css;
    shadow.appendChild(styleEl);

    var root = document.createElement('div');
    root.className = 'hj-root';
    root.setAttribute('role', 'region');
    root.setAttribute('aria-label', 'Chat widget');

    root.innerHTML =
      '<div class="hj-frame" id="hj-frame">' +
        '<div class="hj-head">' +
          '<span class="hj-head-title" id="hj-title">Chat with us</span>' +
          '<div class="hj-head-actions">' +
            '<button class="hj-mode-toggle" id="hj-mode-toggle" aria-label="Switch to form" title="Switch to form">Form</button>' +
            '<button class="hj-head-close" id="hj-close" aria-label="Close chat">&times;</button>' +
          '</div>' +
        '</div>' +
        '<div class="hj-chat-panel active" id="hj-chat-panel">' +
          '<div class="hj-body" id="hj-body"></div>' +
          '<div class="hj-input-area" id="hj-input-area">' +
            '<input id="hj-msg" type="text" autocomplete="off" placeholder="Type a message..." aria-label="Message" maxlength="2000"/>' +
            '<button class="hj-send-btn" id="hj-send" aria-label="Send message">Send</button>' +
          '</div>' +
        '</div>' +
        '<div class="hj-form-panel" id="hj-form-panel">' +
          '<div class="hj-body" id="hj-form-body"></div>' +
        '</div>' +
      '</div>' +
      '<div class="hj-launcher">' +
        '<button class="hj-launcher-btn" id="hj-open" aria-label="Open chat">' +
          '<span class="hj-launcher-icon">&#128172;</span>' +
          '<span class="hj-launcher-label" id="hj-label">Chat with us</span>' +
          '<span class="hj-badge" id="hj-badge" style="display:none">1</span>' +
        '</button>' +
      '</div>';

    shadow.appendChild(root);

    // Cache element refs
    var frame = shadow.getElementById('hj-frame');
    var body = shadow.getElementById('hj-body');
    var formBody = shadow.getElementById('hj-form-body');
    var formPanel = shadow.getElementById('hj-form-panel');
    var chatPanel = shadow.getElementById('hj-chat-panel');
    var msgInput = shadow.getElementById('hj-msg');
    var sendBtn = shadow.getElementById('hj-send');
    var openBtn = shadow.getElementById('hj-open');
    var closeBtn = shadow.getElementById('hj-close');
    var badge = shadow.getElementById('hj-badge');
    var titleEl = shadow.getElementById('hj-title');
    var modeToggle = shadow.getElementById('hj-mode-toggle');
    var launcherLabel = shadow.getElementById('hj-label');

    // ── Helpers ──────────────────────────────────────────────────────────────
    function esc(str) {
      if (str == null) return '';
      return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function appendBubble(html, isUser) {
      var el = document.createElement('div');
      el.className = isUser ? 'hj-user-bubble' : 'hj-bubble';
      el.innerHTML = html;
      body.appendChild(el);
      scrollToBottom();
    }

    function appendRaw(node) {
      body.appendChild(node);
      scrollToBottom();
    }

    function scrollToBottom() {
      requestAnimationFrame(function () {
        body.scrollTop = body.scrollHeight;
      });
    }

    function scrollFormToBottom() {
      requestAnimationFrame(function () {
        formPanel.scrollTop = formPanel.scrollHeight;
      });
    }

    var typingEl = null;
    function showTyping() {
      if (typingEl) return;
      typingEl = document.createElement('div');
      typingEl.className = 'hj-typing';
      typingEl.innerHTML = '<span></span><span></span><span></span>';
      body.appendChild(typingEl);
      scrollToBottom();
    }

    function hideTyping() {
      if (typingEl) { typingEl.remove(); typingEl = null; }
    }

    function showError(text) {
      var el = document.createElement('div');
      el.className = 'hj-error';
      el.textContent = text || 'Something went wrong. Please try again.';
      appendRaw(el);
    }

    function showOffline() {
      hideTyping();
      appendBubble(
        "We're having trouble connecting right now. Please try again later, " +
        "or call us directly. We apologize for the inconvenience!"
      );
    }

    function setLoading(show) {
      body.innerHTML = '';
      if (show) {
        var el = document.createElement('div');
        el.className = 'hj-loading';
        el.innerHTML = '<div class="hj-spinner"></div><span>Loading...</span>';
        body.appendChild(el);
      }
    }

    function setDisabled(state) {
      msgInput.disabled = state;
      sendBtn.disabled = state;
    }

    function updateBadge() {
      if (unreadCount > 0 && !isOpen) {
        badge.style.display = '';
        badge.textContent = unreadCount > 99 ? '99+' : String(unreadCount);
      } else {
        badge.style.display = 'none';
      }
    }

    function updateModeToggle() {
      if (isFormActive) {
        modeToggle.textContent = 'Chat';
        modeToggle.setAttribute('aria-label', 'Switch to chat');
        modeToggle.setAttribute('title', 'Switch to chat');
      } else {
        modeToggle.textContent = 'Form';
        modeToggle.setAttribute('aria-label', 'Switch to form');
        modeToggle.setAttribute('title', 'Switch to form');
      }
    }

    // ── Client-side Field Extraction ────────────────────────────────────────
    function extractEmail(text) {
      if (!text) return null;
      var m = text.match(/[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/);
      return m ? m[0].toLowerCase() : null;
    }

    function extractPhone(text) {
      if (!text) return null;
      // E.164-ish: strip non-digit, must be 10-15 digits
      var digits = text.replace(/\D/g, '');
      if (digits.length >= 10 && digits.length <= 15) {
        // Add country code if missing (assume US +1)
        if (digits.length === 10) digits = '1' + digits;
        return '+' + digits;
      }
      return null;
    }

    function extractName(text) {
      if (!text) return null;
      // "My name is John Smith" / "I'm John" / "John here"
      var patterns = [
        /(?:my\s+name\s+is|i'?m\s+|call\s+me\s+|this\s+is\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/i,
        /(?:^|\s)([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s|$|[,.\-!])/i,
        /(?:^|\s)([A-Z][a-z]+)(?:\s+here\s*$|,\s*)/i,
      ];
      for (var i = 0; i < patterns.length; i++) {
        var m = text.match(patterns[i]);
        if (m && m[1]) {
          var name = m[1].trim();
          // Filter out false positives (short words, common phrases)
          var stop = ['The','This','That','Here','Yes','No','Ok','Sure','Please','Thank','Thanks','Hello','Hi','Hey','Good','Morning','Afternoon','Evening','Need','Want','Looking'];
          if (name.split(' ').length <= 3 && stop.indexOf(name) === -1) {
            return name;
          }
        }
      }
      return null;
    }

    function extractService(text) {
      if (!text) return null;
      var lower = text.toLowerCase();
      var map = [
        { k: ['emergency','urgent','pain','toothache','broken','swelling','bleeding'], v: 'Emergency' },
        { k: ['checkup','check-up','cleaning','hygiene','routine'], v: 'Checkup' },
        { k: ['whitening','cosmetic','veneers','smile'], v: 'Cosmetic' },
        { k: ['implant','dental implant'], v: 'Implants' },
        { k: ['ortho','braces','alignment','straighten'], v: 'Orthodontics' },
        { k: ['crown','root canal','rct','filling','cavity','repair'], v: 'Restorative' },
        { k: ['extract','wisdom','removal'], v: 'Extraction' },
        { k: ['consult','consultation','second opinion'], v: 'Consultation' },
        { k: ['crown','cap'], v: 'Crown' },
        { k: ['bridge'], v: 'Bridge' },
        { k: ['dentures'], v: 'Dentures' },
      ];
      for (var i = 0; i < map.length; i++) {
        for (var j = 0; j < map[i].k.length; j++) {
          if (lower.indexOf(map[i].k[j]) !== -1) return map[i].v;
        }
      }
      return null;
    }

    function extractTime(text) {
      if (!text) return null;
      var patterns = [
        /\b(\d{1,2}:\d{2}\s*(?:am|pm)?)\b/i,
        /\b(\d{1,2}\s*(?:am|pm))\b/i,
      ];
      for (var i = 0; i < patterns.length; i++) {
        var m = text.match(patterns[i]);
        if (m) return m[1];
      }
      var timeWords = ['morning','afternoon','evening','noon','lunchtime'];
      var lower = text.toLowerCase();
      for (var j = 0; j < timeWords.length; j++) {
        if (lower.indexOf(timeWords[j]) !== -1) return timeWords[j];
      }
      return null;
    }

    function extractDate(text) {
      if (!text) return null;
      var patterns = [
        /\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,?\s*\d{4})?)\b/i,
        /\b(\d{1,2}\/\d{1,2}(?:\/\d{2,4})?)\b/,
        /\b(today|tomorrow|next\s+\w+)\b/i,
      ];
      for (var i = 0; i < patterns.length; i++) {
        var m = text.match(patterns[i]);
        if (m) return m[1];
      }
      return null;
    }

    function isEmergency(text) {
      if (!text) return false;
      var keywords = ['emergency','urgent','severe pain','toothache','bleeding','swelling','broken tooth',' knocked out','abscess','fever'];
      var lower = text.toLowerCase();
      for (var i = 0; i < keywords.length; i++) {
        if (lower.indexOf(keywords[i]) !== -1) return true;
      }
      return false;
    }

    // Merge extracted fields into state, return newly found
    function mergeFields(text) {
      var found = {};
      var extractors = [
        { key: 'name', fn: extractName },
        { key: 'email', fn: extractEmail },
        { key: 'phone', fn: extractPhone },
        { key: 'service', fn: extractService },
        { key: 'preferred_date', fn: extractDate },
        { key: 'preferred_time', fn: extractTime },
      ];
      for (var i = 0; i < extractors.length; i++) {
        if (!fields[extractors[i].key]) {
          var val = extractors[i].fn(text);
          if (val) {
            fields[extractors[i].key] = val;
            found[extractors[i].key] = val;
          }
        }
      }
      // Message: last substantial user message
      if (text && text.trim().length > 10 && !fields.message) {
        fields.message = text.trim();
      }
      return found;
    }

    // ── Conversation Engine (client-side) ────────────────────────────────────
    var QUESTIONS = [
      { field: 'name',        prompt: "Hi there! What's your name?" },
      { field: 'email',       prompt: "Nice to meet you, NAME! What's the best email to reach you?", after: 'name' },
      { field: 'phone',       prompt: "And a phone number?", after: 'email' },
      { field: 'service',     prompt: "What service are you looking for? (e.g. checkup, cleaning, emergency)", after: 'phone' },
      { field: 'preferred_date', prompt: "Do you have a preferred date?", after: 'service' },
      { field: 'preferred_time', prompt: "What time works best for you?", after: 'preferred_date' },
    ];

    function getNextQuestion() {
      if (submitted) return null;
      for (var i = 0; i < QUESTIONS.length; i++) {
        var q = QUESTIONS[i];
        if (!fields[q.field]) {
          var text = q.prompt;
          // Replace NAME placeholder with user's name if we have it
          if (text.indexOf('NAME') !== -1 && fields.name) {
            text = text.replace('NAME', fields.name.split(' ')[0]);
          }
          return text;
        }
      }
      if (!submitted) {
        return buildSummaryPrompt();
      }
      return null;
    }

    function buildSummaryPrompt() {
      var lines = [];
      if (fields.name) lines.push('Name: ' + fields.name);
      if (fields.email) lines.push('Email: ' +fields.email);
      if (fields.phone) lines.push('Phone: ' + fields.phone);
      if (fields.service) lines.push('Service: ' + fields.service);
      if (fields.preferred_date) lines.push('Date: ' + fields.preferred_date);
      if (fields.preferred_time) lines.push('Time: ' + fields.preferred_time);
      if (fields.message) lines.push('Note: ' + fields.message);
      return "Thanks! Here's a summary of what I have:\n\n" + lines.join('\n') + "\n\nIs this correct? Say \"submit\" or \"correct\" to confirm, or tell me what to change.";
    }

    function buildSummaryHTML() {
      if (Object.keys(fields).length === 0) return '';
      var rows = '';
      var labels = { name:'Name', email:'Email', phone:'Phone', service:'Service', preferred_date:'Date', preferred_time:'Time', message:'Message' };
      var keys = Object.keys(fields);
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        if (k === '_greeting') continue;
        if (!fields[k]) continue;
        rows += '<div class="hj-summary-row"><strong>' + esc(labels[k] || k) + ':</strong> ' + esc(fields[k]) + '</div>';
      }
      return '<div class="hj-summary"><div class="hj-summary-title">Your Information</div>' + rows +
        '<button class="hj-summary-edit" id="hj-summary-edit">Edit details</button></div>';
    }

    function displayEmergencyBanner() {
      if (emergencyDetected) return;
      emergencyDetected = true;
      var el = document.createElement('div');
      el.className = 'hj-emergency';
      el.innerHTML =
        '<div class="hj-emergency-icon">&#128680;</div>' +
        '<div class="hj-emergency-title">Emergency Detected</div>' +
        '<div class="hj-emergency-body">We\'ve noted this as urgent. For immediate assistance, please call us directly at the number on our website. We\'ll prioritize your request.</div>';
      appendRaw(el);
    }

    function onConversationMessage(text) {
      if (submitted) return;
      if (!text || !text.trim()) return;

      hideTyping();
      appendBubble(esc(text), true);

      // Detect emergency
      if (isEmergency(text)) {
        displayEmergencyBanner();
      }

      // Merge client-side extracted fields
      mergeFields(text);

      // Send to backend
      var typingTimer = setTimeout(function () { showTyping(); }, 400);
      sendMessage(text).then(function (data) {
        clearTimeout(typingTimer);
        hideTyping();
        if (!data) return;
        // Merge fields from backend
        if (data.fields) {
          var keys = Object.keys(data.fields);
          for (var i = 0; i < keys.length; i++) {
            if (data.fields[keys[i]]) fields[keys[i]] = data.fields[keys[i]];
          }
        }
        if (data.reply) {
          appendBubble(esc(data.reply));
        }
        if (data.state === 'submitted' || data.state === 'complete') {
          markSubmitted();
        }
        if (data.state === 'handoff') {
          appendBubble(esc(data.reply || "Thank you! A team member will be with you shortly."));
        }
      }).catch(function (err) {
        clearTimeout(typingTimer);
        hideTyping();
        errorCount++;
        if (errorCount >= 3) {
          showOffline();
        } else {
          // Client-side fallback: ask next question
          var q = getNextQuestion();
          if (q) {
            setTimeout(function () { appendBubble(esc(q)); }, 300);
          } else {
            showError('Connection issue. Please try again or call us directly.');
          }
        }
      });
    }

    function markSubmitted() {
      submitted = true;
      setDisabled(true);
      // Show success confirmation
      hideTyping();
      setTimeout(function () {
        body.innerHTML = '';
        var el = document.createElement('div');
        el.className = 'hj-success';
        var tenant = config && config.tenant_name ? config.tenant_name : 'us';
        el.innerHTML =
          '<div class="hj-success-icon">&#9989;</div>' +
          '<div class="hj-success-title">Message Sent!</div>' +
          '<div class="hj-success-body">Thank you for reaching out to ' + esc(tenant) + '. ' +
          'We\'ll get back to you shortly. Have a great day!</div>';
        body.appendChild(el);
        launcherLabel.textContent = 'Sent';
      }, 600);
    }

    // ── Form Mode ────────────────────────────────────────────────────────────
    function buildForm() {
      formBody.innerHTML = '';
      if (submitted) {
        formBody.innerHTML =
          '<div class="hj-success"><div class="hj-success-icon">&#9989;</div>' +
          '<div class="hj-success-title">Message Sent!</div>' +
          '<div class="hj-success-body">Thank you! We\'ll be in touch shortly.</div></div>';
        return;
      }

      var container = document.createElement('div');
      container.className = 'hj-form';

      var fields_ = [
        { key: 'name', label: 'Full Name *', type: 'text', placeholder: 'Your full name' },
        { key: 'email', label: 'Email Address *', type: 'email', placeholder: 'you@example.com' },
        { key: 'phone', label: 'Phone Number', type: 'tel', placeholder: '(555) 123-4567' },
        { key: 'service', label: 'Service / Intent', type: 'select', options: ['','Checkup','Cleaning','Emergency','Consultation','Cosmetic','Implants','Orthodontics','Restorative','Extraction','Other'] },
        { key: 'preferred_date', label: 'Preferred Date', type: 'text', placeholder: 'e.g. next Monday, 1/15/2025' },
        { key: 'preferred_time', label: 'Preferred Time', type: 'text', placeholder: 'e.g. morning, 2:30 PM' },
        { key: 'message', label: 'Message', type: 'textarea', placeholder: 'Tell us more about what you need...' },
      ];

      for (var i = 0; i < fields_.length; i++) {
        var f = fields_[i];
        var wrapper = document.createElement('div');
        wrapper.className = 'hj-field';

        var label = document.createElement('label');
        label.textContent = f.label;
        label.setAttribute('for', 'hj-f-' + f.key);
        wrapper.appendChild(label);

        if (f.type === 'textarea') {
          var ta = document.createElement('textarea');
          ta.id = 'hj-f-' + f.key;
          ta.name = f.key;
          ta.placeholder = f.placeholder || '';
          ta.maxLength = 2000;
          ta.rows = 3;
          if (fields[f.key]) ta.value = fields[f.key];
          wrapper.appendChild(ta);
        } else if (f.type === 'select') {
          var sel = document.createElement('select');
          sel.id = 'hj-f-' + f.key;
          sel.name = f.key;
          for (var j = 0; j < f.options.length; j++) {
            var opt = document.createElement('option');
            opt.value = f.options[j];
            opt.textContent = f.options[j] || '-- Select --';
            if (fields[f.key] === f.options[j]) opt.selected = true;
            sel.appendChild(opt);
          }
          wrapper.appendChild(sel);
        } else {
          var inp = document.createElement('input');
          inp.id = 'hj-f-' + f.key;
          inp.type = f.type;
          inp.name = f.key;
          inp.placeholder = f.placeholder || '';
          inp.maxLength = 200;
          if (fields[f.key]) inp.value = fields[f.key];
          wrapper.appendChild(inp);
        }

        container.appendChild(wrapper);
      }

      // Submit button
      var actions = document.createElement('div');
      actions.className = 'hj-form-actions';
      var submitBtn = document.createElement('button');
      submitBtn.className = 'hj-submit-btn';
      submitBtn.textContent = 'Send Message';
      submitBtn.id = 'hj-form-submit';
      submitBtn.addEventListener('click', onSubmitForm);
      actions.appendChild(submitBtn);
      container.appendChild(actions);

      formBody.appendChild(container);
      scrollFormToBottom();
    }

    function onSubmitForm() {
      if (isSubmitting || submitted) return;
      isSubmitting = true;
      var btn = formPanel.querySelector('#hj-form-submit');
      if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }

      // Collect form values
      var inputs = formPanel.querySelectorAll('input, select, textarea');
      fields = {};
      for (var i = 0; i < inputs.length; i++) {
        var el = inputs[i];
        if (el.name && el.value && el.value.trim()) {
          fields[el.name] = el.value.trim();
        }
      }

      // Detect emergency from message field
      if (fields.message && isEmergency(fields.message)) {
        emergencyDetected = true;
      }

      submitFields().then(function (data) {
        isSubmitting = false;
        if (data && (data.state === 'submitted' || data.state === 'complete')) {
          markSubmitted();
        } else {
          if (btn) { btn.disabled = false; btn.textContent = 'Send Message'; }
          showError('Something went wrong. Please try again.');
        }
      }).catch(function () {
        isSubmitting = false;
        if (btn) { btn.disabled = false; btn.textContent = 'Send Message'; }
        if (errorCount >= 3) {
          showOffline();
        } else {
          showError('Connection issue. Please try again or call us directly.');
        }
      });
    }

    function submitFields() {
      var msg = fields.message || 'Form submission';
      if (!conversationId) {
        return startConversation().then(function () {
          return sendMessage(msg);
        });
      }
      return sendMessage(msg);
    }

    // ── API ──────────────────────────────────────────────────────────────────
    function api(path, options) {
      if (!apiBase) return Promise.reject(new Error('No API base'));
      var opts = options || {};
      return fetch(apiBase + path, {
        method: opts.method || 'GET',
        headers: { 'Content-Type': 'application/json' },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      }).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
    }

    function loadConfig() {
      return api('/api/v1/public/config?client_key=' + encodeURIComponent(clientKey))
        .then(function (c) {
          config = c;
          if (c.tenant_name) titleEl.textContent = c.tenant_name + ' — Concierge';
          if (c.greeting) fields._greeting = c.greeting;
          if (c.greeting) {
            appendBubble(esc(c.greeting));
          }
          // If config specifies form mode
          if (c.form_mode === true || c.form_mode === 'true') {
            switchToForm();
          }
          return c;
        });
    }

    function startConversation() {
      return api('/api/v1/public/conversations?client_key=' + encodeURIComponent(clientKey), {
        method: 'POST',
        body: {},
      }).then(function (data) {
        conversationId = data.conversation_id;
        conversationState = data.state || 'started';
        if (data.fields) {
          var keys = Object.keys(data.fields);
          for (var i = 0; i < keys.length; i++) {
            if (data.fields[keys[i]]) fields[keys[i]] = data.fields[keys[i]];
          }
        }
        if (data.reply) {
          appendBubble(esc(data.reply));
        }
        return data;
      });
    }

    function sendMessage(text) {
      if (!text || !conversationId) return Promise.resolve({});
      return api('/api/v1/public/conversations/' + conversationId + '/messages?client_key=' + encodeURIComponent(clientKey), {
        method: 'POST',
        body: { message: text },
      }).then(function (data) {
        conversationState = data.state || conversationState;
        if (data.fields) {
          var keys = Object.keys(data.fields);
          for (var i = 0; i < keys.length; i++) {
            if (data.fields[keys[i]]) fields[keys[i]] = data.fields[keys[i]];
          }
        }
        return data;
      });
    }

    // ── Open / Close ─────────────────────────────────────────────────────────
    function openWidget() {
      isOpen = true;
      frame.classList.add('open');
      unreadCount = 0;
      updateBadge();
      updateModeToggle();
      msgInput.focus();

      if (!started) {
        started = true;
        initSession();
      }
    }

    function initSession() {
      setLoading(true);
      showTyping();
      loadConfig().then(function () {
        hideTyping();
        setLoading(false);
        return startConversation();
      }).then(function (data) {
        hideTyping();
        if (!data || !data.reply) {
          // If backend didn't give a reply, start conversational flow
          var q = getNextQuestion();
          if (q) {
            setTimeout(function () { appendBubble(esc(q)); }, 350);
          }
        }
        if (isFormActive) {
          buildForm();
        }
      }).catch(function () {
        hideTyping();
        setLoading(false);
        showOffline();
        if (isFormActive) {
          buildForm();
        }
      });
    }

    function closeWidget() {
      isOpen = false;
      frame.classList.remove('open');
    }

    function switchToForm() {
      isFormActive = true;
      chatPanel.classList.remove('active');
      formPanel.classList.add('active');
      document.getElementById('hj-input-area').style.display = 'none';
      modeToggle.textContent = 'Chat';
      updateModeToggle();
      buildForm();
    }

    function switchToChat() {
      isFormActive = false;
      formPanel.classList.remove('active');
      chatPanel.classList.add('active');
      document.getElementById('hj-input-area').style.display = '';
      modeToggle.textContent = 'Form';
      updateModeToggle();
      // If no messages yet and we have fields, ask next question
      if (body.children.length === 0) {
        var q = getNextQuestion();
        if (q) appendBubble(esc(q));
      }
    }

    // ── Event Listeners ──────────────────────────────────────────────────────
    openBtn.addEventListener('click', openWidget);
    closeBtn.addEventListener('click', closeWidget);

    modeToggle.addEventListener('click', function () {
      if (isFormActive) {
        switchToChat();
      } else {
        switchToForm();
      }
    });

    sendBtn.addEventListener('click', function () {
      var text = msgInput.value.trim();
      if (!text || isSubmitting) return;
      onConversationMessage(text);
      msgInput.value = '';
      msgInput.focus();
    });

    msgInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendBtn.click();
      }
    });

    // Summary edit button
    body.addEventListener('click', function (e) {
      if (e.target.id === 'hj-summary-edit') {
        if (isFormActive) return;
        switchToForm();
      }
    });

    // ── Auto-open ────────────────────────────────────────────────────────────
    var autoOpen = (script.getAttribute('data-heyjarvis-auto-open') || '').toLowerCase();
    if (autoOpen === 'true' || autoOpen === '1') {
      setTimeout(openWidget, 500);
    }

    // ── Error boundary ───────────────────────────────────────────────────────
  } catch (e) {
    if (window.console) console.error('HeyJarvis widget error:', e);
  }
})();
