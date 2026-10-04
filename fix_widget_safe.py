import re
import json

html_path = r'C:\Users\DIVYANSHU\Desktop\concierge\Raleigh_Dentistry_Horizontal_Services2.html'
widget_path = r'C:\Users\DIVYANSHU\Desktop\concierge\src\concierge\static\widget-production.js'
widget_out_path = r'C:\Users\DIVYANSHU\Desktop\concierge\widget-loader.js'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()
with open(widget_path, 'r', encoding='utf-8') as f:
    widget = f.read()

# 1. Find bundle boundaries - use rfind to get the correct closing </script>
bundle_start = html.find('<script id="bundle" type="application/json">')
bundle_content_start = bundle_start + len('<script id="bundle" type="application/json">')
app_script_start = html.find('function render')
bundle_end = html.rfind('</script>', bundle_content_start, app_script_start)

bundle_json_str = html[bundle_content_start:bundle_end]
bundle = json.loads(bundle_json_str)

# 2. Remove widget from ALL pages in bundle (it breaks the JSON)
for route in list(bundle['pages'].keys()):
    page = bundle['pages'][route]
    if 'hj-launcher' in page or 'HeyJarvis' in page:
        # Remove the widget script tag
        page = re.sub(r'<script>\s*/\* HeyJarvis Concierge.*?</script>\s*', '', page, flags=re.DOTALL)
        bundle['pages'][route] = page
        print(f'Removed widget from {route}')

new_bundle_json = json.dumps(bundle, ensure_ascii=False)
html = html[:bundle_content_start] + new_bundle_json + html[bundle_end:]
print('Bundle cleaned')

# 3. Save widget as separate file
with open(widget_out_path, 'w', encoding='utf-8') as f:
    f.write(widget)
print(f'Saved widget to {widget_out_path}')

# 4. Add an iframe injector script that loads the widget file
injector = """<script>
(function() {
  'use strict';
  try {
    var frame = document.getElementById('site');
    if (!frame) return;

    function injectWidget() {
      try {
        var doc = frame.contentDocument || frame.contentWindow.document;
        if (!doc || !doc.body) return false;

        // Create script element pointing to the widget file
        var script = doc.createElement('script');
        script.src = 'widget-loader.js';
        doc.body.appendChild(script);
        console.log('[HeyJarvis] Widget loader injected into iframe');
        return true;
      } catch(e) {
        console.error('[HeyJarvis] Injection failed:', e);
        return false;
      }
    }

    // Try immediately in case iframe is already loaded
    if (!injectWidget()) {
      // Watch for iframe to populate via srcdoc attribute
      var observer = new MutationObserver(function(_, obs) {
        if (injectWidget()) {
          obs.disconnect();
        }
      });
      observer.observe(frame, {
        attributes: true,
        attributeFilter: ['srcdoc']
      });

      // Fallback: try after a short delay
      setTimeout(function() {
        if (injectWidget()) {
          observer.disconnect();
        }
      }, 500);
    }
  } catch(e) {
    console.error('[HeyJarvis] Injector error:', e);
  }
})();
</script>"""

# Insert after the app script's closing </script>, before </body>
last_script_close = html.rfind('</script>')
body_end = html.rfind('</body>')

if last_script_close >= 0 and body_end >= 0 and last_script_close < body_end:
    inject_pos = body_end
    html = html[:inject_pos] + injector + html[inject_pos:]
    print('Added iframe injector')
else:
    print(f'Could not find injection point: last_script={last_script_close}, body_end={body_end}')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Fixed HTML size: {len(html)}')
print(f'Has widget in bundle: {"hj-launcher" in html}')
print(f'Has injector: {"injectWidget" in html}')
