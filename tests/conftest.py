import pytest


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real API calls or emails, and a fresh database + outbox per test."""
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "SMTP_PASSWORD", "CONCIERGE_AUTO_CONFIRM"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CONCIERGE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("CONCIERGE_OUTBOX", str(tmp_path / "outbox"))
    monkeypatch.setenv("CONCIERGE_USE_LLM", "0")
    monkeypatch.setenv("CONCIERGE_SMTP_DRYRUN", "1")
    monkeypatch.setenv("CONCIERGE_DEMO", "1")
    return tmp_path
