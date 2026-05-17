# Decisions & Trade-offs

## What I built

A working claims adjudication system with:
- RESTful API (FastAPI + PostgreSQL + Redis)
- Domain model: Member, Policy, CoverageRule, Claim, LineItem, AdjudicationResult, Dispute
- State machines for Claim, LineItem, and Dispute lifecycles
- Coverage adjudication engine (10-step decision sequence)
- PHI field encryption at the infrastructure layer
- Domain events (persisted to DB; Kafka publish-ready)
- React/Next.js frontend that calls the real API
- Docker Compose for local dev (postgres + redis + backend + frontend)
- Kubernetes manifests + Helm chart for production deployment
- GitHub Actions CI/CD pipeline
- 30+ tests covering domain rules and API behavior

## What I didn't build (and why)

**Authentication & authorization** — Out of scope per the assignment. In production this would be OAuth2/JWT with role-based access (claims rep vs. member vs. auditor). I left clear gaps in the API — no auth middleware — rather than adding stub auth that pretends to be real.

**Async adjudication queue** — The adjudicator is called synchronously after claim submission. In production, you'd enqueue adjudication jobs (SQS or Kafka) and return a 202 Accepted immediately, then poll for results. This is the right architecture for high volume, but it adds significant complexity (async result polling, status webhooks, retry logic). For a demo, synchronous is cleaner and the flows are directly observable. This is called out in the README and self-review.

**Real Kafka publishing** — Domain events are written to a `domain_events` table in PostgreSQL (transactional outbox pattern). The Kafka producer is wired to send them but gated by `ENABLE_KAFKA=false` in dev. The infrastructure (MSK Kafka on AWS) is defined in Terraform. The event types are fully defined — just not published by default.

**Key Management Service (KMS) for PHI** — PHI fields are encrypted with Fernet (AES-128-CBC) using a key in an environment variable. In production this key would live in AWS KMS with envelope encryption. I implemented the encryption correctly; the key storage location is the gap.

**Full annual limit reset logic** — The `benefit_year` field on `AnnualUsage` supports per-year tracking. The code correctly scopes usage to the service date's year. What's missing is a cleanup job to reset/archive stale usage rows at year-end.

**Preauth workflow** — The adjudicator checks `requires_preauth` but the system has no way to record preauth grants. The `preauth_granted=False` default in `AdjudicationContext` means any service with `requires_preauth=True` will be denied. A real system needs a Preauth table and an API to record grants. I didn't build it because it's a whole sub-domain.

**Out-of-pocket max enforcement** — The Policy has an `out_of_pocket_max` field but the adjudicator doesn't check it. This is a known gap (see self-review). It requires summing all cost-sharing (deductible + copay + member remainder) across all claims for the year, which requires an additional usage tracker.

**Email/notification** — Out of scope per the assignment.

**Multi-tenant / role-based access** — Out of scope.

---

## Assumptions I made

**Diagnosis codes on the claim, not a diagnosis table** — In a real system you might have a separate Diagnosis entity with more structure (primary vs. secondary, POA indicators). I went with a single ICD-10 code per line item. This covers the adjudication rules sufficiently and keeps the model lean.

**NPI is a 10-digit string without Luhn validation** — NPIs follow a Luhn algorithm. I validate length and numeric format but not the checksum. Would add in a real system.

**One policy per claim** — The claim references a single policy_id. In reality, a member might have primary + secondary insurance (COB — Coordination of Benefits). COB is a significant domain extension I explicitly scoped out.

**Annual limit is per-policy, per-service-type** — Some plans pool limits (e.g., a combined mental health + substance abuse limit). I model per-service-type limits only. Adding pooled limits would require a rule-level `limit_group` field and usage tracking by group.

**Coverage rules are flat, not hierarchical** — Real plans have network tiers (in-network vs. out-of-network at different rates). I have `network_restriction` on the rule but don't build network-based adjudication. You'd need a provider network table and a lookup on claim submission.

**Synchronous adjudication** — I trigger adjudication immediately after submission and return the result in the POST /claims response. The assignment says "Accepts claim submissions... Adjudicates... Moves claims through lifecycle states" — I interpret this as: show the full lifecycle, not necessarily in a specific async pattern. The architecture is ready for async (domain events, Kafka defined) but the happy path is synchronous for observability in the demo.

---

## Tech stack decisions

**Python + FastAPI** — Async-native, strong typing with Pydantic v2, excellent for domain modeling. The type hints actually encode domain invariants (e.g., `Money` value object, typed enums). FastAPI's dependency injection fits the repository pattern cleanly.

**PostgreSQL over MongoDB** — This domain is relational: policies → rules, claims → line items, adjudication results → rules. JSONB handles the flexible coverage rule attributes (excluded_diagnosis_codes). PostgreSQL's `SELECT FOR UPDATE` is exactly what we need for annual limit concurrency.

**SQLAlchemy 2.0 async** — Async throughout. `asyncpg` is fast. The ORM stays out of the domain layer (repository pattern). Alembic for migrations.

**Hexagonal architecture** — Domain entities import nothing from SQLAlchemy. Infrastructure imports from domain but never vice versa. This made the domain unit tests trivial to write (no DB required, no mocks). The architecture also means we could swap PostgreSQL for a different store without touching a single domain file.

**Redis for caching** — Annual usage data and policy lookups are hot reads (hit on every adjudication). Redis with cache-aside pattern reduces DB load. In dev, `ENABLE_REDIS_CACHE=true` but cache misses gracefully fall back to DB.

**Next.js 14 for frontend** — Server components + client components, TypeScript throughout. @tanstack/react-query for data fetching. Minimal dependency footprint; the UI exists to demonstrate the system, not to be a full product.

---

## CAP theorem stance

**Claims adjudication: CP (Consistency + Partition Tolerance)**

Annual limits are financial commitments. If we approve more than the limit, we've made a commitment we can't reclaim. Under partition, we should block (and return 503) rather than allow potentially inconsistent writes.

PostgreSQL with synchronous Multi-AZ replication on RDS satisfies this. Every write is synchronous to the standby — we never read stale data after a commit.

Redis is CP in `--appendonly yes` mode, but it's used for caching (read path only). A Redis partition causes a cache miss, which falls through to Postgres. No consistency risk on writes.

Kafka for domain events is AP — we prefer availability for event publishing (events can be retried). A transactional outbox pattern (events table in Postgres) ensures no event is lost even if Kafka is temporarily unavailable.

---

## Software design patterns used

| Pattern | Where |
|---------|-------|
| Aggregate Root | `Claim` owns LineItems and DomainEvents |
| Repository | `ClaimRepository`, `PolicyRepository`, etc. |
| Value Object | `Money`, `DiagnosisCode`, `ProcedureCode` |
| State Machine | Explicit transition tables for Claim, LineItem, Dispute |
| Strategy (implicit) | Each CoverageRule is a parameterized adjudication strategy |
| Command | `SubmitClaimCommand`, `SubmitDisputeCommand` |
| Domain Events | `ClaimSubmitted`, `LineItemAdjudicated`, etc. |
| Transactional Outbox | Domain events in Postgres → Kafka publisher |
| Factory | `_generate_claim_number()` |
| Hexagonal / Ports & Adapters | Domain ↔ Application ↔ Infrastructure ↔ API |
| Pessimistic Locking | `SELECT FOR UPDATE` on `annual_usages` |
| Cache-aside | Redis for policy/usage caching |
