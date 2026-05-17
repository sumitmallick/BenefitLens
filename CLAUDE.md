# ClaimsIQ — Claude Code Project Guide

This file is the single source of truth for Claude Code agents working on this project.
Read it in full before making any changes.

---

## Project Overview

**ClaimsIQ** is an enterprise-grade insurance claims adjudication and management platform.

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Next.js 14 (App Router, TypeScript) | Clinician / patient / admin UI |
| Backend | FastAPI (Python 3.12, async) | REST API + claims adjudication engine |
| Database | PostgreSQL 16 | Primary data store (ACID, NUMERIC precision) |
| Cache | Redis 7 | Policy rule caching, rate limiting |
| Events | Kafka (opt-in) | Domain event streaming, audit trail |
| Infra | Docker Compose → K8s + Helm → Terraform (AWS) | Progressive deployment |

---

## Architecture — Hexagonal (Ports & Adapters)

```
┌──────────────────────────────────────────────────────────────┐
│                         API Layer                             │
│  FastAPI routes → Pydantic schemas → RBAC dependencies        │
└────────────────────────┬─────────────────────────────────────┘
                         │ commands / queries
┌────────────────────────▼─────────────────────────────────────┐
│                    Application Layer                          │
│  services.py — orchestrates domain logic, no I/O              │
└────────────────────────┬─────────────────────────────────────┘
                         │ domain entities only
┌────────────────────────▼─────────────────────────────────────┐
│                      Domain Layer                             │
│  entities.py · value_objects.py · adjudicator.py             │
│  state_machines.py · events.py                               │
└──────────────────────────────────────────────────────────────┘
                         │ (domain never imports infrastructure)
┌────────────────────────▼─────────────────────────────────────┐
│                  Infrastructure Layer                         │
│  models.py (SQLAlchemy ORM) · repositories.py · encryption.py│
│  database.py · (kafka publisher) · (redis cache)             │
└──────────────────────────────────────────────────────────────┘
```

**Key rules:**
- Domain layer has ZERO imports from infrastructure or API layers
- All DB access goes through repository classes — no raw SQL in routes
- Monetary values are always `Money` value objects (wraps `Decimal`) — never `float`
- PHI columns are prefixed `phi_` and encrypted at rest (Fernet AES-128-CBC)

---

## Key Design Patterns

| Pattern | Where Used | Why |
|---------|-----------|-----|
| Repository | `infrastructure/repositories.py` | Decouple domain from ORM |
| Value Object | `Money`, `DiagnosisCode`, `ProcedureCode` | Immutable, validated primitives |
| Aggregate Root | `Claim`, `Member`, `Policy` | Consistent transactional boundary |
| State Machine | `state_machines.py` | Explicit, auditable claim lifecycle |
| Domain Events | `DomainEventORM` table | Immutable audit log per claim |
| RBAC | `claims/api/deps.py` | JWT + role enforcement per route |
| Pessimistic Lock | `AnnualUsageRepository.get_for_update()` | Prevent concurrent limit double-spend |
| Outbox (partial) | `DomainEventORM` + Kafka publisher | Reliable event delivery |

---

## RBAC Roles

| Role | Access |
|------|--------|
| `ADMIN` | Full access + user management |
| `CLAIM_PROCESSOR` | All claims, members, disputes (no user management) |
| `PROVIDER` | Submit claims + view own NPI claims |
| `PATIENT` | Own claims only (linked via `users.member_id`) |

---

## Database Conventions

- **Primary keys**: UUID v4 (all tables)
- **Money columns**: `NUMERIC(12, 2)` — never FLOAT
- **PHI columns**: prefixed `phi_`, hold encrypted ciphertext (String 512)
- **Timestamps**: `DateTime(timezone=True)`, always UTC
- **Migrations**: Alembic, sequential (`0001_`, `0002_`, …)
- **Indexes**: All FK columns + composite indexes for common queries

To create a new migration:
```bash
make migrate-new msg="your description"
```

To apply migrations:
```bash
make migrate
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Async DSN: `postgresql+asyncpg://...` |
| `DATABASE_URL_SYNC` | Yes (Alembic) | Sync DSN: `postgresql://...` |
| `REDIS_URL` | Yes | `redis://redis:6379/0` |
| `PHI_ENCRYPTION_KEY` | Prod | 32-byte base64 Fernet key |
| `JWT_SECRET_KEY` | Prod | Min 32-char secret |
| `ENABLE_KAFKA` | No | `true` to publish domain events |
| `KAFKA_BOOTSTRAP_SERVERS` | If Kafka | `kafka:9092` |
| `CORS_ORIGINS` | Yes | JSON array of allowed origins |

