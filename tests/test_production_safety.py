"""Guards against demo shortcuts leaking into production."""

from __future__ import annotations

import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient

from saas.config import get_settings
from saas.repositories import create_tenant, create_user, get_tenant_by_slug


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.delenv("CONCIERGE_DEMO", raising=False)


def test_no_demo_clinic_in_production(production):
    assert get_tenant_by_slug("raleigh-dental-demo") is None
    from saas.repositories import ensure_demo_data
    with pytest.raises(RuntimeError):
        ensure_demo_data()


def test_unknown_clinic_id_does_not_fall_back_to_only_clinic():
    from saas.main import app
    t = create_tenant(slug=f"only-{uuid.uuid4().hex[:6]}", name="Only")
    create_user(t.id, "a@x.test", password="pw-123456")
    r = TestClient(app).post("/api/admin/auth/login", json={"tenant_slug": "typo", "email": "a@x.test", "password": "pw-123456"})
    assert r.status_code == 404


def test_no_hardcoded_mail_credentials_in_source():
    src = pathlib.Path(__file__).resolve().parents[1] / "src"
    for f in src.rglob("*.py"):
        text = f.read_text()
        assert "iapjgasrmazuzqgd" not in text and "parulmaterial@" not in text, f
