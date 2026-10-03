/* HeyJarvis Concierge website widget.
 *
 * Paste into any site (WordPress "Custom HTML", Wix "Embed code",
 * Squarespace "Code block", Webflow "Embed", plain HTML):
 *
 *   <div id="concierge-form"></div>
 *   <script src="https://YOUR-CONCIERGE-HOST/widget.js" defer></script>
 *
 * The site's origin must be listed in CONCIERGE_ALLOWED_ORIGINS on the server.
 * No secrets live in this file; the server rate-limits and drops bot submissions.
 */
(function () {
  var script = document.currentScript;
  var api = new URL("/public/requests", script.src).href;
  var mount = document.querySelector(script.getAttribute("data-target") || "#concierge-form");
  if (!mount) return;

  var css =
    ".cj-form{font:15px/1.5 system-ui,sans-serif;max-width:520px;display:grid;gap:14px;color-scheme:light;color:#222}" +
    ".cj-form label{font-size:13px;font-weight:600;display:grid;gap:4px}" +
    // Fixed light colors so the form reads the same on any site, in light or dark mode.
    ".cj-form input,.cj-form textarea{font:inherit;padding:10px 12px;border:1.5px solid #c9c9c9;border-radius:10px;width:100%;box-sizing:border-box;background:#fff;color:#222}" +
    ".cj-form input::placeholder,.cj-form textarea::placeholder{color:#8a8a8a}" +
    ".cj-form input:focus,.cj-form textarea:focus{outline:2.5px solid #2f6d4f;outline-offset:1px;border-color:#2f6d4f}" +
    ".cj-form input:-webkit-autofill{-webkit-text-fill-color:#222;box-shadow:0 0 0 1000px #fff inset}" +
    ".cj-form textarea{min-height:120px;font-size:15px}" +
    ".cj-form button[type=submit]{font:inherit;font-weight:700;font-size:16px;padding:13px 16px;border:0;border-radius:10px;background:#2f6d4f;color:#fff;cursor:pointer;letter-spacing:.01em}" +
    ".cj-form button[type=submit]:disabled{opacity:.6}" +
    ".cj-hp{position:absolute!important;left:-9999px!important;height:0;overflow:hidden}" +
    ".cj-msg{font-size:14px;font-weight:500}" +
    ".cj-opts{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px}" +
    ".cj-opt{border:2px solid #e0e0e0;border-radius:12px;padding:14px 12px;text-align:center;cursor:pointer;background:#fafafa;transition:all .15s}" +
    ".cj-opt:hover{border-color:#2f6d4f;background:#f0f7f3}" +
    ".cj-opt.picked{border-color:#2f6d4f;background:#e3efe7;box-shadow:0 0 0 2px #2f6d4f33}" +
    ".cj-opt .ico{font-size:26px;display:block;margin-bottom:4px}" +
    ".cj-opt .lbl{font-size:13px;font-weight:700;color:#222;line-height:1.25}" +
    ".cj-opt .sub{font-size:11px;color:#666;margin-top:2px;line-height:1.3}" +
    ".cj-msg.ok{color:#2f6d4f} .cj-msg.err{color:#b3392b}";
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  mount.innerHTML =
    '<form class="cj-form" novalidate>' +
    '<p style="font-size:13px;color:#666;margin:0 0 2px;font-weight:600">What can we help you with?</p>' +
    '<div class="cj-opts" id="cj-opts"></div>' +
    '<label>Tell us more <span style="font-weight:400;color:#888">(preferred times, details&hellip;)</span><textarea name="message" required maxlength="10000"></textarea></label>' +
    '<label>Name<input name="name" autocomplete="name"></label>' +
    '<label>Email<input name="email" type="email" autocomplete="email" required></label>' +
    '<label>Phone<input name="phone" type="tel" autocomplete="tel"></label>' +
    '<div class="cj-hp" aria-hidden="true"><label>Website<input name="website" tabindex="-1" autocomplete="off"></label></div>' +
    '<button type="submit">Request appointment</button>' +
    '<div class="cj-msg" role="status"></div>' +
    "</form>";

  var form = mount.querySelector("form");
  var msg = mount.querySelector(".cj-msg");
  var optsEl = document.getElementById("cj-opts");

  var SAMPLES = [
    ["🦷", "New patient", "checkup and cleaning", "Hi, I just moved to Raleigh and I'm looking for a new dentist. Can I get a checkup and cleaning? Weekday mornings are best. Do you take CareCredit?"],
    ["🚨", "Emergency", "urgent pain today", "My back tooth cracked and it really hurts. Can I come in today? Any opening would help."],
    ["✨", "Cleaning", "routine cleaning", "Hi, I'm due for my regular cleaning. Tuesday afternoons work best for me."],
    ["📅", "Reschedule", "move an existing visit", "I need to push my appointment to next week, afternoons please."],
    ["❌", "Cancel", "cancel an appointment", "Please cancel my upcoming appointment. I'll reschedule later. Thank you!"],
    ["💬", "Question", "ask about something", "Do you accept Delta Dental PPO? And roughly how much is teeth whitening?"],
  ];
  var picked = null;
  SAMPLES.forEach(function (s) {
    var div = document.createElement("div");
    div.className = "cj-opt";
    div.setAttribute("role", "button");
    div.setAttribute("tabindex", "0");
    div.setAttribute("aria-pressed", "false");
    div.innerHTML = '<span class="ico">' + s[0] + '</span><span class="lbl">' + s[1] + '</span><span class="sub">' + s[2] + '</span>';
    div.addEventListener("click", function () {
      if (picked === div) {
        picked = null; div.classList.remove("picked"); div.setAttribute("aria-pressed", "false");
        form.elements.message.value = "";
      } else {
        if (picked) { picked.classList.remove("picked"); picked.setAttribute("aria-pressed", "false"); }
        picked = div; div.classList.add("picked"); div.setAttribute("aria-pressed", "true");
        form.elements.message.value = s[3];
        form.elements.message.focus();
      }
    });
    div.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); div.click(); } });
    optsEl.appendChild(div);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var f = new FormData(form);
    if (!f.get("message") || !f.get("email")) {
      msg.textContent = "Please add a message and your email.";
      return;
    }
    var btn = form.querySelector("button");
    btn.disabled = true;
    msg.textContent = "Sending…";
    var body = {};
    f.forEach(function (v, k) { body[k] = v || null; });
    body.source = "website:" + location.hostname;
    fetch(api, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        form.reset();
        msg.textContent = "Thanks! Our front desk will email you shortly with a time.";
      })
      .catch(function () {
        msg.textContent = "Sorry, that didn't go through. Please call the office.";
      })
      .finally(function () { btn.disabled = false; });
  });
})();
