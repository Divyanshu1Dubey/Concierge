"""Platform FastAPI app: mounts public + admin routes."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from saas.config import get_settings
from saas.database import connect, rows
from saas.public_api import admin_app, frontdesk_app, public_app, _tenant_config, admin_login, public_tenant_login
from saas.repositories import get_tenant_by_slug, ensure_demo_data

settings = get_settings()


def _check_production_secrets() -> None:
    """Refuse to boot in production with placeholder secrets (forgeable logins, readable SMTP passwords)."""
    if not settings.is_production:
        return
    weak = []
    if settings.jwt_secret.startswith("change-me") or len(settings.jwt_secret) < 32:
        weak.append("JWT_SECRET")
    enc = settings.encryption_key.get_secret_value()
    if enc.startswith("change-me") or len(enc) < 32:
        weak.append("ENCRYPTION_KEY")
    if weak:
        raise RuntimeError(f"APP_ENV=production but {', '.join(weak)} unset or too weak (need 32+ random chars)")


_check_production_secrets()
ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src" / "saas" / "static"
STATIC.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("heyjarvis.scheduler")
SCHEDULER_INTERVAL_S = int(os.environ.get("CONCIERGE_SCHEDULER_INTERVAL", "120"))
_last_tick_ok: float | None = None  # time.monotonic() of the last clean tick; /health reports its age


def scheduler_tick() -> None:
    """Pull patient replies from every connected clinic mailbox, then draft any follow-ups that are due."""
    global _last_tick_ok
    from saas import cadence, mailbox
    ok = True
    try:
        tenants = mailbox.connected_tenants()
    except Exception:  # e.g. a locked database: still run the cadence below
        log.exception("listing connected mailboxes failed")
        tenants, ok = [], False
    for tenant_id in tenants:
        try:
            mailbox.sync_mailbox(tenant_id)
        except Exception as e:  # one clinic's bad password must not stop the others
            log.warning("mailbox sync failed for tenant %s: %s", tenant_id, e)
    try:
        cadence.run_due()
    except Exception:
        log.exception("cadence run failed")
        ok = False
    if ok:
        _last_tick_ok = time.monotonic()


async def _scheduler_loop() -> None:
    while True:
        await asyncio.sleep(SCHEDULER_INTERVAL_S)
        try:
            await run_in_threadpool(scheduler_tick)
        except Exception:  # an escaped error would end the task and silently stop every follow-up
            log.exception("scheduler tick failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Single-process scheduler: run one web worker (the Procfile does), or set CONCIERGE_SCHEDULER=0
    # on extra workers so mailboxes aren't polled twice.
    try:
        from saas.database import migrate
        migrate()
        # Demo clinic with known logins: local/dev only, never in production.
        if not settings.is_production or os.environ.get("CONCIERGE_DEMO") == "1":
            ensure_demo_data()
    except Exception as e:
        log.warning("startup migration/demo seed: %s", e)
    task = asyncio.create_task(_scheduler_loop()) if os.environ.get("CONCIERGE_SCHEDULER", "1") != "0" else None
    yield
    if task:
        task.cancel()


_docs = not settings.is_production
app = FastAPI(title="HeyJarvis Concierge Platform", version="1.0.0", lifespan=lifespan,
              docs_url="/docs" if _docs else None, redoc_url="/redoc" if _docs else None,
              openapi_url="/openapi.json" if _docs else None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Legacy/dev surfaces a production server never serves: the old admin page (renders patient fields unescaped and
# reads a token from the URL hash), the install notes (docs/ isn't in the image) and every mounted app's API docs.
_DEV_ONLY_PATHS = frozenset(
    ["/admin", "/admin.html", "/install"]
    + [prefix + p for prefix in ("", "/api", "/api/admin", "/api/admin/fd")
       for p in ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json")]
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    path = re.sub(r"/{2,}", "/", request.url.path)
    if get_settings().is_production and path in _DEV_ONLY_PATHS:
        response: Response = JSONResponse({"detail": "Not Found"}, status_code=404)
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # uvicorn --proxy-headers sets the scheme from X-Forwarded-Proto; the header check covers runs without it.
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if request.url.scheme == "https" or forwarded == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    # Staff pages and APIs can't be framed by other sites. /concierge/{slug} stays frameable: clinics may iframe it.
    if path.startswith(("/frontdesk", "/api/admin")):
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


_RETIRED_BUNDLE = os.path.realpath(STATIC / "dist").casefold()


class _Static(StaticFiles):
    """/static without the retired React bundle (static/dist) in production."""

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        full_path, stat_result = super().lookup_path(path)
        # Judge the file actually resolved, not the URL: '/static/..%2fstatic/dist/...' reaches dist/ too.
        # casefold: macOS and Windows file systems also open 'DIST/'.
        real = os.path.realpath(full_path).casefold() if full_path else ""
        if real and get_settings().is_production and (real == _RETIRED_BUNDLE
                                                      or real.startswith(_RETIRED_BUNDLE + os.sep)):
            return "", None  # -> 404
        return full_path, stat_result


app.mount("/static", _Static(directory=str(STATIC)), name="saas-static")
app.mount("/api/admin", admin_app)
admin_app.mount("/fd", frontdesk_app)
app.mount("/api", public_app)


@app.post("/api/auth/login")
@app.post("/auth/login")
async def app_login_alias(request: Request):
    return await admin_login(request)


@app.post("/api/auth/token")
@app.post("/auth/token")
async def app_token_alias(request: Request):
    return await public_tenant_login(request)


@app.get("/widget.js")
def widget_js() -> FileResponse:
    # The install snippet loads {APP_URL}/widget.js and the widget derives its API base from that URL.
    return FileResponse(STATIC / "widget.js", media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=300"})


@app.get("/oauth/google/callback")
def google_callback(request: Request, code: str | None = None, state: str | None = None,
                    error: str | None = None) -> RedirectResponse:
    """Google sends the clinic back here after the consent screen."""
    from urllib.parse import quote

    from saas import google_oauth, mailbox
    from saas.repositories import audit, get_user

    def back(msg: str | None) -> RedirectResponse:
        resp = RedirectResponse("/frontdesk/settings" + (f"?mailbox_error={quote(msg)}" if msg else "?mailbox=connected"),
                                status_code=303)
        resp.delete_cookie(google_oauth.STATE_COOKIE, path="/oauth/google")  # single use
        return resp

    if error or not code or not state:
        return back("Google sign-in was cancelled." if error == "access_denied" else "Google sign-in did not finish.")
    try:
        claims = google_oauth.read_state(state)
        import hmac
        if not hmac.compare_digest(request.cookies.get(google_oauth.STATE_COOKIE, ""), str(claims.get("n", ""))):
            return back("This sign-in link was started in a different browser. Start again from Settings.")
        user = get_user(int(claims["uid"]))
        if not user or user.tenant_id != int(claims["tid"]) or user.role not in ("owner", "admin"):
            return back("Only a clinic owner or admin can connect the mailbox.")
        tok = google_oauth.exchange_code(code)
    except google_oauth.OAuthError as e:
        return back(str(e))
    tenant_id = int(claims["tid"])
    mailbox.connect_gmail_oauth(tenant_id, tok["email"], tok["refresh_token"], from_name=claims.get("fn") or None)
    google_oauth.remember(tenant_id, tok["access_token"], tok["expires_in"])
    audit(tenant_id, user.id, "mailbox_connected", {"address": tok["email"], "method": "google_oauth"})
    return back(None)


@app.get("/health")
def health() -> dict:
    # Always ok (it's the platform healthcheck); a growing tick age means follow-ups and reply tracking stalled.
    age = None if _last_tick_ok is None else round(time.monotonic() - _last_tick_ok)
    return {"ok": True, "scheduler_last_tick_age_s": age}


@app.get("/")
def index(request: Request) -> Response:
    accept = request.headers.get("accept", "").lower()
    format_param = request.query_params.get("format", "").lower()
    if format_param == "json" or ("application/json" in accept and "text/html" not in accept):
        return JSONResponse({"app": "heyjarvis-platform", "docs": "/docs", "portal": "/", "frontdesk": "/frontdesk", "admin": "/admin"})
    from saas.repositories import _demo_allowed
    if not _demo_allowed():  # production: no developer portal (it lists demo logins)
        return RedirectResponse(url="/frontdesk", status_code=307)
    portal_file = ROOT / "src" / "saas" / "templates" / "portal.html"
    if portal_file.exists():
        return HTMLResponse(portal_file.read_text(encoding="utf-8"))
    return JSONResponse({"app": "heyjarvis-platform", "docs": "/docs"})


@app.get("/portal")
@app.get("/portal.html")
def portal_page() -> Response:
    from saas.repositories import _demo_allowed
    if not _demo_allowed():
        return RedirectResponse(url="/frontdesk", status_code=307)
    portal_file = ROOT / "src" / "saas" / "templates" / "portal.html"
    return HTMLResponse(portal_file.read_text(encoding="utf-8"))


@app.get("/concierge")
@app.get("/concierge/")
@app.get("/chat")
@app.get("/chat/")
def concierge_default_redirect() -> RedirectResponse:
    return RedirectResponse(url="/concierge/raleigh-dental-demo", status_code=307)


@app.get("/concierge/{tenant_slug}")
def hosted_concierge(tenant_slug: str) -> HTMLResponse:
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    path = ROOT / "src" / "saas" / "templates" / "hosted.html"
    import html as _html
    # Clinic names are editable by clinic staff: escape before putting them into the patient-facing page.
    html = path.read_text(encoding="utf-8").replace("{tenant_name}", _html.escape(tenant.name, quote=True)) \
        .replace("{client_key}", _html.escape(_public_key(tenant.id), quote=True))
    return HTMLResponse(html)


@app.get("/desk")
@app.get("/desk/")
@app.get("/app")
@app.get("/app/")
def legacy_desk_redirect() -> RedirectResponse:
    # The React desk is retired; the approved front desk is /frontdesk.
    return RedirectResponse(url="/frontdesk", status_code=307)


@app.get("/frontdesk")
def frontdesk_page() -> HTMLResponse:
    """Simple inbox for the front desk: who needs a reply, the reply, Approve & send."""
    return HTMLResponse((ROOT / "src" / "saas" / "templates" / "desk.html").read_text(encoding="utf-8"))


@app.get("/frontdesk/settings")
def frontdesk_settings_page() -> HTMLResponse:
    """Clinic details, email connection, team and follow-up schedule."""
    return HTMLResponse((ROOT / "src" / "saas" / "templates" / "settings.html").read_text(encoding="utf-8"))


@app.get("/frontdesk/full")
def frontdesk_full_page() -> HTMLResponse:
    """Detailed view: settings, cadence editor, mailbox connection, notes and tasks."""
    return HTMLResponse((ROOT / "src" / "saas" / "templates" / "frontdesk.html").read_text(encoding="utf-8"))


@app.get("/admin")
@app.get("/admin.html")
def admin_page() -> HTMLResponse:
    path = ROOT / "src" / "saas" / "templates" / "admin.html"
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/install")
def install_guide() -> HTMLResponse:
    path = ROOT / "docs" / "installation.md"
    markdown = path.read_text(encoding="utf-8")
    app_url = str(settings.app_url).rstrip("/")
    snippet = (
        "<script\n"
        "  async\n"
        "  src=\"{app_url}/widget.js\"\n"
        "  data-heyjarvis-client=\"YOUR_PUBLIC_KEY\"\n"
        "  data-heyjarvis-form=\"false\"\n"
        "  data-heyjarvis-auto-open=\"false\"\n"
        "></script>"
    ).replace("{app_url}", app_url)
    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Installation Guide — HeyJarvis Concierge</title>"
        "<style>"
        ":root{--primary:#1f3b2e;--accent:#3a7d6e;--bg:#f6f7f8;--card:#fff;--border:#e5e7eb;--text:#1a1a1a;--muted:#6b7280;}"
        "*{box-sizing:border-box;margin:0;padding:0;}"
        "body{font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif;background:var(--bg);color:var(--text);}"
        ".wrap{max-width:860px;margin:0 auto;padding:24px;}"
        ".header{padding:20px 24px;background:linear-gradient(135deg,#1a3c2a 0%,#2d6a4f 100%);color:#fff;border-radius:14px;margin-bottom:18px;}"
        ".header h1{font-size:22px;margin-bottom:6px;}.header p{opacity:.85;font-size:14px;}"
        ".card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;margin-bottom:16px;box-shadow:0 2px 6px rgba(0,0,0,.04);}"
        ".card h2{font-size:16px;margin-bottom:10px;}.card p{color:#374151;margin-bottom:10px;}"
        ".code{background:#f5f5f5;border:1px solid #ddd;border-radius:10px;padding:12px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:13px;word-break:break-all;white-space:pre-wrap;color:#1f3b2e;}"
        ".btn{display:inline-block;margin-top:8px;padding:9px 14px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:0;background:var(--primary);color:#fff;}"
        "ol,ul{margin-left:18px;margin-bottom:12px;color:#374151;}li{margin-bottom:6px;}"
        "a{color:var(--primary);}@media(max-width:420px){.wrap{padding:14px;}}"
        "</style></head><body><div class=\"wrap\">"
        "<div class=\"header\"><h1>Installation Guide</h1><p>Add HeyJarvis Concierge to your website in minutes.</p></div>"
        "<div class=\"card\"><h2>Quick Start</h2><p>Paste this snippet before <code>&lt;/body&gt;</code> and replace <code>YOUR_PUBLIC_KEY</code> with your public API key from the HeyJarvis dashboard.</p>"
        "<div class=\"code\">" + snippet + "</div>"
        "<button class=\"btn\" onclick=\"navigator.clipboard.writeText(this.parentElement.querySelector('.code').textContent).then(()=>alert('Copied!'))\">Copy snippet</button>"
        "</div>"
        + markdown
        + "</div></body></html>"
    )
    return HTMLResponse(html)


@app.get("/api/v1/public/widget-config/{tenant_slug}")
def public_widget_config(tenant_slug: str, request: Request) -> dict:
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or not tenant.enabled:
        raise HTTPException(status_code=404, detail="tenant not found")
    origin = request.headers.get("origin", "").replace("https://", "").replace("http://", "").split("/")[0].lower()
    domain_ok = False
    if origin:
        with connect() as c:
            d = rows(c, "SELECT 1 FROM domains WHERE tenant_id = ? AND domain = ?", tenant.id, origin)
        domain_ok = bool(d)
    cfg = _tenant_config(tenant.id)
    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "tenant_slug": tenant.slug,
        "greeting": cfg.get("greeting"),
        "allowed_origin": domain_ok,
        "widget_config": cfg,
    }


def _public_key(tenant_id: int) -> str:
    import sqlite3
    from saas.database import db_path
    path = db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute("SELECT public_key FROM api_keys WHERE tenant_id = ? LIMIT 1", (tenant_id,)).fetchone()
        return r["public_key"] if r else ""
    finally:
        conn.close()
