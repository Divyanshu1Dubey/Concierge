"""Test isolation for every pytest run, including single root-level files.

Several root test files clean tables with DELETE FROM ...; without this they would
wipe data/saas.db when run on their own. Point everything at a throwaway database
before any saas module is imported.
"""

import os
import tempfile

if "PYTEST_KEEP_DATABASE_URL" not in os.environ:
    _tmp = tempfile.mkdtemp(prefix="saas-test-")
    os.environ["DATABASE_URL"] = os.path.join(_tmp, "test.db")
    os.environ["CONCIERGE_DB"] = os.environ["DATABASE_URL"]
    os.environ.setdefault("CONCIERGE_USE_LLM", "0")
    os.environ["CONCIERGE_SCHEDULER"] = "0"
    os.environ["CONCIERGE_SYNC_ALERTS"] = "1"
    for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "SMTP_PASSWORD", "DEFAULT_SMTP_PASSWORD"):
        os.environ.pop(_k, None)
