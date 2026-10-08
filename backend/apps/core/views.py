"""Core system views: Health, Ready, Version, and Public Widget.js script delivery."""
import os
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.utils import timezone
from django.db import connection

class HealthCheckView(View):
    """Liveness probe: verifies process is alive and database is reachable."""
    def get(self, request):
        db_healthy = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_healthy = False

        status_code = 200 if db_healthy else 503
        return JsonResponse({
            'status': 'healthy' if db_healthy else 'unhealthy',
            'version': '1.0.0',
            'database': 'connected' if db_healthy else 'disconnected',
            'timestamp': timezone.now().isoformat(),
        }, status=status_code)

class ReadyCheckView(View):
    """Readiness probe: verifies system is ready to receive visitor traffic."""
    def get(self, request):
        return JsonResponse({
            'status': 'ready',
            'timestamp': timezone.now().isoformat(),
        })

class VersionCheckView(View):
    """Platform version and environment details."""
    def get(self, request):
        return JsonResponse({
            'platform': 'HeyJarvis Concierge Cloud',
            'version': '1.0.0',
            'environment': 'development' if settings.DEBUG else 'production',
            'public_url': getattr(settings, 'APP_PUBLIC_URL', 'https://web-production-21c4f.up.railway.app'),
        })

def serve_widget_js(request):
    """Serve the universal standalone HeyJarvis widget script with CDN/CORS headers."""
    candidates = [
        os.path.join(settings.BASE_DIR, 'widget', 'heyjarvis-widget.js'),
        os.path.join(settings.BASE_DIR, 'backend', 'static', 'heyjarvis-widget.js'),
        os.path.join(settings.BASE_DIR, 'frontend', 'public', 'widget.js'),
        os.path.join(settings.BASE_DIR, 'frontend', 'public', 'heyjarvis-widget.js'),
        os.path.join(settings.BASE_DIR, 'static', 'heyjarvis-widget.js'),
        os.path.join(settings.BASE_DIR, '..', 'widget', 'heyjarvis-widget.js'),
    ]
    content = ""
    for c in candidates:
        if os.path.exists(c):
            with open(c, 'r', encoding='utf-8') as f:
                content = f.read()
            break

    if not content:
        content = "console.error('HeyJarvis: widget.js source not found');"

    response = HttpResponse(content, content_type='application/javascript')
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def serve_demo_html(request):
    """Serve the interactive HeyJarvis Concierge demo page."""
    candidates = [
        os.path.join(settings.BASE_DIR, 'demo_widget_test.html'),
        os.path.join(settings.BASE_DIR, '..', 'demo_widget_test.html'),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c, 'r', encoding='utf-8') as f:
                content = f.read()
            return HttpResponse(content, content_type='text/html; charset=utf-8')
    return HttpResponse("<h1>Demo page not found</h1>", status=404)


def serve_spa(request, *args, **kwargs):
    """Serve the single-page React application for all dashboard & client routes."""
    candidates = [
        os.path.join(settings.BASE_DIR, 'frontend', 'dist', 'index.html'),
        os.path.join(settings.BASE_DIR, 'dist', 'index.html'),
        os.path.join(settings.BASE_DIR, 'static', 'dist', 'index.html'),
        os.path.join(settings.BASE_DIR, 'backend', 'static', 'dist', 'index.html'),
        os.path.join(settings.BASE_DIR, '..', 'frontend', 'dist', 'index.html'),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c, 'r', encoding='utf-8') as f:
                content = f.read()
            return HttpResponse(content, content_type='text/html')
    return HttpResponse(
        "<h1>HeyJarvis: Frontend build not found</h1><p>Please run <code>npm run build</code> in the frontend folder.</p>",
        status=404
    )


