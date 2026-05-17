Run the full ClaimsIQ test suite.

**Backend tests (pytest):**
```bash
cd app/backend && python -m pytest tests/ -v --tb=short --cov=claims --cov-report=term-missing
```

**Frontend type-check:**
```bash
cd app/frontend && npx tsc --noEmit
```

**Run both via Make:**
```bash
make test
```

Test structure:
- `tests/domain/` — pure unit tests (no DB, no network)
- `tests/api/` — integration tests (real PostgreSQL via httpx TestClient)

Never mock the database in integration tests. The adjudicator, state machines, and repositories are all integration-tested against a real PostgreSQL instance.
