import os
import tempfile

# ── Set test environment BEFORE any saas modules are imported ──────────────
# This runs at conftest import time (during pytest collection), before any
# test module imports saas code.
_tmp = tempfile.mkdtemp(prefix="saas-test-")
_test_db = os.path.join(_tmp, "test.db")

for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY",
           "SMTP_PASSWORD", "CONCIERGE_AUTO_CONFIRM"):
    os.environ.pop(_k, None)

os.environ["DATABASE_URL"] = _test_db
os.environ["CONCIERGE_DB"] = _test_db
os.environ["CONCIERGE_OUTBOX"] = os.path.join(_tmp, "outbox")
os.environ["CONCIERGE_USE_LLM"] = "0"
os.environ["CONCIERGE_SMTP_DRYRUN"] = "1"
os.environ["CONCIERGE_DEMO"] = "1"
os.environ["CONCIERGE_SCHEDULER"] = "0"

import pytest  # noqa: E402
from saas.config import get_settings  # noqa: E402
from saas.database import reset_schema_cache, reset_database  # noqa: E402


def pytest_configure(config):
    """Ensure caches are fresh at start of test session."""
    get_settings.cache_clear()
    reset_schema_cache()


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Per-test: fresh database, no external services."""
    get_settings.cache_clear()
    reset_schema_cache()
    per_test_db = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_URL", per_test_db)
    monkeypatch.setenv("CONCIERGE_DB", per_test_db)
    monkeypatch.setenv("CONCIERGE_OUTBOX", str(tmp_path / "outbox"))
    # Delete any leftover DB from previous test runs
    reset_database()
    return tmp_path
