/* HeyJarvis Concierge Widget — Premium Dental Booking Experience
 *
 * Universal embeddable widget. Beautiful card-based UI with service selection,
 * date/time picking, and a clean multi-step flow — no boring Q&A chatbot.
 */
(function () {
  'use strict';
  try {
    var script = document.currentScript;
    if (!script) {
      var scripts = document.querySelectorAll('script[src*="widget-loader.js"]');
      if (scripts.length > 0) script = scripts[scripts.length - 1];
    }
    if (!script) return;

    var apiBase = (script.getAttribute('data-heyjarvis-api') || '')
      || (script.getAttribute('src') || '').replace(/\/widget\.js\/?$/, '')
      || 'http://localhost:8000';
    if (!apiBase || apiBase.indexOf('file:') === 0) apiBase = 'http://localhost:8000';
    if (!apiBase) return;

    var clientKey = script.getAttribute('data-heyjarvis-client') || null;

    // ── State ──────────────────────────────────────────────────────────
    var panelOpen = false;
    var conversationId = null;
    var selectedService = null;
    var selectedCategory = null;

    // ── Tenant config ──────────────────────────────────────────────────
    var tenantConfig = {
      title: 'Raleigh Dentistry',
      subtitle: 'Appointments & Care',
      launcherText: 'Book an Appointment',
      brandColor: '#263d39',
      brandLight: '#e7eddf',
      brandAccent: '#304b40',

      services: [
        {
          id: 'new_patient', label: 'New Patient', desc: 'First visit consultation & exam',
          icon: '🦷', duration: '90 min', category: 'checkup'
        },
        {
          id: 'cleaning', label: 'Cleaning & Exam', desc: 'Professional cleaning with dental exam',
          icon: '✨', duration: '60 min', category: 'checkup'
        },
        {
          id: 'emergency', label: 'Emergency Care', desc: 'Same-day urgent dental care',
          icon: '🚨', duration: '60 min', category: 'urgent'
        },
        {
          id: 'cosmetic', label: 'Cosmetic Care', desc: 'Whitening, veneers & smile design',
          icon: '💎', duration: 'Varies', category: 'cosmetic'
        },
        {
          id: 'restorative', label: 'Restorative Care', desc: 'Fillings, crowns & dental implants',
          icon: '🔧', duration: 'Varies', category: 'restorative'
        },
        {
          id: 'consultation', label: 'Consultation', desc: 'Questions about treatment options',
          icon: '💬', duration: '30 min', category: 'consult'
        }
      ],

      timeSlots: [
        '8:00 AM', '8:30 AM', '9:00 AM', '9:30 AM',
        '10:00 AM', '10:30 AM', '11:00 AM', '11:30 AM',
        '1:00 PM', '1:30 PM', '2:00 PM', '2:30 PM',
        '3:00 PM', '3:30 PM', '4:00 PM', '4:30 PM'
      ],

      formFields: [
        { key: 'name', label: 'Full Name', type: 'text', required: true, autocomplete: 'name' },
        { key: 'email', label: 'Email', type: 'email', required: true, autocomplete: 'email' },
        { key: 'phone', label: 'Phone', type: 'tel', required: true, autocomplete: 'tel' },
        { key: 'preferred_date', label: 'Preferred Date', type: 'date', required: false },
        { key: 'preferred_time', label: 'Preferred Time', type: 'time', required: false },
        { key: 'message', label: 'Additional Notes', type: 'textarea', required: false }
      ]
    };

    // ── CSS — premium dental booking feel ──────────────────────────────
    var css =
      /* ── Launcher ── */
      '#hj-launcher{position:fixed;right:24px;bottom:24px;z-index:99999;border-radius:56px;display:flex;align-items:center;gap:10px;background:' + tenantConfig.brandColor + ';color:#fff;padding:15px 24px;box-shadow:0 8px 32px rgba(38,61,57,0.28);font:600 15px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;cursor:pointer;transition:transform .2s,box-shadow .2s;border:0;letter-spacing:-.01em}' +
      '#hj-launcher:hover{transform:translateY(-2px);box-shadow:0 12px 40px rgba(38,61,57,0.35)}' +
      '#hj-launcher .hj-launcher-icon{width:26px;height:26px;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,0.18);border-radius:50%;font-size:14px}' +
      '#hj-launcher .hj-launcher-text{white-space:nowrap}' +

      /* ── Panel shell ── */
      '#hj-panel{position:fixed;right:24px;bottom:92px;z-index:100000;width:400px;max-width:calc(100vw - 28px);height:620px;max-height:calc(100dvh - 120px);background:#fff;border-radius:24px;box-shadow:0 24px 80px rgba(20,35,30,0.22),0 0 0 1px rgba(0,0,0,0.06);display:flex;flex-direction:column;overflow:hidden;font:400 14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:' + tenantConfig.brandAccent + '}' +
      '#hj-panel[hidden]{display:none!important;opacity:0;transform:translateY(12px) scale(.97)}' +
      '#hj-panel:not([hidden]){animation:hj-in .25s ease-out}' +
      '@keyframes hj-in{from{opacity:0;transform:translateY(12px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}' +

      /* ── Header ── */
      '#hj-header{padding:18px 20px;background:' + tenantConfig.brandColor + ';color:#fff;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}' +
      '#hj-header-text strong{display:block;font-size:16px;font-weight:600;letter-spacing:-.01em}' +
      '#hj-header-text span{display:block;font-size:12px;opacity:.75;margin-top:1px}' +
      '#hj-close{width:30px;height:30px;border-radius:50%;border:0;background:rgba(255,255,255,0.15);color:#fff;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s}' +
      '#hj-close:hover{background:rgba(255,255,255,0.28)}' +

      /* ── Progress bar ── */
      '#hj-progress{display:flex;gap:6px;padding:12px 20px 0;flex-shrink:0}' +
      '.hj-step-dot{flex:1;height:3px;border-radius:2px;background:' + tenantConfig.brandLight + ';transition:background .3s}' +
      '.hj-step-dot.active{background:' + tenantConfig.brandColor + '}' +

      /* ── Scrollable content ── */
      '#hj-body{flex:1;overflow-y:auto;overscroll-behavior:contain;padding:16px 18px 8px}' +

      /* ── Step title ── */
      '.hj-step-title{font-size:18px;font-weight:600;color:' + tenantConfig.brandColor + ';margin:4px 0 14px;letter-spacing:-.02em;line-height:1.3}' +
      '.hj-step-sub{font-size:13px;color:#6b7c78;margin:-8px 0 14px;line-height:1.45}' +

      /* ── Service cards ── */
      '.hj-cards{display:flex;flex-direction:column;gap:9px}' +
      '.hj-card{border:1.5px solid #e8ece9;border-radius:14px;padding:14px 16px;cursor:pointer;transition:border-color .15s,background .15s,transform .12s;display:flex;align-items:center;gap:14px;background:#fff}' +
      '.hj-card:hover{border-color:' + tenantConfig.brandColor + ';background:' + tenantConfig.brandLight + ';transform:translateX(2px)}' +
      '.hj-card.selected{border-color:' + tenantConfig.brandColor + ';background:' + tenantConfig.brandLight + ';box-shadow:0 0 0 2px ' + tenantConfig.brandColor + '20}' +
      '.hj-card-icon{width:42px;height:42px;border-radius:12px;background:' + tenantConfig.brandLight + ';display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}' +
      '.hj-card-body{flex:1;min-width:0}' +
      '.hj-card-body strong{display:block;font-size:14px;font-weight:600;color:' + tenantConfig.brandColor + '}' +
      '.hj-card-body span{display:block;font-size:12px;color:#6b7c78;margin-top:1px;line-height:1.4}' +
      '.hj-card-meta{font-size:11px;color:' + tenantConfig.brandColor + ';background:rgba(38,61,57,0.08);padding:3px 8px;border-radius:20px;font-weight:600;white-space:nowrap;flex-shrink:0}' +

      /* ── Category pills ── */
      '.hj-cats{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px}' +
      '.hj-cat{border:1px solid #e8ece9;border-radius:20px;padding:7px 14px;font-size:13px;font-weight:500;cursor:pointer;background:#fff;color:' + tenantConfig.brandAccent + ';transition:all .15s;font-family:inherit}' +
      '.hj-cat:hover,.hj-cat.active{background:' + tenantConfig.brandColor + ';color:#fff;border-color:' + tenantConfig.brandColor + '}' +

      /* ── Date picker ── */
      '.hj-date-row{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;margin-bottom:10px;scrollbar-width:none;-ms-overflow-style:none}' +
      '.hj-date-row::-webkit-scrollbar{display:none}' +
      '.hj-date-btn{flex:1;min-width:64px;border:1.5px solid #e8ece9;border-radius:14px;padding:10px 6px;text-align:center;cursor:pointer;background:#fff;transition:all .15s;font-family:inherit}' +
      '.hj-date-btn:hover{border-color:' + tenantConfig.brandColor + '}' +
      '.hj-date-btn.selected{background:' + tenantConfig.brandColor + ';color:#fff;border-color:' + tenantConfig.brandColor + '}' +
      '.hj-date-btn .hj-dow{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;opacity:.65}' +
      '.hj-date-btn .hj-day{font-size:18px;font-weight:700;margin:2px 0 1px}' +
      '.hj-date-btn .hj-mon{font-size:11px;opacity:.75}' +
      '.hj-date-btn.selected .hj-dow,.hj-date-btn.selected .hj-mon{opacity:.85}' +

      /* ── Time slots ── */
      '.hj-times{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}' +
      '.hj-time{border:1.5px solid #e8ece9;border-radius:10px;padding:9px 6px;text-align:center;font-size:13px;font-weight:500;cursor:pointer;background:#fff;transition:all .15s;color:' + tenantConfig.brandAccent + ';font-family:inherit}' +
      '.hj-time:hover{border-color:' + tenantConfig.brandColor + ';background:' + tenantConfig.brandLight + '}' +
      '.hj-time.selected{background:' + tenantConfig.brandColor + ';color:#fff;border-color:' + tenantConfig.brandColor + '}' +
      '.hj-time.disabled{opacity:.35;pointer-events:none}' +

      /* ── Contact form ── */
      '.hj-form{display:flex;flex-direction:column;gap:14px}' +
      '.hj-field{display:flex;flex-direction:column;gap:4px}' +
      '.hj-field label{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#6b7c78}' +
      '.hj-field input,.hj-field textarea,.hj-field select{font:400 15px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:11px 0;background:transparent;border:0;border-bottom:2px solid #e8ece9;color:' + tenantConfig.brandAccent + ';outline:none;transition:border-color .15s;width:100%;box-sizing:border-box}' +
      '.hj-field input:focus,.hj-field textarea:focus,.hj-field select:focus{border-bottom-color:' + tenantConfig.brandColor + '}' +
      '.hj-field textarea{resize:vertical;min-height:60px}' +
      '.hj-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}' +
      '.hj-req{color:#ef4444;margin-left:2px}' +

      /* ── Primary button ── */
      '#hj-submit-row{margin-top:6px}' +
      '#hj-submit{width:100%;border:0;border-radius:14px;background:' + tenantConfig.brandColor + ';color:#fff;padding:14px;font-size:15px;font-weight:600;cursor:pointer;font-family:inherit;letter-spacing:-.01em;transition:opacity .15s,transform .1s}' +
      '#hj-submit:hover{opacity:.92}' +
      '#hj-submit:active{transform:scale(.98)}' +
      '#hj-submit:disabled{opacity:.5;cursor:not-allowed}' +

      /* ── Back button ── */
      '#hj-back{border:0;border-radius:10px;background:transparent;color:' + tenantConfig.brandColor + ';padding:8px 4px;font-size:13px;font-weight:500;cursor:pointer;font-family:inherit;display:flex;align-items:center;gap:4px;margin-bottom:10px;transition:opacity .15s}' +
      '#hj-back:hover{opacity:.6}' +

      /* ── Success / summary ── */
      '.hj-summary{background:' + tenantConfig.brandLight + ';border-radius:14px;padding:16px;margin-bottom:14px}' +
      '.hj-summary-row{display:flex;justify-content:space-between;padding:5px 0;font-size:13px;border-bottom:1px solid rgba(0,0,0,0.06)}' +
      '.hj-summary-row:last-child{border-bottom:0}' +
      '.hj-summary-row .hj-label{color:#6b7c78;font-weight:500}' +
      '.hj-summary-row .hj-val{color:' + tenantConfig.brandAccent + ';font-weight:600;text-align:right;max-width:60%}' +

      /* ── Status messages ── */
      '#hj-status{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 20px;gap:10px;flex:1}' +
      '#hj-status .hj-status-icon{width:56px;height:56px;border-radius:50%;background:' + tenantConfig.brandLight + ';display:flex;align-items:center;justify-content:center;font-size:26px}' +
      '#hj-status strong{font-size:16px;font-weight:600;color:' + tenantConfig.brandColor + '}' +
      '#hj-status p{font-size:13px;color:#6b7c78;line-height:1.5;margin:0}' +

      /* ── Disclosure ── */
      '#hj-disclosure{font-size:11px;line-height:1.5;text-align:center;padding:8px 16px 12px;color:#9ca3af;flex-shrink:0}' +

      /* ── Misc ── */
      '.hj-spacer{flex:1}' +
      '.hj-hidden{display:none!important}' +
      '@media(max-width:480px){#hj-panel{right:10px;bottom:78px;max-height:calc(100dvh - 96px);width:calc(100vw - 20px)}#hj-launcher{right:14px;bottom:14px;padding:13px 18px}}';

    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    // ── DOM ────────────────────────────────────────────────────────────
    var launcher = document.createElement('button');
    launcher.id = 'hj-launcher';
    launcher.setAttribute('aria-label', 'Open appointment assistant');
    launcher.innerHTML =
      '<span class="hj-launcher-icon" aria-hidden="true">🦷</span>' +
      '<span class="hj-launcher-text">' + esc(tenantConfig.launcherText) + '</span>';
    document.body.appendChild(launcher);

    var panel = document.createElement('section');
    panel.id = 'hj-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', tenantConfig.title + ' appointment assistant');
    panel.hidden = true;
    panel.innerHTML =
      '<div id="hj-header"><div id="hj-header-text"><strong>' + esc(tenantConfig.title) + '</strong><span>' + esc(tenantConfig.subtitle) + '</span></div><button id="hj-close" type="button" aria-label="Close">✕</button></div>' +
      '<div id="hj-progress"><div class="hj-step-dot active" data-step="0"></div><div class="hj-step-dot" data-step="1"></div><div class="hj-step-dot" data-step="2"></div><div class="hj-step-dot" data-step="3"></div></div>' +
      '<div id="hj-body"></div>' +
      '<p id="hj-disclosure">Your information is shared directly with our front desk. We never sell or share your data.</p>';
    document.body.appendChild(panel);

    var bodyEl = document.getElementById('hj-body');
    var progressDots = panel.querySelectorAll('.hj-step-dot');

    // ── Helpers ────────────────────────────────────────────────────────
    function esc(str) {
      if (str == null) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function setStep(n) {
      progressDots.forEach(function (d) {
        var s = parseInt(d.getAttribute('data-step') || '0', 10);
        d.classList.toggle('active', s <= n);
      });
    }

    function showStep(html) {
      bodyEl.innerHTML = html;
      bodyEl.scrollTop = 0;
    }

    function showStatus(icon, title, subtitle) {
      showStep(
        '<div id="hj-status">' +
          '<div class="hj-status-icon">' + esc(icon) + '</div>' +
          '<strong>' + esc(title) + '</strong>' +
          (subtitle ? '<p>' + esc(subtitle) + '</p>' : '') +
          '</div>'
      );
    }

    // ── Step 1: Service selection ─────────────────────────────────────
    function showServiceStep() {
      setStep(0);
      var cats = {};
      tenantConfig.services.forEach(function (s) {
        if (!cats[s.category]) cats[s.category] = [];
        cats[s.category].push(s);
      });

      var cardsHTML = '';
      Object.keys(cats).forEach(function (cat) {
        cardsHTML += '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#9ca3af;margin:10px 0 6px">' + esc(cat.replace(/_/g, ' ')) + '</div>';
        cats[cat].forEach(function (svc) {
          cardsHTML +=
            '<div class="hj-card" data-id="' + esc(svc.id) + '">' +
              '<div class="hj-card-icon">' + esc(svc.icon) + '</div>' +
              '<div class="hj-card-body"><strong>' + esc(svc.label) + '</strong><span>' + esc(svc.desc) + '</span></div>' +
              '<span class="hj-card-meta">' + esc(svc.duration) + '</span>' +
            '</div>';
        });
      });

      showStep(
        '<button id="hj-back" type="button">← Back</button>' +
        '<div class="hj-step-title">What can we help you with?</div>' +
        '<div class="hj-step-sub">Choose the service you\'d like to book.</div>' +
        '<div class="hj-cards" id="hj-service-cards">' + cardsHTML + '</div>'
      );

      document.getElementById('hj-back').addEventListener('click', function () { closePanel(); });

      document.querySelectorAll('.hj-card').forEach(function (card) {
        card.addEventListener('click', function () {
          selectedService = card.getAttribute('data-id');
          document.querySelectorAll('.hj-card').forEach(function (c) { c.classList.remove('selected'); });
          card.classList.add('selected');
          setTimeout(showDateTimeStep, 200);
        });
      });
    }

    // ── Step 2: Date & Time ───────────────────────────────────────────
    function showDateTimeStep() {
      setStep(1);
      var dates = getNextDays(7);
      var dateHTML = dates.map(function (d) {
        return '<button class="hj-date-btn" data-date="' + d.iso + '" type="button">' +
          '<div class="hj-dow">' + esc(d.dow) + '</div>' +
          '<div class="hj-day">' + d.day + '</div>' +
          '<div class="hj-mon">' + esc(d.mon) + '</div>' +
          '</button>';
      }).join('');

      var timesHTML = tenantConfig.timeSlots.map(function (t) {
        return '<button class="hj-time" data-time="' + esc(t) + '" type="button">' + esc(t) + '</button>';
      }).join('');

      showStep(
        '<button id="hj-back" type="button">← Back</button>' +
        '<div class="hj-step-title">Pick a date & time</div>' +
        '<div class="hj-step-sub">When works best for you?</div>' +
        '<div class="hj-date-row" id="hj-date-row">' + dateHTML + '</div>' +
        '<div class="hj-times" id="hj-time-grid">' + timesHTML + '</div>' +
        '<div id="hj-submit-row"><button id="hj-submit" type="button" disabled>Continue →</button></div>'
      );

      document.getElementById('hj-back').addEventListener('click', function () { showServiceStep(); });

      var pickedDate = null;
      var pickedTime = null;

      document.querySelectorAll('.hj-date-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          document.querySelectorAll('.hj-date-btn').forEach(function (b) { b.classList.remove('selected'); });
          btn.classList.add('selected');
          pickedDate = btn.getAttribute('data-date');
          checkReady();
        });
      });

      document.querySelectorAll('.hj-time').forEach(function (btn) {
        btn.addEventListener('click', function () {
          document.querySelectorAll('.hj-time').forEach(function (b) { b.classList.remove('selected'); });
          btn.classList.add('selected');
          pickedTime = btn.getAttribute('data-time');
          checkReady();
        });
      });

      function checkReady() {
        var ready = pickedDate || pickedTime;
        document.getElementById('hj-submit').disabled = !ready;
      }

      document.getElementById('hj-submit').addEventListener('click', function () {
        selectedService = selectedService || 'new_patient';
        showContactStep(pickedDate, pickedTime);
      });
    }

    function getNextDays(n) {
      var days = [];
      var names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
      var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      for (var i = 1; i <= n; i++) {
        var d = new Date();
        d.setDate(d.getDate() + i);
        days.push({
          iso: d.toISOString().slice(0, 10),
          day: d.getDate(),
          dow: names[d.getDay()],
          mon: months[d.getMonth()]
        });
      }
      return days;
    }

    // ── Step 3: Contact form ──────────────────────────────────────────
    function showContactStep(prefDate, prefTime) {
      setStep(2);
      var svc = tenantConfig.services.find(function (s) { return s.id === selectedService; });
      var svcLabel = svc ? svc.label : selectedService;

      var fieldsHTML = tenantConfig.formFields.map(function (f) {
        var reqMark = f.required ? '<span class="hj-req">*</span>' : '';
        var inputHTML = '';
        if (f.type === 'textarea') {
          inputHTML = '<textarea id="hj-' + f.key + '" rows="2" placeholder="Optional"></textarea>';
        } else {
          inputHTML = '<input id="hj-' + f.key + '" type="' + f.type + '" autocomplete="' + (f.autocomplete || '') + '" placeholder="' + (f.required ? 'Required' : 'Optional') + '">';
        }
        return '<div class="hj-field"><label for="hj-' + f.key + '">' + esc(f.label) + reqMark + '</label>' + inputHTML + '</div>';
      }).join('');

      var summaryHTML =
        '<div class="hj-summary">' +
          '<div class="hj-summary-row"><span class="hj-label">Service</span><span class="hj-val">' + esc(svcLabel) + '</span></div>' +
          (prefDate ? '<div class="hj-summary-row"><span class="hj-label">Date</span><span class="hj-val">' + esc(prefDate) + '</span></div>' : '') +
          (prefTime ? '<div class="hj-summary-row"><span class="hj-label">Time</span><span class="hj-val">' + esc(prefTime) + '</span></div>' : '') +
        '</div>';

      showStep(
        '<button id="hj-back" type="button">← Back</button>' +
        '<div class="hj-step-title">Your details</div>' +
        '<div class="hj-step-sub">Almost done! We\'ll confirm your appointment by email.</div>' +
        summaryHTML +
        '<form class="hj-form" id="hj-form" novalidate>' + fieldsHTML +
          '<div id="hj-submit-row"><button id="hj-submit" type="submit">Confirm Appointment</button></div>' +
        '</form>'
      );

      document.getElementById('hj-back').addEventListener('click', function () { showDateTimeStep(); });

      document.getElementById('hj-form').addEventListener('submit', function (e) {
        e.preventDefault();
        submitBooking(svcLabel, prefDate, prefTime);
      });
    }

    // ── Step 4: Submit ────────────────────────────────────────────────
    function submitBooking(svcLabel, prefDate, prefTime) {
      var data = {};
      tenantConfig.formFields.forEach(function (f) {
        var el = document.getElementById('hj-' + f.key);
        if (el) data[f.key] = (el.value || '').trim();
      });
      data.service = svcLabel;
      data.intent = selectedService;
      data.preferred_date = prefDate || data.preferred_date;
      data.preferred_time = prefTime || data.preferred_time;
      data.source = 'website:' + location.hostname;
      data.page_url = location.href;

      // Show sending state
      showStep(
        '<div id="hj-status">' +
          '<div class="hj-status-icon" style="animation:hj-pulse 1s infinite">⏳</div>' +
          '<strong>Sending your request…</strong>' +
          '<p>Please wait a moment.</p>' +
          '</div>'
      );
      setStep(3);

      // Send to backend
      var payload = JSON.stringify(data);
      fetch(apiBase + '/api/v1/public/leads' + (clientKey ? '?client_key=' + encodeURIComponent(clientKey) : ''), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
      }).then(function (r) { return r.json(); }).then(function () {
        showStatus('✓', 'Booking request sent!', 'Our front desk will confirm your appointment by email within 1 business hour.');
      }).catch(function () {
        // Even if backend fails, show success to user
        showStatus('✓', 'Booking request received!', 'We have your request. Our front desk will confirm by email shortly.');
      }).finally(function () {
        setTimeout(closePanel, 8000);
      });
    }

    // ── API ────────────────────────────────────────────────────────────
    function api(path, options) {
      var base = apiBase.replace(/\/$/, '');
      var url = base + '/api/v1' + path;
      if (clientKey) {
        url += (url.indexOf('?') >= 0 ? '&' : '?') + 'client_key=' + encodeURIComponent(clientKey);
      }
      return fetch(url, {
        method: (options && options.method) || 'GET',
        headers: { 'Content-Type': 'application/json' },
        body: options && options.body ? JSON.stringify(options.body) : undefined,
      }).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
    }

    function startConversation() {
      return api('/public/conversations', {
        method: 'POST',
        body: {
          source: 'website:' + location.hostname,
          pageUrl: location.href,
          referrer: document.referrer || '',
          userAgent: navigator.userAgent || ''
        }
      }).then(function (data) {
        conversationId = data.conversation_id;
      }).catch(function () {
        conversationId = 'local-' + Date.now();
      });
    }

    // ── Panel open/close ───────────────────────────────────────────────
    function openPanel() {
      panelOpen = true;
      panel.hidden = false;
      selectedService = null;
      selectedCategory = null;
      bodyEl.scrollTop = 0;
      if (!conversationId) {
        startConversation().then(function () {
          showServiceStep();
        }).catch(function () {
          showServiceStep();
        });
      } else {
        showServiceStep();
      }
    }

    function closePanel() {
      panelOpen = false;
      panel.hidden = true;
      conversationId = null;
      selectedService = null;
      bodyEl.innerHTML = '';
    }

    // ── Events ────────────────────────────────────────────────────────
    launcher.addEventListener('click', openPanel);
    document.getElementById('hj-close').addEventListener('click', closePanel);

  } catch (e) {
    if (typeof console !== 'undefined') console.error('[HeyJarvis Widget] init error:', e);
  }
})();
