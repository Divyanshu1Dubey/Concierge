import json

html_path = r'C:\Users\DIVYANSHU\Desktop\concierge\Raleigh_Dentistry_Horizontal_Services2.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Get raw bundle text
bundle_start = html.find('<script id="bundle" type="application/json">')
bundle_content_start = bundle_start + len('<script id="bundle" type="application/json">')
app_script_start = html.find('function render')
bundle_end = html.rfind('</script>', bundle_content_start, app_script_start)
bundle_json_str = html[bundle_content_start:bundle_end]
print('Bundle length:', len(bundle_json_str))
print('Position 830-860:')
for i in range(830, 860):
    print(f'{i}: {repr(bundle_json_str[i])}')
print()
print('Contains </script>:', '</script>' in bundle_json_str)
print('Contains </scr substring:', '</scr' in bundle_json_str)
print('Contains <script>:', '<script>' in bundle_json_str)
print()
# Try to parse and show error location
try:
    bundle = json.loads(bundle_json_str)
    print('Bundle VALID')
except Exception as e:
    print('Bundle ERROR:', e)
    # Find the problematic character
    error_pos = 845
    print(f'Character at error position {error_pos}: {repr(bundle_json_str[error_pos])}')
    print(f'Context around error:')
    start = max(0, error_pos - 50)
    end = min(len(bundle_json_str), error_pos + 50)
    print(bundle_json_str[start:end])
