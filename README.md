# Claims Processing System

Insurance claims adjudication API + UI. Built for the realfast Lead FDE take-home.

## What it does

- Members submit insurance claims with line items (service type, diagnosis code, procedure code, billed amount)
- The system adjudicates each line item against the member's coverage rules: deductible, copay, annual limit, per-visit cap, coverage percentage
- Claims move through a lifecycle: SUBMITTED → UNDER_REVIEW → APPROVED | PARTIALLY_APPROVED | DENIED → PAID
- Members can dispute decisions; each dispute goes through its own lifecycle
- Every coverage decision includes a plain-English explanation ("Your annual benefit of $2,000 for SPECIALIST_VISIT has been fully used for 2026")

---

## Quick start (Docker Compose)

```bash
# 1. Clone and start
git clone <this-repo>
cd claims-processing

# 2. Start all services (postgres, redis, backend, frontend)
docker-compose up --build

# 3. Services
#    Backend API:  http://localhost:8000
#    API docs:     http://localhost:8000/docs
#    Frontend:     http://localhost:3000
```

The backend runs Alembic migrations on startup. No separate migration step needed.

---

## Local development (without Docker)

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL 16 running locally
- Redis 7 running locally

### Backend

```bash
cd app/backend

# Create virtualenv
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: set DATABASE_URL, DATABASE_URL_SYNC, REDIS_URL

# Run migrations
alembic upgrade head

# Start server
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd app/frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
# → http://localhost:3000
```

---

## Running tests

### Domain tests (no DB required — fast)
```bash
cd app/backend
pytest tests/domain/ -v
```

### Integration tests (requires PostgreSQL)
```bash
# Start test database
docker-compose up postgres -d

# Run all tests
TEST_DATABASE_URL=postgresql+asyncpg://claims:claims@localhost:5432/claimsdb_test \
pytest tests/ -v --cov=claims
```

---

## Demo walkthrough

The fastest path to see the system working:

### 1. Create a member
```bash
curl -X POST http://localhost:8000/api/v1/members \
  -H "Content-Type: application/json" \
  -d '{
    "member_id": "MBR-001",
    "name": "Alice Johnson",
    "date_of_birth": "1985-03-15",
    "email": "alice@example.com"
  }'
# → { "id": "<member-uuid>", ... }
```

### 2. Create a policy
```bash
curl -X POST http://localhost:8000/api/v1/policies \
  -H "Content-Type: application/json" \
  -d '{
    "member_id": "<member-uuid>",
    "policy_number": "POL-2026-001",
    "effective_date": "2026-01-01",
    "expiration_date": "2026-12-31",
    "deductible_amount": 500.00,
    "out_of_pocket_max": 5000.00,
    "coverage_rules": [
      {
        "service_type": "PREVENTIVE",
        "coverage_percentage": 100,
        "annual_limit": null,
        "per_visit_limit": null,
        "copay": null,
        "requires_preauth": false,
        "network_restriction": "ANY",
        "excluded_diagnosis_codes": []
      },
      {
        "service_type": "SPECIALIST_VISIT",
        "coverage_percentage": 80,
        "annual_limit": 5000.00,
        "per_visit_limit": 300.00,
        "copay": 30.00,
        "requires_preauth": false,
        "network_restriction": "ANY",
        "excluded_diagnosis_codes": []
      },
      {
        "service_type": "EMERGENCY",
        "coverage_percentage": 90,
        "annual_limit": 50000.00,
        "per_visit_limit": null,
        "copay": 150.00,
        "requires_preauth": false,
        "network_restriction": "ANY",
        "excluded_diagnosis_codes": []
      }
    ]
  }'
# → { "id": "<policy-uuid>", ... }
```

### 3. Submit a claim
```bash
curl -X POST http://localhost:8000/api/v1/claims/ \
  -H "Content-Type: application/json" \
  -d '{
    "member_id": "<member-uuid>",
    "policy_id": "<policy-uuid>",
    "provider_name": "Metro Health Specialists",
    "provider_npi": "1234567890",
    "line_items": [
      {
        "service_type": "PREVENTIVE",
        "service_date": "2026-05-15",
        "billed_amount": 150.00,
        "diagnosis_code": "Z00.00",
        "procedure_code": "99395",
        "description": "Annual wellness exam"
      },
      {
        "service_type": "SPECIALIST_VISIT",
        "service_date": "2026-05-15",
        "billed_amount": 350.00,
        "diagnosis_code": "M54.5",
        "procedure_code": "99213",
        "description": "Orthopedic consult"
      },
      {
        "service_type": "DENTAL",
        "service_date": "2026-05-15",
        "billed_amount": 200.00,
        "diagnosis_code": "K02.9",
        "procedure_code": "D0120",
        "description": "Dental exam"
      }
    ]
  }'
```

