Run all linters for the ClaimsIQ project.

**Backend (Python):**
```bash
cd app/backend
python -m ruff check . --fix          # lint + auto-fix
python -m mypy claims/ --ignore-missing-imports  # type check
```

**Frontend (TypeScript):**
```bash
cd app/frontend
npx tsc --noEmit                      # type check only
```

**All at once:**
```bash
make lint
```

Key rules enforced:
- No PHI values in log statements
- All monetary values use `Money` / `Decimal` (no float)
- All new routes must declare `Depends(get_current_user)` or `Depends(require_roles(...))`
- `parseFloat()` wrapper on all Decimal-serialized API fields in TypeScript
