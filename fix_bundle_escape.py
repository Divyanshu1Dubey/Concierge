import re, json

html_path = r'C:\Users\DIVYANSHU\Desktop\concierge\Raleigh_Dentistry_Horizontal_Services2.html'
widget_path = r'C:\Users\DIVYANSHU\Desktop\concierge\src\concierge\static\widget-production.js'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()
with open(widget_path, 'r', encoding='utf-8') as f:
    widget = f.read()

# 1. Find bundle boundaries
bundle_start = html.find('<script id="bundle" type="application/json">')
bundle_content_start = bundle_start + len('<script id="bundle" type="application/json">')
app_script_start = html.find('function render')
bundle_end = html.rfind('</script>', bundle_content_start, app_script_start)

bundle_json_str = html[bundle_content_start:bundle_end]
bundle = json.loads(bundle_json_str)

# 2. Remove widget from all pages if present
for route in list(bundle['pages'].keys()):
    page = bundle['pages'][route]
    if 'hj-launcher' in page or 'HeyJarvis' in page:
        page = re.sub(r'<script>\s*/\* HeyJarvis Concierge.*?</script>\s*', '', page, flags=re.DOTALL)
        bundle['pages'][route] = page
        print(f'Removed widget from {route}')

# 3. Write external widget file
widget_out = r'C:\Users\DIVYANSHU\Desktop\concierge\widget-loader.js'
with open(widget_out, 'w', encoding='utf-8') as f:
    f.write(widget)
print('Wrote widget-loader.js')

# 4. Inject external loader script at end of body
loader_script = '<script src="widget-loader.js" data-heyjarvis-api="http://localhost:8000" async></script>'
last_body = html.rfind('</body>')
if last_body >= 0:
    html = html[:last_body] + loader_script + '\n' + html[last_body:]
    print('Added external widget loader')

# 5. Serialize bundle - escape </script> to prevent browser from closing the JSON script tag
new_bundle_json = json.dumps(bundle, ensure_ascii=False)
# Escape </script> sequences in the JSON to prevent HTML parser from closing the script tag
new_bundle_json = new_bundle_json.replace('</script>', '<\\/script>')

# 6. Write back to HTML
html = html[:bundle_content_start] + new_bundle_json + html[bundle_end:]

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Final HTML size:', len(html))

# 7. Verify the fix worked
with open(html_path, 'r', encoding='utf-8') as f:
    verify_html = f.read()
verify_bundle = verify_html[bundle_content_start:bundle_content_start + 1000]
print('First 1000 chars of bundle include </script>:', '</script>' in verify_bundle)
print('First 1000 chars include <\\/script>:', '<\\/script>' in verify_bundle)
