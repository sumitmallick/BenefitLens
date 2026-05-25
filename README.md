# ClaimsIQ

![Build](https://img.shields.io/github/actions/workflow/status/sumitkumarmallick/claimsiq/ci.yml?branch=main&label=build)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Next.js](https://img.shields.io/badge/Next.js-14-black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)

**Production-grade insurance claims adjudication platform.**

ClaimsIQ processes, adjudicates, and explains insurance claims against member policy rules — in real time. It enforces benefit limits, deductibles, copays, pre-authorization requirements, and diagnosis exclusions through a deterministic 10-step adjudication engine. Every decision is explainable, auditable, and disputable.

---

## Who It's For

| Persona | What They Get |
|---------|---------------|
| **Health Plans / Payers** | Automated adjudication engine; configurable coverage rules per policy; HIPAA-aligned PHI handling |
| **Providers** | Submit claims via API or UI; track approval status; view per-NPI claim history |
| **Members / Patients** | Self-service portal to view claims, read plain-English explanations, and submit disputes |
| **Claim Processors** | Unified queue with UNDER_REVIEW escalation; dispute resolution workflow |
| **Platform Engineers** | Hexagonal architecture; Helm + Terraform deployment; GitHub Actions CI/CD |

---

## Table of Contents

1. [Architecture](#architecture)
2. [Technology Choices](#technology-choices)
3. [Database Schema](#database-schema)
4. [Scale Design Decisions](#scale-design-decisions)
5. [Auth & RBAC](#auth--rbac)
6. [Adjudication Engine](#adjudication-engine)
7. [Scheduled Jobs](#scheduled-jobs)
8. [Quick Start](#quick-start)
9. [End-to-End User Flows](#end-to-end-user-flows)
10. [Deployment Guide](#deployment-guide)
11. [API Reference](#api-reference)
12. [Environment Variables](#environment-variables)
13. [Development Workflow](#development-workflow)
14. [Security Considerations](#security-considerations)
15. [License](#license)

---

## Architecture

ClaimsIQ follows a **Hexagonal (Ports & Adapters)** architecture. The domain layer contains zero infrastructure imports — no SQLAlchemy, no Redis, no HTTP. This means the adjudication logic is independently testable and the storage layer is swappable without touching business rules.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Next.js 14 Frontend                           │
│              (App Router · TypeScript · Tailwind CSS)                │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTPS / JSON
┌──────────────────────────────▼───────────────────────────────────────┐
│                         FastAPI  (Python 3.12)                       │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  API Layer                                                       │ │
│  │  FastAPI routes · Pydantic v2 schemas · JWT auth dependencies   │ │
│  └────────────────────────────┬────────────────────────────────────┘ │
│  ┌─────────────────────────────▼──────────────────────────────────┐  │
│  │  Application Layer                                              │  │
│  │  ClaimsService · MembersService · DisputeService               │  │
│  │  Orchestrates use cases; owns transaction boundaries           │  │
│  └────────────────────────────┬───────────────────────────────────┘  │
│  ┌─────────────────────────────▼──────────────────────────────────┐  │
│  │  Domain Layer  (pure Python — zero I/O)                        │  │
│  │  Entities · Value Objects · State Machines                     │  │
│  │  ClaimsAdjudicator · Domain Events                             │  │
│  └────────────────────────────┬───────────────────────────────────┘  │
│  ┌─────────────────────────────▼──────────────────────────────────┐  │
│  │  Infrastructure Layer                                           │  │
│  │  SQLAlchemy 2.0 async ORM · Repositories                       │  │
│  │  Fernet PHI Encryption · Redis Cache · Kafka Publisher         │  │
│  └──────┬─────────────────────────────────────────┬──────────────┘   │
└─────────┼───────────────────────────────────────  ┼──────────────────┘
          │                                          │
   ┌──────▼──────┐    ┌───────────────┐    ┌────────▼──────┐
   │ PostgreSQL  │    │     Redis 7   │    │  Kafka / MSK  │
   │     16      │    │               │    │  (optional)   │
   │ ACID store  │    │  Rule cache   │    │ Domain events │
   │ SELECT FOR  │    │  Rate limit   │    │ Audit stream  │
   │   UPDATE    │    └───────────────┘    └───────────────┘
   └─────────────┘
```

### Layer Responsibilities

| Layer | Package | Rule |
|-------|---------|------|
| Domain | `claims/domain/` | No imports outside stdlib. No I/O. Testable in milliseconds. |
| Application | `claims/application/` | Calls repositories (via interfaces). Owns `async with session` transaction scope. |
| Infrastructure | `claims/infrastructure/` | All SQLAlchemy, Redis, Kafka, Fernet. Implements domain interfaces. |
| API | `claims/api/` | HTTP concerns only. Converts Pydantic ↔ domain objects. Enforces RBAC. |

---

## Technology Choices

### PostgreSQL 16

- **ACID transactions are non-negotiable for financial data.** A claim adjudication writes `adjudication_results`, updates `annual_usages`, mutates `claims.status`, and appends to `domain_events` — all or nothing.
- **`NUMERIC(12,2)` throughout** — no IEEE-754 floating-point errors on money. `0.1 + 0.2 == 0.3` in every query.
- **`SELECT FOR UPDATE` on `annual_usages`** prevents two concurrent claims from both seeing a non-exhausted annual limit and both approving. Pessimistic locking is the correct choice here; optimistic retry adds complexity without benefit for a hot-row contention pattern.
- **`JSONB` for `excluded_diagnosis_codes`** — exclusion lists vary wildly per coverage rule (0 to hundreds of ICD-10 codes). JSONB stores them flexibly, supports GIN indexing if queried, and avoids a separate junction table for a read-mostly field.

### Redis 7

- **Coverage rules change rarely but are read on every line item adjudication.** Caching them in Redis eliminates repeated `JOIN`-heavy queries during high-volume claim ingestion.
- **Atomic `INCR` and expiry** provide the foundation for future distributed rate limiting on the `POST /claims/` endpoint without adding a separate rate-limiter service.
- **Session store readiness** — the JWT strategy is stateless today, but Redis is pre-wired to support token revocation (blocklist) when compliance requirements demand it.
- **Sub-millisecond reads** keep adjudication latency predictable under load spikes from batch claim submission.

### Kafka (Apache Kafka / AWS MSK)

- **Decouples claims adjudication from downstream consumers.** Billing, notification, and reporting services consume `ClaimAdjudicated` events without blocking the synchronous API response path.
- **Domain events are published after the database transaction commits**, preventing the dual-write problem. Kafka acts as the reliable event bus, not the primary store.
- **Persistent audit trail separate from the primary database.** Events are retained independently of the `domain_events` table and can be replayed for reprocessing or compliance review.
- **Kafka is optional at startup.** The `KafkaPublisher` is injected as a dependency; if MSK is unavailable, the system falls back gracefully — events are stored in `domain_events` in PostgreSQL.

---

## Database Schema

```mermaid
erDiagram
    MEMBERS {
        uuid id PK
        text phi_member_id "Fernet encrypted"
        text phi_name "Fernet encrypted"
        text phi_date_of_birth "Fernet encrypted"
        text phi_email "Fernet encrypted"
        timestamp created_at
        timestamp updated_at
    }

    USERS {
        uuid id PK
        text email UK
        text hashed_password
        text full_name
        enum role "ADMIN|CLAIM_PROCESSOR|PATIENT|PROVIDER"
        uuid member_id FK
        text provider_npi
        text provider_name
        boolean is_active
    }

    POLICIES {
        uuid id PK
        uuid holder_member_id FK "Primary subscriber (contract owner)"
        text policy_number UK
        date effective_date
        date expiration_date
        enum status "ACTIVE|EXPIRED|CANCELLED"
        numeric deductible_amount "NUMERIC(12,2)"
        numeric deductible_met "NUMERIC(12,2)"
        numeric out_of_pocket_max "NUMERIC(12,2) nullable"
        numeric oop_used "NUMERIC(12,2)"
        timestamp created_at
        timestamp updated_at
    }

    MEMBERSHIP_POLICIES {
        uuid id PK
        uuid policy_id FK
        uuid member_id FK
        enum relationship "SELF|SPOUSE|CHILD|OTHER_DEPENDENT"
        date enrollment_date "Coverage start for this member"
        date termination_date "nullable — NULL means still active"
        enum status "ACTIVE|TERMINATED|SUSPENDED"
        timestamp created_at
        timestamp updated_at
    }

    MEMBERSHIP_COVERAGE_RULES {
        uuid id PK
        uuid membership_id FK
        text service_type
        numeric coverage_percentage "NUMERIC(5,2)"
        numeric annual_limit "nullable"
        numeric per_visit_limit "nullable"
        numeric copay "nullable"
        boolean requires_preauth
        text network_restriction
        jsonb excluded_diagnosis_codes
    }

    COVERAGE_RULES {
        uuid id PK
        uuid policy_id FK
        text service_type
        numeric coverage_percentage "NUMERIC(5,2)"
        numeric annual_limit "nullable"
        numeric per_visit_limit "nullable"
        numeric copay "nullable"
        boolean requires_preauth
        text network_restriction "ANY|IN_NETWORK|PREFERRED"
        jsonb excluded_diagnosis_codes
    }

    ANNUAL_USAGES {
        uuid id PK
        uuid policy_id FK
        text service_type
        integer benefit_year
        numeric used_amount "NUMERIC(12,2)"
    }

    CLAIMS {
        uuid id PK
        text claim_number UK
        uuid member_id FK
        uuid policy_id FK
        enum status
        timestamp submitted_at
        text provider_name
        text provider_npi
        timestamp updated_at
    }

    LINE_ITEMS {
        uuid id PK
        uuid claim_id FK
        text service_type
        date service_date
        numeric billed_amount
        text phi_diagnosis_code "Fernet encrypted ICD-10"
        text procedure_code
        text description
        enum status
    }

    ADJUDICATION_RESULTS {
        uuid id PK
        uuid line_item_id FK "UNIQUE"
        numeric covered_amount
        text denial_reason "nullable"
        text explanation
        numeric deductible_applied
        numeric copay_applied
        timestamp adjudicated_at
    }

    DISPUTES {
        uuid id PK
        uuid claim_id FK
        uuid line_item_id "nullable"
        text reason
        enum status
        timestamp submitted_at
        timestamp resolved_at "nullable"
        text resolution_notes "nullable"
    }

    DOMAIN_EVENTS {
        uuid id PK
        uuid claim_id FK
        text event_type
        timestamp occurred_at
        jsonb payload
    }

    AUDIT_LOGS {
        uuid id PK
        timestamp timestamp
        uuid user_id "nullable"
        text user_email "nullable"
        text user_role "nullable"
        text action
        text resource_type
        uuid resource_id "nullable"
        text ip_address "nullable"
        text request_id "nullable"
        text http_method "nullable"
        text http_path "nullable"
    }

    MEMBERS ||--o{ MEMBERSHIP_POLICIES : "enrolled via"
    MEMBERS ||--o{ POLICIES : "holds (as primary subscriber)"
    MEMBERS ||--o{ CLAIMS : "files"
    USERS }o--o| MEMBERS : "linked to"
    POLICIES ||--o{ MEMBERSHIP_POLICIES : "covers"
    MEMBERSHIP_POLICIES ||--o{ MEMBERSHIP_COVERAGE_RULES : "overrides"
    POLICIES ||--o{ COVERAGE_RULES : "defines (defaults)"
    POLICIES ||--o{ ANNUAL_USAGES : "tracks"
    POLICIES ||--o{ CLAIMS : "governs"
    CLAIMS ||--o{ LINE_ITEMS : "contains"
    CLAIMS ||--o{ DISPUTES : "subject to"
    CLAIMS ||--o{ DOMAIN_EVENTS : "generates"
    LINE_ITEMS ||--o| ADJUDICATION_RESULTS : "produces"
```

### Policy ↔ Member Relationship (Migration 0005)

Prior to migration 0005, `policies.member_id` pointed directly to one member, encoding a one-to-one policy/member relationship that couldn't model group or family plans.

The current design separates three concerns:

| Concept | Column / Table | Meaning |
|---------|---------------|---------|
| **Primary subscriber** | `policies.holder_member_id` | The person who holds the contract and is responsible for premiums. One policy has exactly one holder. |
| **Enrolled members** | `membership_policies` | Every person covered by the policy. The holder is always enrolled with `relationship = SELF`; dependents are added separately. |
| **Per-member coverage** | `membership_coverage_rules` | Optional per-member rule overrides. Absent service types fall back to the policy's default `coverage_rules`. Enables different copays, limits, or coverage percentages per dependent. |

```
MEMBERS ──────────────────────────────────────────────────────────┐
   │  (holder_member_id)                                           │
   │  1 member can hold many policies                              │
   ▼                                                               │
POLICIES ─────────────────────────────────────────────────────┐   │
   │  1 policy covers many members                             │   │
   ▼                                                           │   │
MEMBERSHIP_POLICIES  (policy_id FK + member_id FK + UNIQUE)   │   │
   • relationship  SELF | SPOUSE | CHILD | OTHER_DEPENDENT     │   │
   • enrollment_date / termination_date                        │   │
   • status        ACTIVE | TERMINATED | SUSPENDED             │   │
   │                                                           │   │
   ▼ (optional)                                                │   │
MEMBERSHIP_COVERAGE_RULES  (membership_id FK + UNIQUE per svc)│   │
   • per-member overrides: coverage_%, copay, annual_limit     │   │
   • absent service_type → falls back to COVERAGE_RULES        │   │
   └──────── member_id ──────────────────────────────────────────┘   │
             policy_id ──────────────────────────────────────────────┘
```

**Adjudication rule resolution order** (pure domain, no I/O):
1. Check `membership_coverage_rules` for the claiming member's service type
2. If found → use member-level override
3. If not found → fall back to `coverage_rules` (policy default)

**Indexes on `membership_policies` and `membership_coverage_rules`:**

| Index | Purpose |
|-------|---------|
| `ix_membership_policies_policy_id` | List all members enrolled in a policy |
| `ix_membership_policies_member_id` | List all policies a member is enrolled in |
| `ix_membership_policies_member_active` (partial, `status='ACTIVE'`) | Active-coverage check at claim submission — hot path |
| `ix_membership_policies_policy_status` | Active-member roster per policy — admin/UI |
| `ix_membership_coverage_rules_membership_id` | Rule look-up per membership during adjudication |

### PHI Fields

All fields prefixed `phi_` are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256) before being written to PostgreSQL. The encryption key is loaded from the `PHI_ENCRYPTION_KEY` environment variable and never touches the database. Key rotation is supported via `MultiFernet` with multiple keys.

---

## Scale Design Decisions

### Pessimistic Locking on Annual Usages

Annual benefit limits are a shared mutable resource. Under concurrent load, two claims for the same `(policy_id, service_type)` pair can both read a non-exhausted limit and both approve — a classic double-spend. The solution is `SELECT FOR UPDATE` on the `annual_usages` row at the start of adjudication:

```python
# repositories.py — AnnualUsageRepository
async def get_for_update(self, policy_id, service_type, benefit_year):
    result = await self.session.execute(
        select(AnnualUsageModel)
        .where(...)
        .with_for_update()
    )
```

This serializes concurrent adjudications on the same benefit bucket at the database level, avoiding optimistic retry complexity.

### Composite Indexes (Migration 0003)

Composite and partial indexes were added to support production query patterns:

| Index | Query Pattern |
|-------|---------------|
| `claims(member_id, status)` | Patient dashboard — filter own claims by status |
| `claims(provider_npi, submitted_at)` | Provider portal — paginated submission history |
| `claims(status, submitted_at)` | Processor queue — ordered work queue by status |
| `disputes(claim_id, status)` | Dispute lookup per claim |
| `policies(holder_member_id)` | Holder's policy list |
| `policies(holder_member_id) WHERE status='ACTIVE'` | Active-policy lookup for the holder |
| `membership_policies(member_id) WHERE status='ACTIVE'` | **Adjudication hot path** — active coverage check at claim submission |
| `membership_policies(policy_id, status)` | Active-member roster per policy |
| `membership_coverage_rules(membership_id)` | Per-member rule look-up during adjudication |
| `line_items(claim_id, status)` | Line item rollup per claim |
| `users(role, is_active)` | Admin user management table |

### Separate Pydantic Schemas for PHI Containment

`LineItemResponse` (used in list endpoints) omits `phi_diagnosis_code`. `LineItemDetailResponse` (used in `GET /claims/{id}`) includes it. This is enforced at compile time by the type system — there is no runtime check that can be accidentally bypassed.

### Append-Only Domain Events Table

`domain_events` is written to but never updated or deleted. It serves as an immutable audit log of all state transitions and adjudication decisions, independent of the mutable `claims` and `adjudication_results` tables. This enables point-in-time reconstruction of any claim's history.

### State Machines as Data

Claim and dispute state transitions are represented as `Dict[Status, FrozenSet[Status]]` — a declarative adjacency map. Benefits: the graph is inspectable and printable, transitions are testable without side effects, and invalid transitions raise deterministic exceptions rather than silently succeeding.

---

## Auth & RBAC

ClaimsIQ uses **JWT bearer tokens** (python-jose, RS256-ready) with a **role-based access control** model. Tokens are stateless; the `role` claim is embedded in the JWT payload and verified on every request without a database lookup.

### Role Definitions

| Role | Description |
|------|-------------|
| `ADMIN` | Full platform access including user management and statistics |
| `CLAIM_PROCESSOR` | Submit, review, and resolve claims and disputes; no user management |
| `PROVIDER` | Submit claims for their NPI; view only claims submitted under their NPI |
| `PATIENT` | View their own member's claims and adjudication results; submit disputes |

### Permission Matrix

| Action | ADMIN | CLAIM_PROCESSOR | PATIENT | PROVIDER |
|--------|:-----:|:---------------:|:-------:|:--------:|
| View all claims | Yes | Yes | Own only | Own NPI |
| Submit claims | Yes | Yes | Own only | Yes (own member) |
| Resolve disputes | Yes | Yes | No | No |
| Register members | Yes | Yes | No | No |
| User management | Yes | No | No | No |
| Platform statistics | Yes | Yes | No | No |
| View adjudication detail | Yes | Yes | Own only | Own NPI |

### Token Flow

```
POST /api/v1/auth/login
  → { access_token: "eyJ...", token_type: "bearer" }

Authorization: Bearer eyJ...
  → FastAPI dependency extracts role
  → Route decorator enforces required role(s)
  → Data-layer filter scopes query to member_id or provider_npi
```

---

## Adjudication Engine

The adjudicator (`claims/domain/adjudicator.py`) processes each line item through a deterministic 10-step decision sequence. Steps are evaluated in order; the first failing step produces a denial with a prose explanation. A passing step accumulates state (deductible applied, copay applied, covered amount) for the next step.

```mermaid
flowchart TD
    A[Line Item Received] --> B{1. Policy active\non service date?}
    B -- No --> DENY1[DENIED: POLICY_INACTIVE]
    B -- Yes --> C{2. Service type\ncovered in policy?}
    C -- No --> DENY2[DENIED: NOT_COVERED_SERVICE]
    C -- Yes --> D{3. Diagnosis code\nexcluded?}
    D -- Yes --> DENY3[DENIED: EXCLUDED_DIAGNOSIS]
    D -- No --> E{4. Pre-auth required\nand obtained?}
    E -- No --> DENY4[DENIED: PREAUTH_REQUIRED]
    E -- Yes --> F{5. Annual limit\nnot exhausted?\nSELECT FOR UPDATE}
    F -- Exhausted --> DENY5[DENIED: ANNUAL_LIMIT_EXHAUSTED]
    F -- OK --> G{6. Per-visit limit\nnot exceeded?}
    G -- Exceeded --> PARTIAL[Cap billed_amount\nto per_visit_limit]
    G -- OK --> H[7. Apply deductible\nif not met]
    PARTIAL --> H
    H --> I[8. Apply copay]
    I --> J[9. Apply coverage %\nto remaining balance]
    J --> K[10. Write adjudication_result\nUpdate annual_usages\nEmit ClaimAdjudicated event]
    K --> APPROVE[COVERED / PARTIALLY_COVERED]
    DENY1 & DENY2 & DENY3 & DENY4 & DENY5 --> AUDIT[Write adjudication_result\nEmit ClaimDenied event]
```

### Step Details

| Step | What Is Checked | Denial Code |
|------|-----------------|-------------|
| 1 | `policy.effective_date <= service_date <= policy.expiration_date` | `POLICY_INACTIVE` |
| 2 | Coverage rule exists for `line_item.service_type` | `NOT_COVERED_SERVICE` |
| 3 | `line_item.diagnosis_code` not in `coverage_rule.excluded_diagnosis_codes` | `EXCLUDED_DIAGNOSIS` |
| 4 | `coverage_rule.requires_preauth == False` (or preauth on record) | `PREAUTH_REQUIRED` |
| 5 | `annual_usages.used_amount + billed_amount <= coverage_rule.annual_limit` | `ANNUAL_LIMIT_EXHAUSTED` |
| 6 | `billed_amount <= coverage_rule.per_visit_limit` (caps if exceeded) | _(caps, not denies)_ |
| 7 | Deductible reduction: if `policy.deductible_met == False`, subtract from billed | _(state update)_ |
| 8 | Copay deduction: subtract `coverage_rule.copay` from remaining balance | _(state update)_ |
| 9 | Apply `coverage_rule.coverage_percentage` to post-deductible/copay balance | _(final covered amount)_ |
| 10 | Persist result; update `annual_usages.used_amount`; emit domain event | _(side effects)_ |

### Explanation Output

Every adjudication result carries a prose explanation constructed during processing:

```
Your annual benefit of $2,000.00 for SPECIALIST_VISIT has been fully
used for benefit year 2026. No further specialist visits are covered
under this policy until January 1, 2027.
```

Accessible via `GET /api/v1/claims/{id}/explain`.

---

## Scheduled Jobs

**There are no active cron jobs in the current deployment.** The Helm chart includes a `CronJob` template ready for activation; no implementation ships in v1.0. The decision was deliberate: prematurely running benefit-year rollover logic against production data before the rollover procedure is audited creates liability. Each job below requires a separate approval gate before activation.

### Planned Kubernetes CronJobs

| Job | Schedule | Description |
|-----|----------|-------------|
| `benefit-year-rollover` | `0 0 1 1 *` (Jan 1, midnight UTC) | Resets `annual_usages.used_amount` to `0` for all active policies; marks prior-year records as archived |
| `claim-aging` | `0 6 * * *` (daily 06:00 UTC) | Escalates `SUBMITTED` claims older than 30 days to `UNDER_REVIEW`; emits `ClaimEscalated` domain event |
| `nightly-reporting` | `0 2 * * *` (daily 02:00 UTC) | Aggregates adjudication metrics, denial rates, and financial summaries; exports Parquet to S3 |

To enable a job:

```yaml
# infrastructure/helm/claims-system/values.yaml
cronJobs:
  benefitYearRollover:
    enabled: true
  claimAging:
    enabled: true
```

---

## Quick Start

### Prerequisites

- Docker 24+ and Docker Compose v2
- `make` (GNU Make)
- Ports 3000, 8000, 5432, 6379 available locally

### Start in Three Commands

```bash
git clone https://github.com/sumitkumarmallick/claimsiq.git
cd claimsiq

make dev          # docker compose up -d --build
make migrate      # alembic upgrade head (runs inside backend container)
make seed         # register the four demo accounts
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |

### Demo Accounts

| Email | Password | Role |
|-------|----------|------|
| admin@claimsiq.com | Admin1234! | ADMIN |
| processor@claimsiq.com | Processor1! | CLAIM_PROCESSOR |
| provider@citymed.com | Provider1! | PROVIDER (NPI: 1234567890) |
| patient@example.com | Patient1! | PATIENT |

### First API Call

```bash
# Obtain a token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@claimsiq.com","password":"Admin1234!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# View platform statistics
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/stats
```

---

## End-to-End User Flows

This section walks through every page of the ClaimsIQ UI for each role. Start the platform with `make dev && make migrate && make seed`, then open http://localhost:3000.

### Demo Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@claimsiq.com | Admin1234! |
| Claim Processor | processor@claimsiq.com | Processor1! |
| Provider | provider@citymed.com | Provider1! |
| Patient | patient@example.com | Patient1! |

---

### Role: ADMIN

The Admin sees the full platform — stats, all claims, all members, all disputes, and user management.

#### 1. Dashboard (`/`)

- Displays live platform statistics: total claims, approval rate, this-month submissions.
- Four quick-action cards: **New Claim**, **Register Member**, **Member Directory**, **Disputes**.
- Recent claims table shows all claims across all members.

#### 2. Submit a Claim (`/claims/new`)

- Fill **Member ID** and **Policy ID** (copy from Member Directory or Demo Setup).
- Enter **Provider Name** and **NPI** (10 digits).
- Add one or more line items: service type, ICD-10 diagnosis code, CPT procedure code, billed amount, service date.
- Click **Submit Claim** — adjudication runs immediately server-side.
- Redirects to the claim detail page showing per-line-item coverage decisions.

#### 3. Claims List (`/claims`)

- Shows all claims across every member.
- Filter by status (SUBMITTED, APPROVED, DENIED, etc.).
- Click any row → Claim Detail.

#### 4. Claim Detail (`/claims/[id]`)

- Full adjudication breakdown per line item: covered amount, denial reason, deductible applied, copay applied.
- **Explain** tab gives a plain-English explanation per line item.
- **Dispute** button files a dispute for the whole claim or a specific line item.

#### 5. Member Directory (`/members`)

- Table of all registered members.
- Each row shows member name and plan-issued member ID.
- **Register Member** button opens the new-member form.

#### 6. Register Member (`/members/new`)

- Fields: Full Name, Date of Birth, Plan-issued Member ID, Contact Email.
- On submit creates the member record (PHI fields encrypted at rest).
- Shows the generated UUID — copy it for policy creation.

#### 7. Policies (`/policies` — or via Members)

- Lists all policies with effective date, expiration date, status, deductible.
- **Create Policy** links a policy to an existing member with configurable coverage rules.

#### 8. Disputes (`/disputes`)

- Lists all open and resolved disputes.
- Click **Resolve** → enter outcome (UPHELD / DENIED) and resolution notes.

#### 9. User Management (`/admin/users`)

- Full user table: email, name, role, active status.
- Change any user's role (dropdown).
- Deactivate accounts.
- This page is **Admin-only** — other roles receive a 403.

#### 10. Demo Setup (`/demo`)

- One-click provisioning: creates a test member (Alex Johnson) + comprehensive policy.
- Displays generated Member ID and Policy ID with copy buttons.
- **Submit a Claim with These IDs** button pre-fills the claim form.

---

### Role: CLAIM_PROCESSOR

Same as Admin minus User Management. The Claim Processor's primary workflow is the claim queue and dispute resolution.

#### Typical daily flow

1. **Login** → Dashboard shows today's submission count and approval rate.
2. **Claims** → filter by `SUBMITTED` → work through unreviewed claims.
3. **Claim Detail** → review adjudication breakdown → escalate to `UNDER_REVIEW` if manual review needed.
4. **Disputes** → resolve pending disputes: read member's reason, check adjudication, enter UPHELD/DENIED + notes.
5. **Member Directory** → register new members as enrollment requests arrive.
6. **Demo Setup** → quickly provision test data for QA or demos.

**Pages available:** Dashboard, Submit Claim, Claims List, Claim Detail, Members, Register Member, Policies, Create Policy, Disputes, Demo Setup.

**Pages not available:** User Management (`/admin/users`) — redirects with "Admin access required".

---

### Role: PROVIDER

Providers submit claims under their NPI and see only claims filed from their NPI.

#### 1. Dashboard (`/`)

- Shows only the **Submit a Claim** quick-action card (no stats, no member management).
- Recent claims table is scoped to this provider's NPI.

#### 2. Submit a Claim (`/claims/new`)

- **Requires a Member ID and Policy ID** from the patient's insurer.
- Enter the NPI (pre-filled with the provider's registered NPI if available).
- Add clinical line items (service type, diagnosis, procedure, billed amount).
- Submit → immediate adjudication → review covered vs. denied line items.

#### 3. Claims List (`/claims`)

- Scoped to claims submitted under this provider's NPI only.
- Can see status, adjudication result, and dispute status.

#### 4. Claim Detail + Disputes

- View the full adjudication breakdown for each claim.
- File a dispute if coverage was incorrectly denied.

**Pages not available:** Member Directory, Register Member, Policies, User Management, Demo Setup (redirects with "Staff Access Required").

---

### Role: PATIENT

Patients have a self-service portal: insurance card, claim history, disputes.

#### 1. Dashboard (`/`)

- Welcome card showing the patient's name and role.
- Quick-action card: **My Insurance** (to view their insurance card and submit a claim).
- Recent claims table scoped to their linked member record.
- No stats, no member management, no admin actions.

#### 2. My Insurance (`/my-insurance`)

**If insurance is not yet linked (new patient):**

- Shows a **pending activation** preview with:
  - A frosted-glass insurance card showing the patient's actual name and a "PENDING" badge.
  - Sample coverage table (7 service types) mirroring a real Silver-tier plan.
  - Sample deductible tracker at $0.
  - 4-step activation guide with the patient's registered email shown in a code block.
  - A hidden activation shortcut: navigate to `/activate-insurance` to instantly provision a demo member + policy.

**If insurance is linked:**

- Digital insurance card (dark blue gradient) showing:
  - Member name, Plan-issued Member ID, Policy Number
  - Effective date, expiration date, policy status badge
- Deductible progress bar (amount met / total deductible).
- Out-of-Pocket Maximum progress bar.
- Full coverage rules table (service type, coverage %, copay, annual limit, preauth required).
- **Submit a Claim** button — pre-fills Member ID and Policy ID automatically.

#### 3. Activate Insurance (`/activate-insurance`) — hidden

- Not shown in sidebar navigation — access by direct URL only.
- On page load, automatically calls `POST /api/v1/auth/me/activate-demo`:
  - Creates a demo MemberORM record using the patient's registered name.
  - Creates a PolicyORM for the current benefit year with 7 service types.
  - Links the new member UUID to `users.member_id`.
- Shows a spinner ("Activating your insurance…"), then a green checkmark.
- Redirects to `/my-insurance` where the patient now sees their live insurance card.
- **Idempotent**: if the patient already has insurance linked, redirects immediately without creating duplicate records.

#### 4. Submit a Claim (`/claims/new`) — patient-specific flow

- Member ID and Policy ID are **auto-fetched** from the patient's linked record and shown as a read-only summary card — no manual copy-paste required.
- Patient fills in: Provider Name, Provider NPI, and line items.
- If no insurance is linked, shows an "Insurance not linked" full-page message with a link to `/my-insurance`.

#### 5. Claims History (`/claims`)

- Lists only the patient's own claims (scoped by member_id).
- Shows claim status, date, total billed vs. total covered.
- Click → Claim Detail with adjudication breakdown and plain-English explanations.

#### 6. File a Dispute

- From Claim Detail → click **Dispute** on a denied or partially-covered line item.
- Enter reason (minimum 10 characters).
- Dispute goes to Claim Processor queue for review.
- Patient can track dispute status in the claim detail view.

---

### Page → Role Access Matrix

| Page | ADMIN | CLAIM_PROCESSOR | PROVIDER | PATIENT |
|------|:-----:|:---------------:|:--------:|:-------:|
| Dashboard `/` | Full stats | Full stats | Scoped | Welcome card |
| My Insurance `/my-insurance` | — | — | — | Full portal |
| Activate Insurance `/activate-insurance` | Redirect `/` | Redirect `/` | Redirect `/` | Self-service |
| Submit Claim `/claims/new` | Yes | Yes | Yes | Auto-fill |
| Claims List `/claims` | All | All | Own NPI | Own only |
| Claim Detail `/claims/[id]` | Yes | Yes | Own NPI | Own only |
| Disputes `/disputes` | Yes | Yes | — | Via claim detail |
| Member Directory `/members` | Yes | Yes | — | — |
| Register Member `/members/new` | Yes | Yes | — | — |
| Policies `/policies` | Yes | Yes | — | — |
| Demo Setup `/demo` | Yes | Yes | Blocked | Blocked |
| User Management `/admin/users` | Yes | Blocked | Blocked | Blocked |

---

## Deployment Guide

### Local (no Docker)

```bash
# Backend
cd app/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit DATABASE_URL, REDIS_URL, PHI_ENCRYPTION_KEY
alembic upgrade head
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd app/frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

### Docker Compose (Development / Staging)

```bash
make dev          # Start: postgres, redis, backend, frontend
make migrate      # Apply pending Alembic migrations
make seed         # Load demo data
make logs         # Follow all container logs
make down         # Stop and remove containers + volumes
```

### Kubernetes (Helm)

```bash
# Add secrets to your values override file first
cp infrastructure/helm/claims-system/values.yaml my-values.yaml
# Edit my-values.yaml: set image tags, secrets, ingress host

helm upgrade --install claims-system \
  infrastructure/helm/claims-system \
  --namespace claims \
  --create-namespace \
  --values my-values.yaml \
  --wait
```

The Helm chart provisions:

- `Deployment` for backend and frontend with configurable replica counts
- `HorizontalPodAutoscaler` on backend (CPU 70% threshold)
- `CronJob` templates for benefit-year rollover and claim aging (disabled by default)
- `Ingress` with TLS termination
- `ConfigMap` and `Secret` templates for environment injection

### AWS (Terraform)

```bash
cd infrastructure/terraform

# Initialize providers
terraform init

# Review the plan
terraform plan -var-file=production.tfvars

# Apply
terraform apply -var-file=production.tfvars
```

Terraform provisions:

| Resource | Purpose |
|----------|---------|
| **EKS** | Managed Kubernetes cluster for backend and frontend workloads |
| **RDS PostgreSQL 16** | Multi-AZ primary store with automated snapshots |
| **ElastiCache Redis 7** | Cluster mode disabled (single primary, one replica) |
| **MSK (Kafka)** | Two-broker cluster for domain event streaming |
| **ALB** | Application Load Balancer with ACM certificate |
| **ECR** | Private container registry for backend and frontend images |
| **S3** | Nightly report storage and Terraform state backend |
| **IAM** | IRSA roles for EKS pod-level AWS API access |
| **VPC** | Three-tier network: public (ALB), private (EKS nodes), isolated (RDS/ElastiCache) |

### CI/CD (GitHub Actions)

Pipeline defined at `.github/workflows/ci.yml`:

```
push / pull_request
  └─ test          pytest (domain + integration), coverage gate
  └─ lint          ruff, mypy, tsc --noEmit
  └─ scan          Trivy CVE scan on built Docker image
  └─ deploy        helm upgrade (main branch only, after all gates pass)
```

---

## API Reference

All endpoints are prefixed `/api/v1`. Full interactive documentation available at `/docs` (Swagger UI) and `/redoc`.

### Authentication

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/auth/register` | Register a new user | None |
| `POST` | `/auth/login` | Obtain JWT access token | None |
| `GET` | `/auth/me` | Get current user profile | Bearer |

### Claims

| Method | Path | Description | Min Role |
|--------|------|-------------|----------|
| `POST` | `/claims/` | Submit a new claim with line items; triggers immediate adjudication | CLAIM_PROCESSOR / PROVIDER |
| `GET` | `/claims/` | List claims (scoped by role: all / own NPI / own member) | Any |
| `GET` | `/claims/{id}` | Claim detail with line items and adjudication results | Any (scoped) |
| `GET` | `/claims/{id}/explain` | Plain-English adjudication explanation per line item | Any (scoped) |

### Disputes

| Method | Path | Description | Min Role |
|--------|------|-------------|----------|
| `POST` | `/disputes/claims/{claim_id}` | File a dispute against a claim or specific line item | Any (scoped) |
| `POST` | `/disputes/{id}/resolve` | Resolve a dispute with outcome and notes | CLAIM_PROCESSOR |

### Members & Policies

| Method | Path | Description | Min Role |
|--------|------|-------------|----------|
| `GET` | `/members` | List all members | CLAIM_PROCESSOR |
| `POST` | `/members` | Register a new member with PHI | CLAIM_PROCESSOR |
| `GET` | `/policies` | List policies | CLAIM_PROCESSOR |
| `POST` | `/policies` | Create a policy with coverage rules | CLAIM_PROCESSOR |

### Platform

| Method | Path | Description | Min Role |
|--------|------|-------------|----------|
| `GET` | `/stats` | Aggregate platform statistics | CLAIM_PROCESSOR |

### Claim Status Lifecycle

```
SUBMITTED → UNDER_REVIEW → APPROVED
                         → PARTIALLY_APPROVED
                         → DENIED
APPROVED / PARTIALLY_APPROVED → PAID
Any non-terminal → CANCELLED
```

### Dispute Status Lifecycle

```
SUBMITTED → UNDER_REVIEW → UPHELD
                         → DENIED
```

---

## Environment Variables

### Backend (`app/backend/.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | Async PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `DATABASE_URL_SYNC` | Yes | — | Sync DSN for Alembic migrations (`postgresql+psycopg2://...`) |
| `REDIS_URL` | Yes | — | Redis connection string (`redis://...`) |
| `PHI_ENCRYPTION_KEY` | Yes | — | Base64 Fernet key for PHI field encryption. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SECRET_KEY` | Yes | — | JWT signing secret (min 32 chars). Generate: `openssl rand -hex 32` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | JWT access token TTL |
| `KAFKA_BOOTSTRAP_SERVERS` | No | — | Kafka broker list (e.g. `broker1:9092,broker2:9092`). If unset, Kafka publishing is disabled. |
| `KAFKA_TOPIC_CLAIMS` | No | `claims.events` | Kafka topic for domain events |
| `ENVIRONMENT` | No | `development` | `development` / `staging` / `production` — controls log level and CORS |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `LOG_LEVEL` | No | `INFO` | Python logging level |

### Frontend (`app/frontend/.env.local`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | `http://localhost:8000` | Backend API base URL |

---

## Development Workflow

```bash
make help              # Print all available commands

# ── Day-to-day ──────────────────────────────────────────────────────
make dev               # Start all services (docker compose up -d --build)
make logs              # Follow all container logs
make db-shell          # Open psql prompt in the postgres container
make down              # Stop and destroy containers and volumes

# ── Database migrations ─────────────────────────────────────────────
make migrate                         # Apply all pending migrations
make migrate-new msg="add audit_log" # Auto-generate migration from model diff
make migrate-rollback                # Rollback one migration step
make migrate-history                 # Show full migration history

# ── Testing ─────────────────────────────────────────────────────────
make test              # Full suite: backend pytest + frontend tsc
make test-backend      # pytest with coverage report
                       # Domain tests run without a database connection

# ── Code quality ────────────────────────────────────────────────────
make lint              # ruff check + mypy (Python) + tsc --noEmit (TypeScript)

# ── Build ───────────────────────────────────────────────────────────
make build             # Build Docker images without starting containers
make seed              # POST the four demo accounts to a running backend
```

### Running Domain Tests in Isolation

The domain layer has zero infrastructure dependencies. Tests run without PostgreSQL or Redis:

```bash
cd app/backend
pytest tests/domain/ -v
# Runs in < 1 second; no Docker required
```

### Integration Tests

```bash
docker compose up postgres -d

TEST_DATABASE_URL=postgresql+asyncpg://claims:claims@localhost:5432/claimsdb_test \
pytest tests/api/ -v --tb=short --cov=claims --cov-report=term-missing
```

---

## Security Considerations

### PHI Encryption at Rest

All Protected Health Information (diagnosis codes, member names, dates of birth, email addresses) is encrypted at the application layer using **Fernet symmetric encryption** (AES-128-CBC + HMAC-SHA256) before being written to PostgreSQL. A database administrator with direct table access cannot read PHI without the `PHI_ENCRYPTION_KEY`.

Key rotation is supported via `MultiFernet`: set `PHI_ENCRYPTION_KEY` to a comma-separated list of Fernet keys. The first key is used for encryption; all keys are tried for decryption, enabling zero-downtime rotation.

**Production recommendation:** Replace the environment-variable key with AWS KMS envelope encryption — generate a per-row data key, encrypt it with a KMS CMK, and store the encrypted data key alongside the ciphertext. This eliminates the static key from environment variables entirely.

### JWT Security

- Tokens are signed with `HS256` by default; the codebase is RS256-ready (swap the signing key for a PEM keypair).
- Token expiry defaults to 30 minutes. Refresh token support is a planned addition.
- Role claims embedded in the JWT are verified on every request. No database lookup is required, but this means role changes do not take effect until token expiry. For ADMIN operations with immediate revocation requirements, pair with a Redis blocklist.

### RBAC Data Scoping

Role enforcement is two-layered:

1. **Route-level:** FastAPI dependencies reject requests from roles without permission before any query runs.
2. **Query-level:** Repository methods accept a `current_user` parameter and apply `WHERE member_id = :user_member_id` or `WHERE provider_npi = :user_npi` filters. A PATIENT cannot retrieve another member's claims by guessing a UUID.

### Input Validation

Pydantic v2 validates all incoming request bodies at the API boundary. ICD-10 and CPT codes are validated against format patterns. `NUMERIC(12,2)` in PostgreSQL rejects values that would cause precision loss.

### SQL Injection

All queries use SQLAlchemy's parameterized ORM layer. Raw SQL strings are not used anywhere in the codebase.

### Container Security

The GitHub Actions CI pipeline runs **Trivy** container image scanning on every build. High and critical CVEs block deployment. Base images are pinned to digest-locked versions in production Dockerfiles.

### Network Security (AWS)

- RDS and ElastiCache are in the isolated subnet tier with no public IP.
- EKS nodes are in the private subnet tier; only the ALB is public-facing.
- Security groups restrict database access to EKS node security group only.
- All inter-service traffic within VPC is on private IPs; no public endpoints for internal services.

### HIPAA Alignment Notes

ClaimsIQ is designed with HIPAA technical safeguard requirements in mind:

- PHI encrypted at rest (Fernet) and in transit (TLS 1.2+)
- Audit log via append-only `domain_events` table
- Access control enforced at both route and data query layers
- No PHI in application logs (diagnosis codes are never logged in plaintext)

ClaimsIQ is not a BAA-covered service out of the box. Organizations deploying ClaimsIQ in a HIPAA environment must execute a BAA with AWS and complete an organizational risk analysis.

---

## Project Structure

```
claimsiq/
├── app/
│   ├── backend/
│   │   ├── claims/
│   │   │   ├── domain/             # Pure Python — no I/O
│   │   │   │   ├── adjudicator.py  # 10-step adjudication engine
│   │   │   │   ├── entities.py     # Claim, Policy, Member, LineItem
│   │   │   │   ├── events.py       # Domain event definitions
│   │   │   │   ├── state_machines.py
│   │   │   │   └── value_objects.py
│   │   │   ├── application/
│   │   │   │   └── services.py     # Use case orchestration
│   │   │   ├── infrastructure/
│   │   │   │   ├── database.py     # SQLAlchemy async engine
│   │   │   │   ├── encryption.py   # Fernet PHI encryption
│   │   │   │   ├── models.py       # ORM table definitions
│   │   │   │   ├── repositories.py # Data access + SELECT FOR UPDATE
│   │   │   │   ├── cache.py        # Redis coverage rule cache
│   │   │   │   └── kafka.py        # Domain event publisher
│   │   │   └── api/
│   │   │       ├── schemas.py      # Pydantic request/response models
│   │   │       ├── deps.py         # JWT auth + RBAC dependencies
│   │   │       └── routes/
│   │   │           ├── auth.py
│   │   │           ├── claims.py
│   │   │           ├── disputes.py
│   │   │           └── members.py
│   │   ├── tests/
│   │   │   ├── domain/             # Unit tests (no DB required)
│   │   │   └── api/                # Integration tests
│   │   ├── alembic/
│   │   │   └── versions/           # 0001_initial, 0002_users, 0003_indexes
│   │   ├── main.py
│   │   └── requirements.txt
│   └── frontend/
│       ├── app/                    # Next.js 14 App Router
│       ├── components/
│       └── lib/
├── infrastructure/
│   ├── docker/
│   ├── helm/
│   │   └── claims-system/
│   ├── kubernetes/
│   └── terraform/
│       ├── main.tf
│       ├── eks.tf
│       ├── rds.tf
│       ├── elasticache.tf
│       └── msk.tf
├── docs/
│   ├── domain-model.md
│   ├── decisions.md
│   └── self-review.md
├── .github/
│   └── workflows/
│       └── ci.yml
├── Makefile
├── docker-compose.yml
└── LICENSE
```

---

## License

MIT License — Copyright (c) 2026 Sumit Kumar Mallick

See [LICENSE](./LICENSE) for the full text.
