"""Multi-tenant SaaS layer for HeyJarvis Concierge.

Existing ``src/concierge/`` is the proven single-tenant core.
This package adds:
- tenant model and persistence
- authentication
- public tenant-aware APIs
- embeddable chat widget
- admin dashboard
- email template engine
- installation / domain allowlist
- hosted concierge pages
- WordPress integration assets

The core engine in ``concierge`` is reused, not rewritten.
"""
