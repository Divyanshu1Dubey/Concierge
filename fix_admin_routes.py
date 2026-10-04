"""Fix admin_app route prefixes to remove double /api/admin."""
import re
from pathlib import Path

path = Path("src/saas/public_api.py")
content = path.read_text(encoding="utf-8")

# Pattern: @admin_app.METHOD("/api/admin/...)") -> @admin_app.METHOD("/...")
# These are the correct routes because admin_app is mounted at /api/admin in main.py
replacements = {
    '@admin_app.get("/api/admin/tenants')': '@admin_app.get("/tenants"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}")': '@admin_app.get("/tenants/{tenant_id}"',
    '@admin_app.patch("/api/admin/tenants/{tenant_id}")': '@admin_app.patch("/tenants/{tenant_id}"',
    '@admin_app.post("/api/admin/tenants/{tenant_id}/domains")': '@admin_app.post("/tenants/{tenant_id}/domains"',
    '@admin_app.post("/api/admin/domains/{domain_id}/verify")': '@admin_app.post("/domains/{domain_id}/verify"',
    '@admin_app.delete("/api/admin/domains/{domain_id}")': '@admin_app.delete("/domains/{domain_id}"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/domains")': '@admin_app.get("/tenants/{tenant_id}/domains"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/leads")': '@admin_app.get("/tenants/{tenant_id}/leads"',
    '@admin_app.get("/api/admin/leads/{lead_id}")': '@admin_app.get("/leads/{lead_id}"',
    '@admin_app.patch("/api/admin/leads/{lead_id}")': '@admin_app.patch("/leads/{lead_id}"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/conversations")': '@admin_app.get("/tenants/{tenant_id}/conversations"',
    '@admin_app.get("/api/admin/conversations/{conversation_id}/messages")': '@admin_app.get("/conversations/{conversation_id}/messages"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/analytics")': '@admin_app.get("/tenants/{tenant_id}/analytics"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/widget")': '@admin_app.get("/tenants/{tenant_id}/widget"',
    '@admin_app.put("/api/admin/tenants/{tenant_id}/widget")': '@admin_app.put("/tenants/{tenant_id}/widget"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/email")': '@admin_app.get("/tenants/{tenant_id}/email"',
    '@admin_app.put("/api/admin/tenants/{tenant_id}/email")': '@admin_app.put("/tenants/{tenant_id}/email"',
    '@admin_app.post("/api/admin/tenants/{tenant_id}/email/test")': '@admin_app.post("/tenants/{tenant_id}/email/test"',
    '@admin_app.post("/api/admin/tenants/{tenant_id}/email/test-smtp")': '@admin_app.post("/tenants/{tenant_id}/email/test-smtp"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/templates")': '@admin_app.get("/tenants/{tenant_id}/templates"',
    '@admin_app.put("/api/admin/tenants/{tenant_id}/templates/{template_name}")': '@admin_app.put("/tenants/{tenant_id}/templates/{template_name}"',
    '@admin_app.get("/api/admin/template-variables")': '@admin_app.get("/template-variables"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/business-rules")': '@admin_app.get("/tenants/{tenant_id}/business-rules"',
    '@admin_app.put("/api/admin/tenants/{tenant_id}/business-rules")': '@admin_app.put("/tenants/{tenant_id}/business-rules"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/settings")': '@admin_app.get("/tenants/{tenant_id}/settings"',
    '@admin_app.put("/api/admin/tenants/{tenant_id}/settings")': '@admin_app.put("/tenants/{tenant_id}/settings"',
    '@admin_app.get("/admin/dashboard/{tenant_id}")': '@admin_app.get("/dashboard/{tenant_id}"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/audit")': '@admin_app.get("/tenants/{tenant_id}/audit"',
    '@admin_app.post("/api/admin/tenants/{tenant_id}/api-keys")': '@admin_app.post("/tenants/{tenant_id}/api-keys"',
    '@admin_app.delete("/api/admin/api-keys/{key_id}")': '@admin_app.delete("/api-keys/{key_id}"',
    '@admin_app.post("/api/admin/tenants/{tenant_id}/members")': '@admin_app.post("/tenants/{tenant_id}/members"',
    '@admin_app.get("/api/admin/tenants/{tenant_id}/members")': '@admin_app.get("/tenants/{tenant_id}/members"',
    '@admin_app.delete("/api/admin/members/{membership_id}")': '@admin_app.delete("/members/{membership_id}"',
    '@admin_app.post("/api/admin/auth/login")': '@admin_app.post("/auth/login"',
}

count = 0
for old, new in replacements.items():
    if old in content:
        content = content.replace(old, new)
        count += 1

path.write_text(content, encoding="utf-8")
print(f"Fixed {count} routes")

# Verify
import re
matches = re.findall(r'@admin_app\.(get|post|patch|delete)\(["\']\/api\/admin', content)
if matches:
    print(f"WARNING: {len(matches)} routes still have double prefix:")
    for m in matches[:5]:
        print(f"  {m}")
else:
    print("All admin_app route prefixes fixed!")

# Check no leading slash routes on admin_app (except dashboard)
bad = re.findall(r'@admin_app\.(get|post|patch|delete)\(["\']/[^a]', content)
if bad:
    print(f"Note: found {len(bad)} non-/api/admin routes (check if intentional)")