Expected result:
- PREVENTIVE: **COVERED** at 100% ($150.00)
- SPECIALIST_VISIT: **DENIED** (deductible of $500 not yet met; $300 per-visit cap; $30 copay → all goes to deductible → $0 covered)
- DENTAL: **DENIED** (NOT_COVERED_SERVICE — no dental rule in policy)
- Claim status: **PARTIALLY_APPROVED**

### 4. Get explanation
```bash
curl http://localhost:8000/api/v1/claims/<claim-id>/explain
```

### 5. Dispute the dental denial
```bash
curl -X POST http://localhost:8000/api/v1/disputes/claims/<claim-id> \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "My policy booklet shows dental coverage was added via rider effective Jan 2026.",
    "line_item_id": "<dental-line-item-id>"
  }'
```

### 6. Resolve the dispute
```bash
curl -X POST http://localhost:8000/api/v1/disputes/<dispute-id>/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "outcome": "UPHELD",
    "notes": "Dental rider confirmed active. Claim to be reprocessed with dental coverage."
  }'
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend                          │
│                     (React, TypeScript, TQ)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (JSON)
┌────────────────────────────▼────────────────────────────────────┐
│                     FastAPI Backend                              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  API Layer (routes, schemas)                │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │              Application Service Layer                      │  │
│  │  (submit_claim, adjudicate_claim, submit_dispute, etc.)    │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │                  Domain Layer                               │  │
│  │  Entities, Value Objects, State Machines, Adjudicator      │  │
│  │  (NO I/O — pure Python)                                    │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │               Infrastructure Layer                          │  │
│  │  SQLAlchemy ORM, Repositories, PHI Encryption, Events      │  │
│  └────────────┬────────────────────────────────┬──────────────┘  │
└───────────────┼────────────────────────────────┼─────────────────┘
                │                                │
          PostgreSQL                           Redis
          (primary store,              (policy/usage cache)
          SELECT FOR UPDATE)
                │
           Kafka/SQS
         (domain events,
          async optional)
```

---

## Interesting problems solved

### Annual limit double-spend
Two concurrent claims for the same service type would both see $5,000 remaining and both approve. Solution: `SELECT FOR UPDATE` on `annual_usages`. See `repositories.py:AnnualUsageRepository.get_for_update()`.

### PHI in a list vs. detail API
Diagnosis codes (PHI) appear in claim detail (`GET /claims/:id`) but not in list responses (`GET /claims/member/:id`). Separate Pydantic schemas (`LineItemResponse` vs `LineItemDetailResponse`) enforce this at compile time.

### Explaining a denial in plain English
Every adjudication result carries a prose explanation naming the specific rule, amounts, and reason. The adjudicator builds this as it processes each step. See `adjudicator.py`.

### State machine as data
Transitions are a `Dict[Status, FrozenSet[Status]]`, not methods. This makes the graph inspectable (print it, render it as a diagram), testable without side effects, and serializable to an audit log.

---

## Project structure

```
realfast-claims/
├── app/
│   ├── backend/
│   │   ├── claims/
│   │   │   ├── domain/          # Pure domain (no I/O)
│   │   │   │   ├── adjudicator.py
│   │   │   │   ├── entities.py
│   │   │   │   ├── events.py
│   │   │   │   ├── state_machines.py
│   │   │   │   └── value_objects.py
│   │   │   ├── application/     # Orchestration
│   │   │   │   └── services.py
│   │   │   ├── infrastructure/  # DB, encryption, repos
│   │   │   │   ├── database.py
│   │   │   │   ├── encryption.py
│   │   │   │   ├── models.py
│   │   │   │   └── repositories.py
│   │   │   └── api/             # HTTP layer
│   │   │       ├── schemas.py
│   │   │       └── routes/
│   │   ├── tests/
│   │   │   ├── domain/          # Unit tests (no DB)
│   │   │   └── api/             # Integration tests
│   │   ├── alembic/
│   │   ├── main.py
│   │   └── requirements.txt
│   └── frontend/                # Next.js 14
├── docs/
│   ├── domain-model.md
│   ├── decisions.md
│   └── self-review.md
├── infrastructure/
│   ├── docker/
│   ├── kubernetes/
│   ├── terraform/
│   └── helm/
├── .github/workflows/ci.yml
├── ai-artifacts/                # Claude Code session logs
└── docker-compose.yml
```

---

## Known gaps

- Out-of-pocket maximum not enforced (field exists, adjudicator doesn't check it)
- Preauth grants not recordable (adjudicator checks but no API to submit them)
- Redis cache not implemented (infrastructure ready, application code pending)
- KMS envelope encryption not implemented (env var key in dev; documented in self-review)
- Adjudicator mutates Policy.deductible_met in-place (implicit state mutation)

See `docs/self-review.md` for the full honest assessment.
