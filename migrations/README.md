# Legacy migrations

These SQL files and `run.py` document the pre-Alembic compatibility path. They
are retained so operators can identify the schema represented by
`0001_current_schema`; application startup no longer executes them.

Use `python scripts/migrate.py upgrade` for every fresh or existing database.
The command creates a fresh schema, stamps a complete pre-Alembic current
schema without modifying its data, and applies later revisions. A partial or
unknown schema fails visibly instead of swallowing DDL errors.

