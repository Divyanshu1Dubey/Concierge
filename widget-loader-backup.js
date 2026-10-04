/* HeyJarvis Concierge - Production-Ready Dental Widget
 *
 * Embed on any site:
 *   <script async src="https://YOUR-HOST/widget.js"><\/script>
 *
 * Features:
 * - Matches exact site design ("Plan your visit" style)
 * - AI-powered appointment booking conversation
 * - Form collection as fallback
 * - Local API: /public/requests
 * - Floating launcher + panel
 * - Accessible, responsive, mobile-friendly
 */
(function () {
  'use strict';
  try {
    console.log('[HeyJarvis Widget] IIFE starting');
    var script = document.currentScript;
    if (!script) {
      var scripts = document.querySelectorAll('script[src*="widget-loader.js"]');
      if (scripts.length > 0) script = scripts[scripts.length - 1];
      console.log('[HeyJarvis Widget] Found script via querySelector:', script ? 'yes' : 'no');
    }
    if (!script) {
      console.log('[HeyJarvis Widget] No script found, returning');
      return;
    }

    var apiBase = (script.getAttribute('data-heyjarvis-api') || '')
      || (script.getAttribute('src') || '').replace(/\/widget\.js\/?$/, '');
    if (!apiBase || apiBase.indexOf('file:') === 0 || apiBase === 'widget-loader.js') {
      apiBase = 'http://localhost:8000';
    }
    console.log('[HeyJarvis Widget] apiBase:', apiBase);
    if (!apiBase) return;

    var STATE = { CLOSED: 'closed', OPEN: 'open', CHAT: 'chat', FORM: 'form', SENDING: 'sending', SENT: 'sent' };
    var mode = STATE.CLOSED;
    var conversationId = null;
    var collected = {};
    var conversationHistory = [];
    var currentStep = 'greeting';
    var selectedService = null;
    var selectedCategory = null;

    // Exact site colors/matching
    var THEME = {
      ink: '#263d39',
      panel: '#fbfcf8f5',
      heading: '#e7eddf',
      bubble: '#edf1e7',
      bubbleUser: '#304b40',
      userText: '#ffffff',
      botText: '#304b40',
      border: '#dce3d6',
      button: '#263d39',
      buttonText: '#ffffff',
      inputBorder: '#82977c',
      disclosure: '#657265',
      launcherBg: '#263d39',
      launcherText: '#ffffff',
      launcherOpenBg: '#e1e9da',
      launcherOpenText: '#263d39'
    };

    var css =
      '#hj-launcher{position:fixed;right:26px;bottom:25px;z-index:99999;border:1px solid rgba(255,255,255,0.44);border-radius:100px;display:flex;gap:12px;align-items:center;background:' + THEME.launcherBg + ';color:' + THEME.launcherText + ';padding:14px 22px;box-shadow:0 8px 35px rgba(24,43,48,0.19);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;cursor:pointer;transition:background .15s,color .15s,transform .15s}' +
      '#hj-launcher:hover{transform:translateY(-1px)}' +
      '#hj-symbol{font-size:24px;line-height:1}' +
      '#hj-panel{position:fixed;right:26px;bottom:96px;z-index:100000;width:390px;max-width:calc(100vw - 32px);height:570px;max-height:calc(100dvh - 130px);background:' + THEME.panel + ';backdrop-filter:blur(25px);border:1px solid rgba(255,255,255,0.9);border-radius:26px;box-shadow:0 18px 70px rgba(30,52,46,0.19);display:flex;flex-direction:column;overflow:hidden}' +
      '#hj-panel[hidden]{display:none}' +
      '#hj-header{padding:20px 22px;background:' + THEME.heading + ';display:flex;align-items:center;justify-content:space-between;gap:15px;border-bottom:1px solid ' + THEME.border + '}' +
      '#hj-header strong{display:block;font-size:17px;font-weight:500;color:' + THEME.ink + '}' +
      '#hj-header span{display:block;font-size:13px;color:' + THEME.disclosure + '}' +
      '#hj-close{background:none;border:0;font-size:28px;line-height:1;padding:8px;cursor:pointer;color:' + THEME.ink + '}' +
      '#hj-thread{flex:1;min-height:80px;overflow-y:auto;overscroll-behavior:contain;padding:22px 18px 12px;display:flex;flex-direction:column;gap:12px}' +
      '.hj-bubble{max-width:93%;padding:13px 16px;background:' + THEME.bubble + ';border-radius:17px 17px 17px 4px;color:' + THEME.botText + ';font-size:15px;line-height:1.55;white-space:pre-line;flex-shrink:0}' +
      '.hj-bubble.user{background:' + THEME.bubbleUser + ';color:' + THEME.userText + ';align-self:flex-end;border-radius:17px 17px 4px 17px}' +
      '.hj-bubble.sys{background:rgba(255,255,255,0.7);border:1px solid ' + THEME.border + ';align-self:center;text-align:center;font-size:13px;border-radius:10px;padding:8px 12px;color:' + THEME.disclosure + '}' +
      '.hj-options{display:flex;gap:8px;flex-wrap:wrap;padding:8px 18px 15px}' +
      '.hj-options button,.hj-options a{border:1px solid ' + THEME.border + ';border-radius:18px;padding:9px 13px;font-size:14px;background:#fff;color:' + THEME.ink + ';line-height:1.35;cursor:pointer;font-family:inherit}' +
      '.hj-options button:hover,.hj-options a:hover{background:' + THEME.heading + '}' +
      '#hj-form{border-top:1px solid ' + THEME.border + ';display:flex;flex-direction:column;gap:10px;padding:14px 16px}' +
      '#hj-form[hidden]{display:none}' +
      '.hj-field{display:flex;flex-direction:column;gap:4px}' +
      '.hj-field label{font-size:13px;font-weight:600;color:' + THEME.ink + '}' +
      '.hj-field input,.hj-field textarea,.hj-field select{font:16px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:10px 4px;background:transparent;border:0;border-bottom:1.5px solid ' + THEME.border + ';color:' + THEME.ink + ';outline:none;transition:border-color .15s}' +
      '.hj-field input:focus,.hj-field textarea:focus,.hj-field select:focus{border-bottom-color:' + THEME.inputBorder + ';outline:1px solid ' + THEME.inputBorder + ';outline-offset:2px;border-radius:5px}' +
      '.hj-field textarea{resize:vertical;min-height:70px}' +
      '.hj-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}' +
      '#hj-submit{border:0;border-radius:13px;background:' + THEME.button + ';color:' + THEME.buttonText + ';padding:10px 15px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}' +
      '#hj-submit:disabled{opacity:.55;cursor:not-allowed}' +
      '#hj-disclosure{font-size:12px;line-height:1.45;text-align:center;padding:0 14px 14px;color:' + THEME.disclosure + '}' +
      '.hj-typing{display:flex;gap:4px;padding:6px 0}' +
      '.hj-typing span{width:7px;height:7px;border-radius:50%;background:#9ca3af;animation:hj-bounce .6s infinite alternate}' +
      '.hj-typing span:nth-child(2){animation-delay:.15s}' +
      '.hj-typing span:nth-child(3){animation-delay:.3s}' +
      '@keyframes hj-bounce{from{transform:translateY(0)}to{transform:translateY(-4px)}}' +
      '@media(max-width:800px){#hj-launcher{right:16px;bottom:16px;padding:13px 18px}#hj-panel{right:16px;bottom:85px;max-height:calc(100dvh - 104px);height:565px}}';

    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    var launcher = document.createElement('div');
    launcher.id = 'hj-launcher';
    launcher.setAttribute('role', 'button');
    launcher.setAttribute('aria-expanded', 'false');
    launcher.setAttribute('tabindex', '0');
    launcher.innerHTML =
      '<span id="hj-symbol" aria-hidden="true">✺</span>' +
      '<span>Plan your visit</span>';
    document.body.appendChild(launcher);

    var panel = document.createElement('section');
    panel.id = 'hj-panel';
    panel.className = 'chat-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Appointment assistant');
    panel.hidden = true;
    panel.innerHTML =
      '<div id="hj-header"><div><strong>Raleigh Dentistry</strong><span>Appointment assistant</span></div><button id="hj-close" type="button" aria-label="Close appointment assistant">✕</button></div>' +
      '<div id="hj-thread" role="log" aria-live="polite" aria-relevant="additions"></div>' +
      '<div id="hj-options" class="hj-options"></div>' +
      '<form id="hj-form" novalidate hidden>' +
        '<div class="hj-field"><label for="hj-name">Full name</label><input id="hj-name" autocomplete="name" required></div>' +
        '<div class="hj-row">' +
          '<div class="hj-field"><label for="hj-email">Email</label><input id="hj-email" type="email" autocomplete="email" required></div>' +
          '<div class="hj-field"><label for="hj-phone">Phone</label><input id="hj-phone" type="tel" autocomplete="tel"></div>' +
        '</div>' +
        '<div class="hj-field"><label for="hj-service">Service interest</label><select id="hj-service"><option value="">Select a service</option><option>New patient</option><option>Cleaning & exam</option><option>Emergency</option><option>Restorative care</option><option>Cosmetic care</option><option>Other</option></select></div>' +
        '<div class="hj-field"><label for="hj-message">Tell us more</label><textarea id="hj-message" maxlength="10000"></textarea></div>' +
        '<button id="hj-submit" type="submit">Request appointment</button>' +
      '</form>' +
      '<p id="hj-disclosure">Guided assistance  -  Our team confirms appointments.<br>Please don’t share private medical information here.</p>';
    document.body.appendChild(panel);

    var launcherBtn = document.getElementById('hj-launcher');
    var closeBtn = document.getElementById('hj-close');
    var thread = document.getElementById('hj-thread');
    var optionsEl = document.getElementById('hj-options');
    var formEl = document.getElementById('hj-form');
    var submitBtn = document.getElementById('hj-submit');
    var nameEl = document.getElementById('hj-name');
    var emailEl = document.getElementById('hj-email');
    var phoneEl = document.getElementById('hj-phone');
    var serviceEl = document.getElementById('hj-service');
    var messageEl = document.getElementById('hj-message');

    function esc(str) {
      if (str == null) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function bubble(html, type) {
      console.log('[HeyJarvis Widget] bubble called:', html.substring(0, 50));
      if (!thread) {
        console.log('[HeyJarvis Widget] ERROR: thread is null!');
        return;
      }
      var el = document.createElement('div');
      el.className = 'hj-bubble ' + (type || 'bot');
      el.innerHTML = html;
      thread.appendChild(el);
      thread.scrollTop = thread.scrollHeight;
      conversationHistory.push({ from: type || 'bot', html: html });
    }

    function sysMsg(text) { bubble(esc(text), 'sys'); }

    function showTyping() {
      var el = document.createElement('div');
      el.className = 'hj-typing';
      el.id = 'hj-typing';
      el.innerHTML = '<span></span><span></span><span></span>';
      thread.appendChild(el);
      thread.scrollTop = thread.scrollHeight;
    }

    function hideTyping() {
      var el = document.getElementById('hj-typing');
      if (el) el.remove();
    }

    function setDisabled(disabled) {
      [nameEl, emailEl, phoneEl, serviceEl, messageEl, submitBtn].forEach(function (el) { el.disabled = disabled; });
    }

    function openPanel() {
      console.log('[HeyJarvis Widget] openPanel called, conversationId:', conversationId);
      panel.hidden = false;
      launcherBtn.setAttribute('aria-expanded', 'true');
      mode = STATE.OPEN;
      if (!conversationId) {
        console.log('[HeyJarvis Widget] starting conversation');
        startConversation();
      } else {
        console.log('[HeyJarvis Widget] conversation already started');
      }
    }

    function closePanel() {
      panel.hidden = true;
      launcherBtn.setAttribute('aria-expanded', 'false');
      mode = STATE.CLOSED;
      // Reset so reopening shows greeting fresh
      conversationId = null;
      collected = {};
      conversationHistory = [];
      currentStep = 'greeting';
      selectedService = null;
      selectedCategory = null;
      thread.innerHTML = '';
      optionsEl.innerHTML = '';
      formEl.hidden = true;
      optionsEl.hidden = true;
    }

    console.log('[HeyJarvis Widget] Adding event listeners');
    launcherBtn.addEventListener('click', function(e) {
      console.log('[HeyJarvis Widget] launcher clicked');
      openPanel();
    });
    launcherBtn.addEventListener('keydown', function (e) {
      console.log('[HeyJarvis Widget] launcher keydown:', e.key);
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPanel(); }
    });
    closeBtn.addEventListener('click', function(e) {
      console.log('[HeyJarvis Widget] close clicked');
      closePanel();
    });
    console.log('[HeyJarvis Widget] Event listeners added, initialization complete');

    function api(path, options) {
      var base = apiBase.replace(/\/$/, '');
      var url = base + '/api/v1' + path;
      console.log('[HeyJarvis Widget] API call:', url);
      return fetch(url, {
        method: options && options.method || 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        body: options && options.body ? JSON.stringify(options.body) : undefined,
      }).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status + ':' + url);
        return r.json();
      });
    }

    function startConversation() {
      console.log('[HeyJarvis Widget] startConversation called');
      return api('/public/conversations', { method: 'POST', body: { source: 'website:' + location.hostname, message: 'Conversation started from website widget.' } })
        .then(function (data) {
          console.log('[HeyJarvis Widget] API response:', data);
          conversationId = data.conversation_id || ('local-' + Date.now());
          console.log('[HeyJarvis Widget] conversationId set:', conversationId);
          startGreeting();
          return data;
        })
        .catch(function (err) {
          console.log('[HeyJarvis Widget] API error:', err);
          conversationId = 'local-' + Date.now();
          console.log('[HeyJarvis Widget] using local conversationId:', conversationId);
          startGreeting();
        });
    }

    function startGreeting() {
      console.log('[HeyJarvis Widget] startGreeting called');
      bubble('Hi! Welcome to Raleigh Dentistry. How can we help you today?', 'bot');
      console.log('[HeyJarvis Widget] bubble added');
      showOptions([
        { label: '🦷 New patient appointment', value: 'new_patient' },
        { label: '✨ Routine cleaning', value: 'cleaning' },
        { label: '🚨 Emergency visit', value: 'emergency' },
        { label: '📅 Reschedule / cancel', value: 'reschedule' },
        { label: '💬 Question about care', value: 'question' }
      ]);
      console.log('[HeyJarvis Widget] options shown');
      currentStep = 'intent';
    }

    function showOptions(items) {
      optionsEl.innerHTML = '';
      items.forEach(function (item) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = item.label;
        btn.addEventListener('click', function () {
          optionsEl.innerHTML = '';
          bubble(item.label, 'user');
          handleIntent(item.value);
        });
        optionsEl.appendChild(btn);
      });
    }

    function handleIntent(value) {
      selectedService = value;
      collected.service = value;
      if (value === 'emergency') collected.urgency = 'emergency';

      var reply = 'Great choice.';
      if (value === 'new_patient') reply += ' For new patients, please share your name and best contact info so our front desk can confirm a time.';
      else if (value === 'cleaning') reply += ' For cleanings, please share your preferred day and time window, like weekday morning.';
      else if (value === 'emergency') reply += ' For emergencies, we try to see patients the same day when possible. Please tell me what you’re experiencing.';
      else if (value === 'reschedule') reply += ' I can help with that. Please tell me your current appointment day and preferred new time.';
      else reply += ' I’ll pass this along. Please add any details below.';

      bubble(reply, 'bot');
      setTimeout(openForm, 350);
      currentStep = 'collecting';
    }

    function openForm() {
      optionsEl.innerHTML = '';
      formEl.hidden = false;
      setDisabled(false);
      nameEl.focus();
    }

    function normalizeLead() {
      collected.name = (nameEl.value || '').trim();
      collected.email = (emailEl.value || '').trim();
      collected.phone = (phoneEl.value || '').trim();
      collected.service = serviceEl.value || collected.service;
      collected.message = (messageEl.value || '').trim();
      collected.source = 'website:' + location.hostname;
      collected.pageUrl = location.href;
      collected.referrer = document.referrer || '';
      collected.userAgent = navigator.userAgent || '';
      collected.createdAt = new Date().toISOString();
      collected.status = 'new';
      collected.urgency = collected.urgency || 'normal';
      collected.tenantId = collected.tenantId || 'raleigh';
      collected.conversationId = conversationId;
      collected.conversationSummary = buildSummary();
      return collected;
    }

    function buildSummary() {
      var lines = [];
      if (collected.name) lines.push('Name: ' + collected.name);
      if (collected.email) lines.push('Email: ' + collected.email);
      if (collected.phone) lines.push('Phone: ' + collected.phone);
      if (collected.service) lines.push('Interest: ' + collected.service);
      if (collected.urgency) lines.push('Urgency: ' + collected.urgency);
      if (collected.message) lines.push('Details: ' + collected.message);
      return lines.join('\n') || 'Website appointment request';
    }

    function submitForm() {
      if (mode === STATE.SENDING) return;
      var data = normalizeLead();
      if (!data.name || !data.email || !data.message) {
        sysMsg('Please enter your name, email, and a brief message.');
        return;
      }

      mode = STATE.SENDING;
      setDisabled(true);
      submitBtn.disabled = true;
      submitBtn.textContent = 'Sending…';
      sysMsg('Sending your request to the front desk…');
      showTyping();

      api('/public/conversations/' + conversationId + '/messages', { method: 'POST', body: { message: buildSummary(), lead: data } })
        .then(function (res) {
          hideTyping();
          sysMsg('Thanks! Our front desk will email you shortly with a time.');
          formEl.reset();
          formEl.hidden = true;
          mode = STATE.SENT;
          setTimeout(closePanel, 2400);
        })
        .catch(function () {
          hideTyping();
          sysMsg('Sorry, that didn’t go through. Please call the office or try again.');
          mode = STATE.OPEN;
          setDisabled(false);
          submitBtn.disabled = false;
          submitBtn.textContent = 'Request appointment';
        });
    }

    formEl.addEventListener('submit', function (e) {
      e.preventDefault();
      submitForm();
    });
  } catch (e) {
    console.error('[HeyJarvis] Widget failed to init:', e);
  }
})();
