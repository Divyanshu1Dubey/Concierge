"""Platform FastAPI app: mounts public + admin routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from saas.config import get_settings
from saas.public_api import admin_app, public_app
from saas.repositories import get_tenant_by_slug

settings = get_settings()
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "saas" / "static"
STATIC.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="HeyJarvis Concierge Platform", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="saas-static")
app.mount("/api", public_app)
app.mount("/api/admin", admin_app)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/")
def index() -> dict:
    return {"app": "heyjarvis-platform", "docs": "/docs"}


@app.get("/concierge/{tenant_slug}")
def hosted_concierge(tenant_slug: str) -> HTMLResponse:
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    path = ROOT / "saas" / "templates" / "hosted.html"
    html = path.read_text(encoding="utf-8").replace("{tenant_name}", tenant.name).replace("{client_key}", _public_key(tenant.id))
    return HTMLResponse(html)


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