---

## Development Workflow

```bash
make dev          # Start all services
make obs          # Start full stack + Prometheus + Loki + Grafana
make migrate      # Apply pending DB migrations
make seed         # Create demo users
make test         # Run full test suite
make lint         # ruff + mypy + tsc
make logs         # Follow all service logs
make grafana      # Open Grafana (http://localhost:3001, admin/admin)
make prometheus   # Open Prometheus (http://localhost:9090)
make down         # Stop and clean up
```

---

## Observability Stack

**PLG (Prometheus + Loki + Grafana)** — started with `make obs`.

| Component | Port | Purpose |
|-----------|------|---------|
| Prometheus | 9090 | Scrapes `/metrics` from FastAPI every 10 s |
| Loki | 3100 | Receives logs from Promtail (internal only) |
| Promtail | — | Ships Docker container logs to Loki |
| Grafana | 3001 | Unified metrics + logs UI (admin/admin) |

**Metrics** (`/metrics` endpoint on backend):
- `http_requests_total{method, handler, status}` — request counts by endpoint
- `http_request_duration_seconds` — latency histogram (p50/p95/p99)
- Provided by `prometheus-fastapi-instrumentator` — zero config

**Structured logs** (`claims/infrastructure/logging.py`):
- Development: coloured console via structlog `ConsoleRenderer`
- Production: JSON lines → Promtail → Loki → queryable in Grafana
- Every log line carries `request_id` (from `RequestIDMiddleware`)
- PHI filter: `_phi_filter` processor strips all `phi_*` keys before render

**Pre-built dashboard**: `infrastructure/observability/grafana/dashboards/claimsiq-overview.json`
- SLI row: request rate, error rate, P95 + P99 latency
- Claims row: submissions vs adjudicated, slowest endpoints
- Logs row: live error stream + full log tail

---

## Slash Commands (Skills)

- `/test`    — Run the full test suite
- `/migrate` — Apply Alembic migrations
- `/lint`    — Run all linters
- `/dev`     — Start development environment
- `/seed`    — Seed demo users and data
- `/tdd`    — TDD writer agent: write tests first, then stub implementation
- `/debug`  — Debug agent: diagnose issues from query results + logs (no DB access)

---

## TDD Agent (`/tdd <feature description>`)

Follows strict TDD sequence:
1. Read existing domain/infra code for context
2. Write domain tests first (`tests/domain/test_<feature>.py`) — pure Python, no DB
3. Write API integration tests (`tests/api/test_<feature>_api.py`) — real PostgreSQL
4. Run tests → confirm they fail (no implementation yet)
5. Write minimal implementation to make them pass
6. Run tests → confirm green

Never mock the database in integration tests.

---

## Debug Agent (`/debug`)

Works from **query results and logs only** — no DB access.

Paste in: SQL output, `docker logs claims-backend` lines, stack traces, curl responses.

The agent:
- Classifies the symptom (500, 422, 403, slow query, PHI leak, money arithmetic bug)
- Maps it to the exact file and line in the codebase
- Proposes the minimal fix with before/after diff
- Writes a regression test so it can't regress

---

## Testing Philosophy

Tests are written **before** the implementation (TDD). Three layers:

1. **Domain tests** (`tests/domain/`) — pure Python, no DB, no I/O
2. **API integration tests** (`tests/api/`) — httpx TestClient, real PostgreSQL
3. **Frontend type-check** — `tsc --noEmit` in CI

Never mock the database in integration tests. Use the test database configured in `pytest.ini`.

---

## Critical Rules for Claude Agents

1. **Never log PHI** — diagnosis codes, names, DOBs, emails must not appear in log output
2. **Never use float for money** — always `Decimal` / `Money` value object
3. **Never bypass RBAC** — all new routes must have `Depends(get_current_user)` or `Depends(require_roles(...))`
4. **Always add `parseFloat()`** — Pydantic v2 serializes `Decimal` as JSON strings; TypeScript must parse before arithmetic
5. **Migrations are sequential** — never edit an existing migration file; always create a new one
6. **PHI in API responses only in detail endpoints** — list endpoints strip diagnosis codes
