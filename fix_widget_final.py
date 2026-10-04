import re

html_path = r'C:\Users\DIVYANSHU\Desktop\concierge\Raleigh_Dentistry_Horizontal_Services1.html'
widget_path = r'C:\Users\DIVYANSHU\Desktop\concierge\src\concierge\static\widget-production.js'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()
with open(widget_path, 'r', encoding='utf-8') as f:
    widget = f.read()

# Find and fix the app script
import re
scripts = re.findall(r'<script[^>]*>.*?</script>', html, re.DOTALL)
app_script = None
for s in scripts:
    if 'function render' in s and 'bundle.pages' in s:
        app_script = s
        break

if app_script:
    # Remove the broken widget replace line from render function
    # The line is: html=html.replace('\n<script>\n/* HeyJarvis...','<script>'+init+bundle.js+'\n'+bridge+'</scr'+'ipt></body>');
    bad_replace = "html=html.replace('\\n<script>\\n/* HeyJarvis Concierge"
    if bad_replace in app_script:
        # Find the full replace statement
        start = app_script.find(bad_replace)
        # Find the end of this statement (semicolon)
        end = app_script.find(';', start) + 1
        broken_code = app_script[start:end]
        print(f'Removing broken replace: {len(broken_code)} chars')
        print(f'Broken code preview: {repr(broken_code[:100])}...')
        # Remove it
        app_script = app_script.replace(broken_code, '')
        print('Removed broken replace from app script')
    else:
        print('Broken replace not found in app script')

    # Replace the old app script with fixed one
    html = html.replace(scripts[scripts.index(app_script) - len(scripts)], app_script)
    # Actually need to find the exact match in html
    old_app_script = None
    for s in scripts:
        if 'function render' in s and 'bundle.pages' in s:
            old_app_script = s
            break
    if old_app_script:
        html = html.replace(old_app_script, app_script)
        print('Replaced app script in HTML')

# Now fix the injector - it has the widget text embedded with bad escaping
# Find the injector script
injector_start = html.find('<script>\n\n(function() {\n  \'use strict\';\n  try {\n    var frame = document.getElementById(\'site\');')
if injector_start >= 0:
    injector_end = html.find('</script>', injector_start) + len('</script>')
    old_injector = html[injector_start:injector_end]
    print(f'Found injector: {len(old_injector)} chars')

    # Create a proper injector that reads widget from a separate file
    new_injector = '''<script>
(function() {
  'use strict';
  try {
    var frame = document.getElementById('site');
    if (!frame) return;

    function injectWidget() {
      try {
        var doc = frame.contentDocument || frame.contentWindow.document;
        if (!doc || !doc.body) return false;

        var script = doc.createElement('script');
        script.src = 'widget-injector.js';
        doc.body.appendChild(script);
        console.log('[HeyJarvis] Widget injected into iframe');
        return true;
      } catch(e) {
        console.error('[HeyJarvis] Injection failed:', e);
        return false;
      }
    }

    // Try immediately
    if (!injectWidget()) {
      // Watch for iframe to populate
      var observer = new MutationObserver(function(_, obs) {
        if (injectWidget()) obs.disconnect();
      });
      observer.observe(frame, {
        attributes: true,
        attributeFilter: ['srcdoc']
      });

      // Fallback timeout
      setTimeout(function() {
        if (injectWidget()) observer.disconnect();
      }, 1000);
    }
  } catch(e) {
    console.error('[HeyJarvis] Injector error:', e);
  }
})();
</script>'''

    html = html.replace(old_injector, new_injector)
    print('Replaced injector with file-based version')
else:
    print('Injector not found')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Fixed HTML size:', len(html))

# Also write the widget injector file
with open(r'C:\Users\DIVYANSHU\Desktop\concierge\widget-injector.js', 'w', encoding='utf-8') as f:
    f.write(widget)
print('Wrote widget-injector.js')
