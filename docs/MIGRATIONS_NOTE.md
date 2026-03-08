# Running migrations

The app **runs migrations automatically** when backend mode is used: on startup, `ensure_database_ready(_get_db_path())` is invoked (see `app_prototype_v2.py`) and applies `db/schema.sql` if needed, then migrations 001–004 in order. No manual step is required.

To run migrations manually (e.g. from a script or shell):

```python
from db.connection import ensure_database_ready
ensure_database_ready("/path/to/your/cockpit.db")
```

Ensure the process has read/write access to the DB file and to `db/schema.sql` and `db/migrations/`.
