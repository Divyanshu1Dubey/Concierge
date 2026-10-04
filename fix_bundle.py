import json, re, base64

html_path = r'C:\Users\DIVYANSHU\Desktop\concierge\Raleigh_Dentistry_Horizontal_Services2.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Get bundle from base64
bundle_start = html.find('<script id="bundle" type="application/json" data-b64="1">')
bundle_content_start = bundle_start + len('<script id="bundle" type="application/json" data-b64="1">')
bundle_end = html.find('</script>', bundle_content_start)
bundle_b64 = html[bundle_content_start:bundle_end]

bundle_json = base64.b64decode(bundle_b64).decode('utf-8')
bundle = json.loads(bundle_json)

# Remove ALL widget remnants from ALL pages
for route, page in list(bundle['pages'].items()):
    original_len = len(page)

    # Remove all remaining HeyJarvis widget code
    # Pattern: from var css = to the end of the IIFE
    page = re.sub(
        r'var css =[\s\S]*?}\)\(\);',
        '',
        page
    )

    # Remove all hj- CSS rules
    page = re.sub(r'#hj-[a-z-]+\{[^}]+\}', '', page)
    page = re.sub(r'\.hj-[a-z-]+\{[^}]+\}', '', page)

    # Remove any remaining console.error about HeyJarvis
    page = re.sub(r"console\.error\('\[HeyJarvis\][^)]*'\);", '', page)
    page = re.sub(r"console\.error\('\[HeyJarvis\][^}]*\}", '', page)

    if len(page) != original_len:
        print('Removed widget remnants from ' + route + ' (' + str(original_len - len(page)) + ' bytes)')

    bundle['pages'][route] = page

# Verify
page = bundle['pages']['/']
heyjarvis_count = page.count('HeyJarvis')
hj_launcher = page.count('hj-launcher')
hj_css = page.count('hj-')

print('Root page: HeyJarvis=' + str(heyjarvis_count) + ', hj-launcher=' + str(hj_launcher) + ', hj-=' + str(hj_css))

# Re-encode bundle
new_bundle_json = json.dumps(bundle, ensure_ascii=False)
new_bundle_b64 = base64.b64encode(new_bundle_json.encode('utf-8')).decode('ascii')

# Update HTML
html = html[:bundle_content_start] + new_bundle_b64 + html[bundle_end:]

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Removed all widget remnants from bundle')
print('New bundle base64 length: ' + str(len(new_bundle_b64)))