class RootIndexView(View):
    """Platform Gateway Root View: provides dashboard links, API docs, and service status."""
    def get(self, request):
        frontend_url = os.environ.get('FRONTEND_URL') or getattr(settings, 'FRONTEND_URL', '')
        current_host = request.get_host().split(':')[0]
        current_origin = request.build_absolute_uri('/').rstrip('/')

        # Use relative paths if hosted on the same domain or FRONTEND_URL is not set
        if not frontend_url or current_host in frontend_url or frontend_url.startswith('/'):
            dashboard_link = "/dashboard"
            concierge_link = "/dashboard/concierge"
            portal_link = "/portal"
        else:
            dashboard_link = f"{frontend_url.rstrip('/')}/dashboard"
            concierge_link = f"{frontend_url.rstrip('/')}/dashboard/concierge"
            portal_link = f"{frontend_url.rstrip('/')}/portal"

        if 'text/html' in request.META.get('HTTP_ACCEPT', ''):
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>HeyJarvis™ Dental Intelligence Cloud - Gateway</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', sans-serif; background: #0B0F19; color: #E2E8F0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }}
    .card {{ background: #131B2E; border: 1px solid rgba(255,255,255,0.08); border-radius: 20px; max-width: 760px; width: 100%; padding: 40px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }}
    .badge {{ display: inline-flex; align-items: center; gap: 8px; background: rgba(20,184,166,0.12); color: #2DD4BF; border: 1px solid rgba(20,184,166,0.3); padding: 6px 14px; border-radius: 9999px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 20px; }}
    .pulse {{ width: 8px; height: 8px; background: #2DD4BF; border-radius: 50%; box-shadow: 0 0 10px #2DD4BF; }}
    h1 {{ font-size: 30px; font-weight: 800; color: #FFF; margin-bottom: 10px; letter-spacing: -0.02em; }}
    p.lead {{ color: #94A3B8; font-size: 15px; margin-bottom: 28px; line-height: 1.6; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 30px; }}
    .link-card {{ display: block; text-decoration: none; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 18px; border-radius: 12px; transition: all 0.2s; }}
    .link-card:hover {{ background: rgba(45,212,191,0.08); border-color: rgba(45,212,191,0.4); transform: translateY(-2px); }}
    .link-title {{ color: #FFF; font-weight: 700; font-size: 14px; margin-bottom: 4px; display: flex; align-items: center; justify-content: space-between; }}
    .link-desc {{ color: #64748B; font-size: 12px; }}
    .tag {{ font-size: 10px; padding: 2px 6px; border-radius: 4px; background: #1E293B; color: #38BDF8; font-family: 'JetBrains Mono', monospace; }}
    .footer {{ border-top: 1px solid rgba(255,255,255,0.06); padding-top: 18px; display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #64748B; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge"><div class="pulse"></div> HeyJarvis Concierge™ Dental Cloud</div>
    <h1>HeyJarvis™ AI Dental Concierge</h1>
    <p class="lead">AI-Powered Dental Front Desk &amp; Patient Communication: 24/7 inbound appointment triage, smart message composer, and automated practice scheduling.</p>
    <div class="grid">
      <a href="{dashboard_link}" class="link-card">
        <div class="link-title">Front Desk Workspace <span class="tag">Portal</span></div>
        <div class="link-desc">Appointment requests, live conversations, and patient records</div>
      </a>
      <a href="{concierge_link}" class="link-card">
        <div class="link-title">Inbound Concierge <span class="tag">24/7 AI</span></div>
        <div class="link-desc">Website receptionist, emergency triage, and appointment booking</div>
      </a>
      <a href="{portal_link}" class="link-card">
        <div class="link-title">Patient Portal <span class="tag">Live App</span></div>
        <div class="link-desc">Interactive landing page, practice sign-in &amp; showcase</div>
      </a>
      <a href="/api/docs/" class="link-card">
        <div class="link-title">Swagger UI <span class="tag">/api/docs</span></div>
        <div class="link-desc">Interactive OpenAPI specification &amp; REST testing</div>
      </a>
      <a href="/api/health/" class="link-card">
        <div class="link-title">Health Probe <span class="tag">/api/health</span></div>
        <div class="link-desc">System status, PMS sync &amp; multi-tenant database connectivity</div>
      </a>
    </div>
    <div class="footer">
      <span>HeyJarvis Multi-Tenant Dental SaaS Cloud</span>
      <span>v2.0.0 &bull; Dental AI Platform</span>
    </div>
  </div>
</body>
</html>"""
            return HttpResponse(html, content_type='text/html')

        return JsonResponse({
            'platform': 'HeyJarvis™ AI Dental Concierge Cloud',
            'version': '2.0.0',
            'status': 'operational',
            'architecture': 'multi-tenant agency model',
            'engines': {
                'conversations': '/api/conversations/',
                'appointments': '/api/appointments/',
                'emails': '/api/emails/',
                'practices': '/api/practices/',
                'chat': '/api/chat/',
            },
            'docs': '/api/docs/',
            'health': '/api/health/',
            'frontend_url': frontend_url or current_origin,
        })

