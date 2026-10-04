import re, json

html_path = r'C:\Users\DIVYANSHU\Desktop\concierge\Raleigh_Dentistry_Horizontal_Services1.html'
widget_path = r'C:\Users\DIVYANSHU\Desktop\concierge\src\concierge\static\widget-production.js'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()
with open(widget_path, 'r', encoding='utf-8') as f:
    widget = f.read()

# Locate bundle boundaries safely
bundle_start = html.find('<script id="bundle" type="application/json">')
bundle_content_start = bundle_start + len('<script id="bundle" type="application/json">')
app_script_start = html.find('function render')
if app_script_start == -1:
    app_script_start = len(html)
bundle_end = html.rfind('</script>', bundle_content_start, app_script_start)
if bundle_end == -1:
    bundle_end = html.find('</script>', bundle_content_start)

bundle_json_str = html[bundle_content_start:bundle_end]
bundle = json.loads(bundle_json_str)

# Remove widget from ALL pages in bundle
for route in list(bundle['pages'].keys()):
    page = bundle['pages'][route]
    if 'hj-launcher' in page or 'HeyJarvis' in page:
        page = re.sub(r'<script>\s*/\* HeyJarvis Concierge.*?</script>\s*', '', page, flags=re.DOTALL)
        bundle['pages'][route] = page
        print(f'Removed widget from {route}')

new_bundle_json = json.dumps(bundle, ensure_ascii=False)
html = html[:bundle_content_start] + new_bundle_json + html[bundle_end:]

# Remove broken widget replace from render function
render_idx = html.find('function render')
if render_idx >= 0:
    render_end = html.find('window.addEventListener', render_idx)
    render_func = html[render_idx:render_end]
    render_func = re.sub(
        r"html=html\.replace\('\n<script>\n/\* HeyJarvis.*?</script>','<script>'\+init\+bundle\.js\+'\\n'\+bridge\+'</scr'\+'ipt></body>'\);",
        '',
        render_func,
        flags=re.DOTALL
    )
    html = html[:render_idx] + render_func + html[render_end:]
    print('Fixed render function')

# Build iframe injector
injector = """
(function() {
  'use strict';
  try {
    var frame = document.getElementById('site');
    if (!frame) return;
    function injectWidget() {
      try {
        var doc = frame.contentDocument || frame.contentWindow.document;
        if (!doc || !doc.body) return false;
        var s = doc.createElement('script');
        s.textContent = WIDGET_PLACEHOLDER;
        doc.body.appendChild(s);
        console.log('[HeyJarvis] Widget injected into iframe');
        return true;
      } catch(e) { return false; }
    }
    if (!injectWidget()) {
      var obs = new MutationObserver(function(_, observer) {
        if (injectWidget()) observer.disconnect();
      });
      obs.observe(frame, { attributes: true, attributeFilter: ['srcdoc'] });
      setTimeout(function() { if (injectWidget()) obs.disconnect(); }, 1000);
    }
  } catch(e) {
    console.error('[HeyJarvis] Injector error:', e);
  }
})();
"""

# Escape widget for JS string literal inside the injector
escaped = widget.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
injector = injector.replace('WIDGET_PLACEHOLDER', escaped)

# Inject after app script - find the ACTUAL </body> at end of file
last_script_close = html.rfind('</script>')
# Find last </body> in file (not ones inside bundle JSON)
body_end = html.rfind('</body>')
if last_script_close >= 0 and body_end >= 0 and last_script_close < body_end:
    inject_pos = last_script_close + len('</script>')
    html = html[:inject_pos] + '\n<script>\n' + injector + '\n</script>\n' + html[inject_pos:]
    print('Added iframe injector')
else:
    print(f'Could not inject: last_script={last_script_close}, body_end={body_end}')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Final size:', len(html))
print('Has widget in bundle:', 'hj-launcher' in html)
print('Has injector:', 'injectWidget' in html)
