/*!
 * HeyJarvis Concierge website widget v3
 * Embed:
 *   <script async src="https://YOUR-CONCIERGE-DOMAIN/widget.js"
 *           data-api-url="https://YOUR-CONCIERGE-DOMAIN"
 *           data-heyjarvis-client="YOUR_CLIENT_KEY"></script>
 * Optional: data-position="left|right", data-color="#hex", data-label="Book a visit", data-open="true"
 */
(function () {
  'use strict';
  if (window.__heyjarvisWidget) return;
  window.__heyjarvisWidget = true;

  var VERSION = '3.0.0';
  var REQUEST_TIMEOUT_MS = 30000;

  // ── Configuration from the script tag ────────────────────────────────────
  var script = document.currentScript ||
    document.querySelector('script[data-heyjarvis-client], script[data-client-key], script[data-practice]');
  function attr(name) { return (script && script.getAttribute(name)) || ''; }
  function originOf(src) {
    try { var u = new URL(src, window.location.href); return /^https?:$/.test(u.protocol) ? u.origin : ''; } catch (e) { return ''; }
  }
  var cfg = {
    clientKey: attr('data-heyjarvis-client') || attr('data-client-key'),
    slug: attr('data-practice'),
    // The API is wherever data-api-url says, else the server the script came from. Never guessed.
    apiUrl: (attr('data-api-url') || originOf(script && script.src) ||
             (/^https?:$/.test(window.location.protocol) ? window.location.origin : '')).replace(/\/+$/, ''),
    position: attr('data-position'),
    color: attr('data-color'),
    label: attr('data-label') || 'Book a visit',
    autoOpen: attr('data-open') === 'true'
  };

  // ── Small helpers ────────────────────────────────────────────────────────
  function store(kind) { try { return window[kind]; } catch (e) { return null; } }
  function getItem(kind, key) { try { var s = store(kind); return s ? s.getItem(key) : null; } catch (e) { return null; } }
  function setItem(kind, key, val) { try { var s = store(kind); if (s) s.setItem(key, val); } catch (e) { /* storage blocked */ } }
  function removeItem(kind, key) { try { var s = store(kind); if (s) s.removeItem(key); } catch (e) { /* ignore */ } }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function rich(text) {
    return esc(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
  }
  function validHex(c) { return /^#([0-9a-f]{3}){1,2}$/i.test(c || '') ? c : ''; }
  function textOn(hex) {
    var h = hex.replace('#', ''); if (h.length === 3) h = h.replace(/(.)/g, '$1$1');
    var r = parseInt(h.substr(0, 2), 16), g = parseInt(h.substr(2, 2), 16), b = parseInt(h.substr(4, 2), 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.62 ? '#111827' : '#ffffff';
  }
  function newId() { return 'hj_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36); }

  var keyBase = 'hj_widget_' + (cfg.clientKey ? cfg.clientKey.slice(0, 12) : (cfg.slug || 'default'));
  var state = {
    brand: null,            // practice config from the server
    configError: null,
    sessionId: getItem('localStorage', keyBase + '_session') || newId(),
    conversationId: getItem('localStorage', keyBase + '_conv') || '',
    transcript: [],
    started: false,
    initPromise: null,
    sending: false,
    complete: false,
    open: false,
    lastFailed: null
  };
  setItem('localStorage', keyBase + '_session', state.sessionId);
  try { state.transcript = JSON.parse(getItem('localStorage', keyBase + '_log') || '[]') || []; } catch (e) { state.transcript = []; }
  state.complete = getItem('localStorage', keyBase + '_done') === '1';
  function persist() {
    setItem('localStorage', keyBase + '_conv', state.conversationId || '');
    setItem('localStorage', keyBase + '_log', JSON.stringify(state.transcript.slice(-60)));
    setItem('localStorage', keyBase + '_done', state.complete ? '1' : '0');
  }

  // ── API (no custom headers: only Content-Type, so CORS works on any website) ─
  function friendlyError(err) {
    var name = (state.brand && state.brand.practice_name) || 'the practice';
    if (!err || err.status === 0) {
      return navigator.onLine === false ? 'You appear to be offline. Check your connection and try again.'
        : 'We could not reach ' + name + '. Please try again in a moment.';
    }
    if (err.status === 403) return 'Chat is not enabled for this website yet. Please call ' + name + ' directly.';
    if (err.status === 404) return 'This chat is not available right now. Please call ' + name + ' directly.';
    if (err.status === 429) return 'You are sending messages too quickly. Please wait a moment and try again.';
    if (err.status === 408) return 'This is taking longer than usual. Please try again.';
    return 'Something went wrong on our side. Please try again.';
  }
  function api(path, body) {
    if (!cfg.apiUrl) return Promise.reject({ status: 0, config: true });
    var isGet = !body;
    var params = [];
    if (cfg.clientKey) params.push('client_key=' + encodeURIComponent(cfg.clientKey));
    else if (cfg.slug) params.push('practice_slug=' + encodeURIComponent(cfg.slug));
    var url = cfg.apiUrl + path + (isGet && params.length ? '?' + params.join('&') : '');
    var payload = null;
    if (!isGet) {
      payload = {};
      for (var k in body) if (Object.prototype.hasOwnProperty.call(body, k)) payload[k] = body[k];
      if (cfg.clientKey) payload.client_key = cfg.clientKey;
      if (cfg.slug) payload.practice_slug = cfg.slug;
    }
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, REQUEST_TIMEOUT_MS) : null;
    return fetch(url, {
      method: isGet ? 'GET' : 'POST',
      headers: isGet ? undefined : { 'Content-Type': 'application/json' },
      body: payload ? JSON.stringify(payload) : undefined,
      credentials: 'omit',
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (res) {
      if (timer) clearTimeout(timer);
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw { status: res.status, data: data };
        return data;
      });
    }, function (e) {
      if (timer) clearTimeout(timer);
      throw { status: e && e.name === 'AbortError' ? 408 : 0 };
    });
  }

  // ── Styles (inside a shadow root, so the host page cannot affect them) ─────
  var CSS = [
    ':host{all:initial}',
    '[hidden]{display:none!important}',
    '*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}',
    '.wrap{position:fixed;bottom:20px;z-index:2147483000;display:flex;flex-direction:column;align-items:flex-end;gap:12px}',
    '.wrap.left{align-items:flex-start}',
    '.launcher{display:flex;align-items:center;gap:10px;border:0;cursor:pointer;background:var(--c);color:var(--ct);height:56px;padding:0 20px 0 16px;border-radius:999px;box-shadow:0 10px 30px -8px rgba(15,23,42,.45);font-size:15px;font-weight:600;transition:transform .18s ease,box-shadow .18s ease}',
    '.launcher:hover{transform:translateY(-1px);box-shadow:0 14px 34px -8px rgba(15,23,42,.5)}',
    '.launcher:focus-visible,button:focus-visible,a:focus-visible,textarea:focus-visible{outline:3px solid rgba(37,99,235,.55);outline-offset:2px}',
    '.launcher svg{width:22px;height:22px;flex-shrink:0}',
    '.launcher.icon-only{width:56px;padding:0;justify-content:center}',
    '.badge{position:absolute;top:-2px;right:-2px;width:14px;height:14px;border-radius:50%;background:#ef4444;border:2px solid #fff}',
    '.teaser{max-width:260px;background:#fff;color:#1f2937;border-radius:14px;padding:12px 34px 12px 14px;font-size:14px;line-height:1.45;box-shadow:0 12px 30px -10px rgba(15,23,42,.35);position:relative;cursor:pointer;animation:rise .3s ease both}',
    '.teaser strong{display:block;color:#111827;margin-bottom:2px}',
    '.teaser button{position:absolute;top:6px;right:6px;width:22px;height:22px;border:0;background:transparent;color:#9ca3af;cursor:pointer;font-size:16px;line-height:1;border-radius:6px}',
    '.panel{width:380px;height:min(640px,calc(100vh - 110px));background:#fff;border-radius:20px;box-shadow:0 24px 60px -12px rgba(15,23,42,.45),0 0 0 1px rgba(15,23,42,.06);display:flex;flex-direction:column;overflow:hidden;animation:rise .22s ease both}',
    '@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}',
    '.head{background:var(--c);color:var(--ct);padding:16px 14px 16px 18px;display:flex;align-items:center;gap:12px}',
    '.avatar{width:42px;height:42px;border-radius:12px;background:rgba(255,255,255,.18);display:flex;align-items:center;justify-content:center;font:600 18px Georgia,serif;flex-shrink:0}',
    '.dark .avatar{background:rgba(0,0,0,.08)}',
    '.who{min-width:0;flex:1}',
    '.who b{display:block;font-size:15px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.status{display:flex;align-items:center;gap:6px;font-size:12px;opacity:.9;margin-top:3px}',
    '.dot{width:8px;height:8px;border-radius:50%;background:#4ade80;box-shadow:0 0 0 2px rgba(255,255,255,.35)}',
    '.dot.off{background:#fbbf24}',
    '.hbtn{width:36px;height:36px;border-radius:10px;border:0;background:rgba(255,255,255,.14);color:inherit;display:flex;align-items:center;justify-content:center;cursor:pointer;text-decoration:none;flex-shrink:0}',
    '.dark .hbtn{background:rgba(0,0,0,.07)}',
    '.hbtn:hover{background:rgba(255,255,255,.24)}',
    '.hbtn svg{width:18px;height:18px}',
    '.body{flex:1;overflow-y:auto;padding:18px 16px 8px;background:#f7f7f5;scroll-behavior:smooth}',
    '.trust{display:flex;align-items:center;gap:8px;font-size:12px;color:#6b7280;background:#fff;border:1px solid #ecebe6;border-radius:12px;padding:9px 11px;margin-bottom:14px}',
    '.trust svg{width:16px;height:16px;color:#16a34a;flex-shrink:0}',
    '.row{display:flex;margin:0 0 10px}',
    '.row.me{justify-content:flex-end}',
    '.bubble{max-width:84%;padding:11px 14px;border-radius:16px;font-size:14.5px;line-height:1.5;word-wrap:break-word;overflow-wrap:anywhere}',
    '.them .bubble{background:#fff;color:#1f2937;border:1px solid #ecebe6;border-top-left-radius:6px}',
    '.me .bubble{background:var(--c);color:var(--ct);border-top-right-radius:6px}',
    '.meta{font-size:11px;color:#9ca3af;margin:-4px 2px 10px;text-align:right}',
    '.meta.fail{color:#b91c1c}',
    '.meta.fail button{border:0;background:none;color:#b91c1c;font-weight:600;text-decoration:underline;cursor:pointer;font-size:11px;padding:0;margin-left:4px}',
    '.chips{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 14px}',
    '.chip{border:1px solid var(--c);color:var(--c-ink);background:#fff;border-radius:999px;padding:8px 13px;font-size:13.5px;font-weight:500;cursor:pointer;transition:background .15s}',
    '.chip:hover{background:var(--c-soft)}',
    '.chip:disabled{opacity:.5;cursor:default}',
    '.typing{display:inline-flex;gap:4px;padding:14px 16px}',
    '.typing i{width:7px;height:7px;border-radius:50%;background:#9ca3af;animation:blink 1.2s infinite both}',
    '.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}',
    '@keyframes blink{0%,80%,100%{opacity:.25;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}',
    '.notice{display:flex;gap:10px;align-items:flex-start;background:#fef2f2;border:1px solid #fecaca;color:#991b1b;border-radius:12px;padding:11px 12px;font-size:13.5px;line-height:1.45;margin:4px 0 12px}',
    '.notice button{margin-top:6px;border:0;background:#991b1b;color:#fff;border-radius:8px;padding:6px 12px;font-size:13px;font-weight:600;cursor:pointer}',
    '.notice.info{background:#fffbeb;border-color:#fde68a;color:#92400e}',
    '.done{background:#fff;border:1px solid #d1fae5;border-radius:14px;padding:14px;margin:4px 0 12px;font-size:14px;color:#065f46;line-height:1.5}',
    '.done b{display:block;color:#064e3b;margin-bottom:2px}',
    '.done button{margin-top:10px;border:1px solid #a7f3d0;background:#ecfdf5;color:#065f46;border-radius:999px;padding:7px 13px;font-size:13px;font-weight:600;cursor:pointer}',
    '.skeleton{height:14px;border-radius:7px;background:linear-gradient(90deg,#eceae4,#f5f4f0,#eceae4);background-size:200% 100%;animation:shine 1.2s infinite;margin:8px 0}',
    '@keyframes shine{to{background-position:-200% 0}}',
    '.foot{border-top:1px solid #ecebe6;background:#fff;padding:10px 12px 8px}',
    '.compose{display:flex;align-items:flex-end;gap:8px;background:#f7f7f5;border:1px solid #e5e4de;border-radius:16px;padding:6px 6px 6px 14px}',
    '.compose:focus-within{border-color:var(--c);background:#fff}',
    'textarea{flex:1;border:0;background:transparent;resize:none;font-size:15px;line-height:1.4;max-height:96px;min-height:22px;padding:7px 0;color:#111827;outline:none}',
    'textarea:focus,textarea:focus-visible{outline:none}',
    '.send{width:38px;height:38px;border-radius:12px;border:0;background:var(--c);color:var(--ct);cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}',
    '.send:disabled{opacity:.4;cursor:default}',
    '.send svg{width:18px;height:18px}',
    '.fine{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:#9ca3af;margin-top:7px;padding:0 4px}',
    '.fine a{color:#6b7280;text-decoration:none;font-weight:600}',
    '.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}',
    '@media (max-width:520px){.wrap{bottom:16px}.wrap.right{right:16px!important}.wrap.left{left:16px!important}',
    '.wrap.is-open{inset:0;bottom:0;right:0!important;left:0!important;gap:0}',
    '.wrap.is-open .launcher,.wrap.is-open .teaser{display:none}',
    '.panel{width:100vw;height:100%;max-height:none;border-radius:0}',
    '.head{padding-top:calc(14px + env(safe-area-inset-top))}.foot{padding-bottom:calc(8px + env(safe-area-inset-bottom))}',
    '.launcher{height:54px}}',
    '@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}'
  ].join('\n');

  var ICON = {
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>'
  };

  // ── DOM ──────────────────────────────────────────────────────────────────
  var host = document.createElement('div');
  host.id = 'heyjarvis-widget';
  var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
  var el = {};

  function applyBrand() {
    var b = state.brand || {};
    var color = validHex(cfg.color) || validHex(b.primary_color) || '#1f4d3a';
    var ink = textOn(color);
    el.wrap.style.setProperty('--c', color);
    el.wrap.style.setProperty('--ct', ink);
    el.wrap.style.setProperty('--c-ink', ink === '#ffffff' ? color : '#111827');
    el.wrap.style.setProperty('--c-soft', color + '14');
    el.wrap.classList.toggle('dark', ink !== '#ffffff');
    var left = (cfg.position || b.position) === 'left';
    el.wrap.classList.toggle('left', left);
    el.wrap.classList.toggle('right', !left);
    el.wrap.style[left ? 'left' : 'right'] = '20px';
    el.wrap.style[left ? 'right' : 'left'] = 'auto';
  }

  function build() {
    var style = document.createElement('style');
    style.textContent = CSS;
    root.appendChild(style);
    el.wrap = document.createElement('div');
    el.wrap.className = 'wrap right';
    el.wrap.innerHTML =
      '<div class="panel" role="dialog" aria-modal="false" aria-label="Chat with the practice" hidden>' +
        '<div class="head">' +
          '<div class="avatar" aria-hidden="true"></div>' +
          '<div class="who"><b class="name">Loading…</b><div class="status"><span class="dot"></span><span class="status-text">Connecting…</span></div></div>' +
          '<a class="hbtn call" hidden aria-label="Call the office">' + ICON.phone + '</a>' +
          '<button class="hbtn close" type="button" aria-label="Close chat">' + ICON.close + '</button>' +
        '</div>' +
        '<div class="body" aria-live="polite"></div>' +
        '<div class="foot">' +
          '<div class="compose"><label class="sr" for="hj-input">Type your message</label>' +
            '<textarea id="hj-input" rows="1" maxlength="1500" placeholder="Type your message…"></textarea>' +
            '<button class="send" type="button" aria-label="Send message" disabled>' + ICON.send + '</button></div>' +
          '<div class="fine"><span>Please don\'t share medical details here.</span><span>Powered by HeyJarvis</span></div>' +
        '</div>' +
      '</div>' +
      '<div class="teaser" hidden role="button" tabindex="0"><button type="button" aria-label="Dismiss">&times;</button><strong></strong><span></span></div>' +
      '<button class="launcher" type="button" aria-haspopup="dialog" aria-expanded="false">' + ICON.chat + '<span class="launch-label"></span></button>';
    root.appendChild(el.wrap);
    el.panel = el.wrap.querySelector('.panel');
    el.body = el.wrap.querySelector('.body');
    el.name = el.wrap.querySelector('.name');
    el.avatar = el.wrap.querySelector('.avatar');
    el.dot = el.wrap.querySelector('.dot');
    el.statusText = el.wrap.querySelector('.status-text');
    el.call = el.wrap.querySelector('.call');
    el.input = el.wrap.querySelector('textarea');
    el.send = el.wrap.querySelector('.send');
    el.launcher = el.wrap.querySelector('.launcher');
    el.launchLabel = el.wrap.querySelector('.launch-label');
    el.teaser = el.wrap.querySelector('.teaser');
    el.launchLabel.textContent = cfg.label;
    document.body.appendChild(host);
    applyBrand();

    el.launcher.addEventListener('click', function () { toggle(); });
    el.wrap.querySelector('.close').addEventListener('click', function () { toggle(false); });
    el.teaser.addEventListener('click', function (e) {
      if (e.target.tagName === 'BUTTON') { dismissTeaser(); e.stopPropagation(); return; }
      toggle(true);
    });
    el.teaser.addEventListener('keydown', function (e) { if (e.key === 'Enter') toggle(true); });
    el.send.addEventListener('click', function () { send(el.input.value); });
    el.input.addEventListener('input', function () {
      el.input.style.height = 'auto';
      el.input.style.height = Math.min(el.input.scrollHeight, 96) + 'px';
      el.send.disabled = !el.input.value.trim() || state.sending;
    });
    el.input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(el.input.value); }
    });
    el.wrap.addEventListener('keydown', function (e) { if (e.key === 'Escape' && state.open) toggle(false); });
  }

  function renderHeader() {
    var b = state.brand;
    if (!b) return;
    el.name.textContent = b.practice_name || 'Our office';
    el.avatar.textContent = (b.practice_name || '?').trim().charAt(0).toUpperCase();
    el.panel.setAttribute('aria-label', 'Chat with ' + (b.practice_name || 'the practice'));
    var open = b.is_open !== false;
    el.dot.classList.toggle('off', !open);
    el.statusText.textContent = open ? 'Online · replies in seconds' : 'Office closed · leave a message';
    if (b.phone) {
      el.call.hidden = false;
      el.call.href = 'tel:' + String(b.phone).replace(/[^\d+]/g, '');
      el.call.setAttribute('aria-label', 'Call ' + b.practice_name + ' at ' + b.phone);
    }
  }

  // ── Rendering messages ───────────────────────────────────────────────────
  function scrollDown() { el.body.scrollTop = el.body.scrollHeight; }
  function clearTransient() {
    var n = el.body.querySelectorAll('.chips, .typing-row, .notice, .skeleton-box');
    for (var i = 0; i < n.length; i++) n[i].parentNode.removeChild(n[i]);
  }
  function addBubble(role, text, opts) {
    opts = opts || {};
    var row = document.createElement('div');
    row.className = 'row ' + (role === 'me' ? 'me' : 'them');
    row.innerHTML = '<div class="bubble">' + rich(text) + '</div>';
    el.body.appendChild(row);
    var meta = null;
    if (role === 'me') {
      meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = opts.status === 'failed' ? '' : 'Sent';
      el.body.appendChild(meta);
    }
    if (opts.save !== false) {
      state.transcript.push({ r: role, t: text });
      persist();
    }
    scrollDown();
    return meta;
  }
  function showChips(list) {
    if (!list || !list.length || state.complete) return;
    var box = document.createElement('div');
    box.className = 'chips';
    list.slice(0, 6).forEach(function (item) {
      // Concierge sends {label, value}: show the label, send the value.
      var label = typeof item === 'string' ? item : (item && (item.label || item.value)) || '';
      var value = typeof item === 'string' ? item : (item && (item.value || item.label)) || '';
      if (!label) return;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.textContent = label;
      b.addEventListener('click', function () { send(value, null, label); });
      box.appendChild(b);
    });
    el.body.appendChild(box);
    scrollDown();
  }
  function showTyping() {
    var row = document.createElement('div');
    row.className = 'row them typing-row';
    row.innerHTML = '<div class="bubble typing" aria-label="Typing"><i></i><i></i><i></i></div>';
    el.body.appendChild(row);
    scrollDown();
  }
  function showNotice(message, retry, info) {
    var box = document.createElement('div');
    box.className = 'notice' + (info ? ' info' : '');
    box.setAttribute('role', 'alert');
    box.innerHTML = '<div><div>' + esc(message) + '</div></div>';
    if (retry) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = 'Try again';
      b.addEventListener('click', function () { box.parentNode && box.parentNode.removeChild(box); retry(); });
      box.firstChild.appendChild(b);
    }
    el.body.appendChild(box);
    scrollDown();
  }
  function showDone() {
    var box = document.createElement('div');
    box.className = 'done';
    var name = (state.brand && state.brand.practice_name) || 'The practice';
    box.innerHTML = '<b>Request sent to the front desk</b>' + esc(name) +
      ' will contact you to confirm a time. Your appointment is not booked until they confirm it with you.';
    var again = document.createElement('button');
    again.type = 'button';
    again.textContent = 'Start a new conversation';
    again.addEventListener('click', restart);
    box.appendChild(again);
    el.body.appendChild(box);
    el.input.disabled = true;
    el.input.placeholder = 'Conversation complete';
    el.send.disabled = true;
    scrollDown();
  }
  function trustLine() {
    var name = (state.brand && state.brand.practice_name) || 'this practice';
    var t = document.createElement('div');
    t.className = 'trust';
    t.innerHTML = ICON.lock + '<span>Your details go only to the ' + esc(name) + ' front desk.</span>';
    el.body.appendChild(t);
  }

  // ── Conversation flow (all replies come from the practice's Concierge) ─────
  function loadConfig() {
    return api('/api/v1/widget/config/').then(function (data) {
      state.brand = data;
      state.configError = null;
      applyBrand();
      renderHeader();
      return data;
    }, function (err) {
      state.configError = err;
      throw err;
    });
  }

  function start() {
    if (state.initPromise) return state.initPromise;   // one conversation per visitor, even on double clicks
    el.body.innerHTML = '<div class="skeleton-box"><div class="skeleton" style="width:70%"></div><div class="skeleton" style="width:45%"></div></div>';
    state.initPromise = (state.brand ? Promise.resolve(state.brand) : loadConfig()).then(function () {
      return api('/api/v1/widget/conversation/', { session_id: state.sessionId, url: window.location.href });
    }).then(function (data) {
      state.started = true;
      if (data.conversation_id) state.conversationId = data.conversation_id;
      el.body.innerHTML = '';
      trustLine();
      if (state.transcript.length) {
        state.transcript.forEach(function (m) { addBubble(m.r, m.t, { save: false }); });
        if (state.complete) showDone(); else showChips(data.quick_replies);
      } else {
        addBubble('them', data.welcome_message || data.message || 'Hi! How can we help you today?');
        showChips(data.quick_replies);
      }
      persist();
      el.input.disabled = state.complete;
      el.send.disabled = true;
      if (!state.complete) el.input.focus();
    }, function (err) {
      state.initPromise = null;
      el.body.innerHTML = '';
      if (err && err.config) {
        showNotice('This chat is missing its connection settings (data-api-url). Please contact the website owner.', null);
        return;
      }
      el.statusText.textContent = 'Not connected';
      el.dot.classList.add('off');
      if (!state.brand) el.name.textContent = 'Chat unavailable';
      showNotice(friendlyError(err), function () { start(); });
    });
    return state.initPromise;
  }

  function send(text, retryMeta, shownText) {
    text = String(text || '').trim();
    if (!text || state.sending || state.complete) return;
    if (!state.started) { start(); return; }
    state.sending = true;
    el.send.disabled = true;
    clearTransient();
    var meta = retryMeta || addBubble('me', shownText || text);
    if (retryMeta) { retryMeta.className = 'meta'; retryMeta.textContent = 'Sending…'; }
    el.input.value = '';
    el.input.style.height = 'auto';
    showTyping();
    api('/api/v1/widget/message/', {
      session_id: state.sessionId,
      conversation_id: state.conversationId || undefined,
      message: text,
      url: window.location.href
    }).then(function (data) {
      clearTransient();
      if (data.conversation_id) state.conversationId = data.conversation_id;
      meta.className = 'meta';
      meta.textContent = 'Sent';
      addBubble('them', data.response || data.message || '');
      if (data.conversation_complete) {
        state.complete = true;
        persist();
        showDone();
      } else {
        showChips(data.quick_replies);
      }
    }, function (err) {
      clearTransient();
      meta.className = 'meta fail';
      meta.textContent = 'Not delivered.';
      var retry = document.createElement('button');
      retry.type = 'button';
      retry.textContent = 'Retry';
      retry.addEventListener('click', function () { send(text, meta, shownText); });
      meta.appendChild(retry);
      showNotice(friendlyError(err), null);
    }).then(function () {
      state.sending = false;
      if (!state.complete) {
        el.send.disabled = !el.input.value.trim();
        el.input.focus();
      }
    });
  }

  function restart() {
    state.transcript = [];
    state.complete = false;
    state.started = false;
    state.initPromise = null;
    state.conversationId = '';
    state.sessionId = newId();
    setItem('localStorage', keyBase + '_session', state.sessionId);
    removeItem('localStorage', keyBase + '_log');
    persist();
    el.input.disabled = false;
    el.input.placeholder = 'Type your message…';
    start();
  }

  function toggle(force) {
    var open = typeof force === 'boolean' ? force : !state.open;
    if (open === state.open) return;
    state.open = open;
    el.panel.hidden = !open;
    el.wrap.classList.toggle('is-open', open);
    el.launcher.setAttribute('aria-expanded', String(open));
    el.launcher.innerHTML = open ? ICON.close + '<span class="sr">Close chat</span>' : ICON.chat + '<span class="launch-label"></span>';
    el.launcher.classList.toggle('icon-only', open);
    if (!open) el.wrap.querySelector('.launch-label').textContent = cfg.label;
    if (open) {
      dismissTeaser();
      start();
      setTimeout(function () { if (!el.input.disabled) el.input.focus(); }, 50);
    } else {
      el.launcher.focus();
    }
  }

  function dismissTeaser() {
    el.teaser.hidden = true;
    setItem('sessionStorage', keyBase + '_teaser', '1');
  }
  function maybeTeaser() {
    if (state.open || getItem('sessionStorage', keyBase + '_teaser') || state.transcript.length) return;
    var b = state.brand || {};
    el.teaser.querySelector('strong').textContent = 'Need an appointment?';
    el.teaser.querySelector('span').textContent = (b.is_open === false
      ? 'We\'re closed right now, but you can request a visit here and we\'ll get back to you.'
      : 'Ask us anything or request a visit. We usually reply in seconds.');
    el.teaser.hidden = false;
  }

  function init() {
    build();
    loadConfig().then(function (b) {
      setTimeout(maybeTeaser, 4000);
      if (cfg.autoOpen || b.auto_open) setTimeout(function () { toggle(true); }, (b.auto_open_delay || 0) * 1000);
    }, function () { /* the panel explains the problem when opened */ });
    window.HeyJarvis = {
      open: function () { toggle(true); },
      close: function () { toggle(false); },
      toggle: function () { toggle(); },
      reset: restart,
      version: VERSION
    };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();