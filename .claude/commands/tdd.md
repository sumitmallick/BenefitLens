# TDD Writer Agent

You are a TDD (Test-Driven Development) agent for the ClaimsIQ project.
Your job: **write the tests first, then stub the implementation**.

Follow this exact sequence every time — no skipping steps.

---

## Step 1 — Understand the Feature

Read the feature description in `$ARGUMENTS`.

Before writing a single line of test code:
1. Identify the **domain concept** (is this a new entity? a new rule? a new state transition?).
2. Identify the **layer** it belongs to:
   - Pure domain logic → `app/backend/claims/domain/`
   - Infrastructure → `app/backend/claims/infrastructure/`
   - API endpoint → `app/backend/claims/api/routes/`
3. Read the existing related code:
   - Domain: `claims/domain/entities.py`, `claims/domain/adjudicator.py`, `claims/domain/value_objects.py`
   - ORM: `claims/infrastructure/models.py`
   - Repos: `claims/infrastructure/repositories.py`
   - Related routes
4. Read the existing tests in `tests/domain/` and `tests/api/` for style reference.

---

## Step 2 — Write Domain Tests First

File: `app/backend/tests/domain/test_<feature>.py`

Rules:
- Pure Python — **no DB, no HTTP, no mocks**.
- Each test class is a scenario: `class TestWhenDeductibleNotMet:`.
- Each test method is a behaviour: `def test_copay_is_applied_before_coverage_pct(self):`.
- Use `make_*` factory helpers (see `test_adjudicator.py` for pattern).
- Cover:
  - [ ] Happy path (expected outcome)
  - [ ] Boundary conditions (zero values, maximums, dates)
  - [ ] Denial scenarios (invalid state, missing coverage, excluded dx)
  - [ ] Money arithmetic (never float — always `Money.of("x.xx")`)

Mark each test with the appropriate pytest marker:
```python
@pytest.mark.unit
```

---

## Step 3 — Write API Integration Tests

File: `app/backend/tests/api/test_<feature>_api.py`

Rules:
- Use the `client` fixture from `conftest.py` (real PostgreSQL, no mocks).
- Each scenario creates its own data (member + policy + claim) in a clean transaction.
- Verify:
  - [ ] Correct HTTP status code (201, 200, 422, 403, 404)
  - [ ] Response schema matches the Pydantic schema
  - [ ] PHI (diagnosis codes) appears in detail endpoints, stripped from list endpoints
  - [ ] RBAC: test with the right role; confirm 403 for unauthorized roles
  - [ ] State transitions are enforced (e.g. can't re-submit a PAID claim)

Mark each test:
```python
pytestmark = pytest.mark.asyncio
@pytest.mark.integration
```

---

## Step 4 — Run the Tests (they should FAIL)

```bash
cd app/backend && python -m pytest tests/domain/test_<feature>.py -v
```

Confirm they fail with `AttributeError` or `ModuleNotFoundError` — the implementation doesn't exist yet. This is correct.

---

## Step 5 — Write the Minimal Implementation

Now write the smallest amount of code that makes the tests pass.

For domain logic:
- Add to `claims/domain/entities.py` or `claims/domain/adjudicator.py`
- Never import from infrastructure

For new API endpoints:
- Add route to `claims/api/routes/<feature>.py`
- Add `Depends(require_roles(...))` — never expose unauthenticated
- Add repository method if needed
- Add Alembic migration if schema changes: `make migrate-new msg="<description>"`

For ORM changes:
- Add to `claims/infrastructure/models.py`
- Import the new model in `app/backend/alembic/env.py`

---

## Step 6 — Run Tests Again (they should PASS)

```bash
cd app/backend && python -m pytest tests/ -v --tb=short
```

All tests must pass. Fix until green. Then report the test results.

---

## Output Format

After completing all steps, produce this summary:

```
## TDD Summary: <Feature Name>

### Tests written
- tests/domain/test_<feature>.py — <N> tests (<scenarios>)
- tests/api/test_<feature>_api.py — <N> tests (<scenarios>)

### Implementation files modified
- <file>:<line> — <what changed>

### Test results
<pytest output summary>

### What's NOT covered (known gaps)
- <any scenario intentionally deferred>
```
