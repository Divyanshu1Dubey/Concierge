/* HeyJarvis Concierge universal embeddable widget loader. */
(function () {
  'use strict';
  try {
    var script = document.currentScript;
    if (!script) return;
    var clientKey = script.getAttribute('data-heyjarvis-client');
    if (!clientKey) return;
    var target = document.querySelector(script.getAttribute('data-target') || '#concierge-form');
    if (!target) return;

    var apiBase = (script.getAttribute('src') || '').replace('/widget.js', '');
    var css = '.hj-launcher{position:fixed;right:18px;bottom:18px;z-index:9999;font:15px/1.5 system-ui,sans-serif}'
      + '.hj-launcher button{border:0;border-radius:999px;background:#1f3b2e;color:#fff;padding:12px 16px;font-weight:700;cursor:pointer;box-shadow:0 6px 18px rgba(0,0,0,.18)}'
      + '.hj-frame{position:fixed;right:18px;bottom:86px;width:360px;max-width:calc(100vw - 36px);max-height:520px;z-index:9999;background:#fff;border-radius:14px;border:1px solid #e5e5e5;box-shadow:0 18px 40px rgba(0,0,0,.18);display:none;flex-direction:column;overflow:hidden}'
      + '.hj-frame.open{display:flex}'
      + '.hj-head{padding:12px 14px;border-bottom:1px solid #eee;font-weight:700;display:flex;justify-content:space-between;align-items:center}'
      + '.hj-body{padding:12px 14px;overflow:auto;display:flex;flex-direction:column;gap:10px}'
      + '.hj-bubble{background:#f4f7f5;border-radius:12px;padding:10px 12px}'
      + '.hj-user{background:#1f3b2e;color:#fff;align-self:flex-end;border-radius:12px;padding:10px 12px}'
      + '.hj-input{display:flex;gap:8px;padding:10px 12px;border-top:1px solid #eee}'
      + '.hj-input input{flex:1;font:inherit;padding:10px 12px;border:1.5px solid #ddd;border-radius:10px}'
      + '.hj-input button{border:0;border-radius:10px;background:#1f3b2e;color:#fff;padding:10px 12px;font-weight:700}';

    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    var container = document.createElement('div');
    container.className = 'hj-launcher';
    container.innerHTML = '<div class="hj-frame" id="hj-frame"><div class="hj-head"><span>Concierge</span><button id="hj-close">Close</button></div><div class="hj-body" id="hj-body"></div><div class="hj-input"><input id="hj-msg" autocomplete="off"/><button id="hj-send">Send</button></div></div><button id="hj-open">Concierge</button>';
    target.appendChild(container);

    var frame = container.querySelector('#hj-frame');
    var body = container.querySelector('#hj-body');
    var msg = container.querySelector('#hj-msg');
    var conversationId = null;
    var started = false;

    container.querySelector('#hj-open').onclick = function () {
      frame.classList.add('open');
      if (!started) startConversation();
    };
    container.querySelector('#hj-close').onclick = function () { frame.classList.remove('open'); };
    container.querySelector('#hj-send').onclick = sendMessage;
    msg.addEventListener('keydown', function (e) { if (e.key === 'Enter') sendMessage(); });

    function append(html, user) {
      var el = document.createElement('div');
      el.className = user ? 'hj-user' : 'hj-bubble';
      el.innerHTML = html;
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
    }

    function startConversation() {
      started = true;
      fetch(apiBase + '/api/v1/public/conversations?client_key=' + encodeURIComponent(clientKey), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({})})
        .then(function (r) { return r.json(); })
        .then(function (data) {
          conversationId = data.conversation_id;
          append(data.reply || '');
        });
    }

    function sendMessage() {
      var text = msg.value.trim();
      if (!text || !conversationId) return;
      msg.value = '';
      append(text, true);
      fetch(apiBase + '/api/v1/public/conversations/' + conversationId + '/messages?client_key=' + encodeURIComponent(clientKey), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message: text})})
        .then(function (r) { return r.json(); })
        .then(function (data) { append(data.reply || ''); });
    }
  } catch (e) {
    if (window.console) console.error('HeyJarvis widget error', e);
  }
})();
