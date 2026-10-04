# PostgreSQL Migration Guide

## Overview

The application supports both SQLite (development) and PostgreSQL (production) via SQLAlchemy-compatible patterns. The database layer uses raw SQL with parameterized queries, making it compatible with PostgreSQL via psycopg2 or asyncpg.

## Connection String Format

### SQLite (Development)
```
DATABASE_URL=sqlite:///data/saas.db
DATABASE_URL=data/saas.db  # Also works with current code
```

### PostgreSQL (Production)
```
DATABASE_URL=postgresql://user:password@host:5432/heyjarvis
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/heyjarvis  # For async
```

## Schema Compatibility

The current schema uses SQLite-specific features:

1. `INTEGER PRIMARY KEY AUTOINCREMENT` → PostgreSQL: `SERIAL PRIMARY KEY` or `BIGSERIAL`
2. `TEXT NOT NULL DEFAULT '{}'` → PostgreSQL: same (works)
3. `json_set()` (SQLite) → PostgreSQL: `jsonb_set()`
4. `last_insert_rowid()` → PostgreSQL: `RETURNING id`
5. `PRAGMA journal_mode=WAL` → PostgreSQL: native MVCC
6. `UNIQUE(key, window_start)` → PostgreSQL: same

## Migration Script

Run this once when switching to PostgreSQL:

```sql
-- tenants table (idempotent)
CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    plan VARCHAR(50) NOT NULL DEFAULT 'trial',
    metadata JSONB NOT NULL DEFAULT '{}'
);

-- users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    hashed_password TEXT,
    role VARCHAR(50) NOT NULL DEFAULT 'owner',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMP,
    metadata JSONB NOT NULL DEFAULT '{}',
    UNIQUE(tenant_id, email)
);

-- ... (same schema for all other tables, replacing INTEGER AUTOINCREMENT with SERIAL)
```

## Python Code Changes Required

### 1. Database Connection

Current (SQLite):
```python
conn = sqlite3.connect(path)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
```

PostgreSQL:
```python
import psycopg2
conn = psycopg2.connect(DATABASE_URL)
conn.row_factory = psycopg2.extras.RealDictRow
```

### 2. Insert with RETURNING

Current (SQLite):
```python
tid = c.execute("INSERT INTO ...").lastrowid
```

PostgreSQL:
```python
tid = c.execute("INSERT INTO ... RETURNING id").fetchone()["id"]
```

### 3. JSON Operations

Current (SQLite):
```python
c.execute("UPDATE ... SET flags = json_set(flags, '$.key', ?)", (value,))
```

PostgreSQL:
```python
c.execute("UPDATE ... SET flags = jsonb_set(flags, '{key}', %s::jsonb)", (value,))
```

## Verification Checklist

- [ ] All existing tests pass with PostgreSQL
- [ ] Tenant isolation works
- [ ] Conversation flow works
- [ ] Lead creation works
- [ ] Email settings work
- [ ] Business rules work
- [ ] Audit logging works
- [ ] Analytics work
- [ ] API keys work
- [ ] Rate limiting works

## Rollback

To rollback to SQLite:
```bash
export DATABASE_URL=data/saas.db
```

Data migration from PostgreSQL to SQLite requires export/import scripts.
