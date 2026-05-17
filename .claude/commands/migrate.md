Apply all pending Alembic database migrations.

```bash
docker compose exec backend sh -c "cd /app && alembic upgrade head"
```

After applying, verify with:
```bash
docker compose exec backend sh -c "cd /app && alembic current"
```

To create a new migration from model changes (replace DESCRIPTION):
```bash
cd app/backend && alembic revision --autogenerate -m "DESCRIPTION"
```

Migration naming convention: `0001_initial_schema.py`, `0002_add_users.py`, `0003_add_scale_indexes.py`, ...
Never edit an existing migration file — always create a new one.
