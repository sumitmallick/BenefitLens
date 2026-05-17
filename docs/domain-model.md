# Domain Model

## Why this decomposition?

Insurance claim processing looks simple from the outside but is messy at the seams. The interesting questions:

1. **What does "covered" mean?** Not a boolean — it's a function of service type, diagnosis, annual limits, deductibles, copays, preauth status, and network.
2. **What's the unit of adjudication?** The line item, not the claim. A claim with 5 line items can have 3 covered, 1 denied, 1 needing review simultaneously.
3. **How do you track limits without double-spend?** Annual limits are a shared resource across claims. Concurrent submissions can race to consume them.
4. **How do you explain a denial clearly?** The adjudicator must produce an explanation alongside every decision, not just a code.

These questions shaped every entity and relationship below.

---

## Entities

### Member
The policy holder. Contains PHI: name, date of birth, plan-issued member ID, email. All encrypted at the infrastructure layer.

**Invariant:** A member can have multiple policies, but only one active policy per service date.

### Policy
The contract that determines coverage. Carries:
- `effective_date` / `expiration_date` — coverage window
- `deductible_amount` / `deductible_met` — how much the member must pay before insurance contributes
- `out_of_pocket_max` — cap on member's total annual cost-sharing
- A collection of `CoverageRule` objects

**Invariant:** Deductible can never exceed `deductible_amount`.

### CoverageRule
The workhorse of adjudication. One rule per service type per policy. Carries:
- `service_type` — which service it applies to (enum: PRIMARY_CARE, SPECIALIST_VISIT, EMERGENCY, etc.)
- `coverage_percentage` — what fraction the insurer pays (0–100)
- `annual_limit` — optional hard cap per year (e.g., $5,000 of specialist visits)
- `per_visit_limit` — optional cap per visit (e.g., $300/specialist visit)
- `copay` — flat fee the member pays per visit before coverage percentage applies
- `requires_preauth` — whether prior authorization must be on file
- `excluded_diagnosis_codes` — ICD-10 codes excluded from this rule even if service type matches

**Design decision:** Coverage rules as data (stored in DB as JSONB), not code. This allows non-engineers to update rules without a deploy. The trade-off: we can't verify rule correctness at compile time. We compensate with validation on write and test fixtures that exercise rule edge cases.

### AnnualUsage
Tracks dollars consumed per (policy, service_type, benefit_year). One row per combination, with a UniqueConstraint. Used by the adjudicator to check remaining annual allowance and updated atomically via SELECT FOR UPDATE.

**Why a separate table?** Embedding usage in Policy would require locking the whole policy row on every adjudication. A dedicated table locks at the narrowest possible granularity.

### Claim (Aggregate Root)
The claim ties everything together. It's the aggregate root — all mutations to line items flow through the Claim.

- `claim_number` — human-readable identifier (CLM-YYYYMMDD-XXXXXX)
- `status` — drives the state machine
- `provider_name` / `provider_npi` — who delivered the service
- Contains a list of `LineItem` objects
- Accumulates `DomainEvent` objects (published post-commit)

### LineItem
A single service in the claim. Each has its own `status` and `adjudication`.

**PHI:** `diagnosis_code` (ICD-10) is encrypted at rest. Excluded from list API responses. Present only in claim detail responses.

### AdjudicationResult
The output of running the adjudicator. Attached 1:1 to a LineItem after adjudication.

Contains:
- `covered_amount` — what the insurer will pay
- `denial_reason` — structured code (enum)
- `explanation` — plain-English prose for the member
- `deductible_applied` / `copay_applied` — for transparency
- `applied_rule_id` — which CoverageRule made this decision (audit trail)

### Dispute
A member's challenge to a claim or line item decision.

- `line_item_id=None` means the member is disputing the entire claim outcome
- Drives a separate state machine (SUBMITTED → UNDER_REVIEW → UPHELD | DENIED)
- Upheld dispute does not auto-re-adjudicate; it signals claims ops to reprocess

---

## State Machines

### Claim State Machine

```
                    ┌─────────┐
              ┌────►│ VOIDED  │◄───────────────────────┐
              │     └─────────┘                         │
              │                                         │
        SUBMITTED ──────────► UNDER_REVIEW ─────────────┤
                                    │                   │
                         ┌──────────┼──────────┐        │
                         ▼          ▼          ▼        │
                      APPROVED  PARTIALLY   DENIED      │
                      (all li)  _APPROVED   (all li)    │
                         │     (mixed li)     │          │
                         └────────┬───────────┘         │
                                  ▼                      │
                               DISPUTED ◄────────────────┘
                                  │
                                  ▼
                         DISPUTE_RESOLVED
                                  │
                                  ▼
                               PAID ◄── (from APPROVED/PARTIALLY_APPROVED)
```

Key invariants:
- `PAID` and `VOIDED` are terminal — no exits
- A `DENIED` claim cannot move to `PAID` without going through `DISPUTED → DISPUTE_RESOLVED`
- `SUBMITTED` cannot skip to `APPROVED` (must pass through adjudication in `UNDER_REVIEW`)

### LineItem State Machine

```
PENDING ──────────► COVERED        (terminal)
        │──────────► PARTIALLY_COVERED (terminal)
        │──────────► DENIED        (terminal)
        └──────────► NEEDS_REVIEW ─► COVERED | PARTIALLY_COVERED | DENIED
```

NEEDS_REVIEW is for line items requiring human intervention (e.g., out-of-network preauth escalation). Not currently triggered automatically; reserved for future rules.

### Dispute State Machine

```
SUBMITTED ──► UNDER_REVIEW ──► UPHELD   (terminal)
                            └──► DENIED  (terminal)
```

---

## Coverage Adjudication: Decision Sequence

The adjudicator applies these checks in order:

1. **Policy active on service date?** If not → DENIED (SERVICE_DATE_OUT_OF_POLICY_PERIOD)
2. **Service type covered?** If no matching rule → DENIED (NOT_COVERED_SERVICE)
3. **Diagnosis code excluded?** If matched → DENIED (EXCLUDED_DIAGNOSIS)
4. **Preauth required but not on file?** → DENIED (REQUIRES_PREAUTH)
5. **Annual limit exhausted?** If remaining = $0 → DENIED (ANNUAL_LIMIT_EXHAUSTED)
6. **Per-visit limit** — cap billed amount (not a denial; reduces payable)
7. **Annual cap** — reduce to remaining annual allowance (partial approval)
8. **Deductible** — consume from billed amount; remainder proceeds to coverage
9. **Copay** — flat fee subtracted before coverage percentage
10. **Coverage percentage** — `covered = remainder × (coverage_pct / 100)`
11. **Status** — COVERED if covered == billed, PARTIALLY_COVERED if covered < billed, DENIED if covered == 0

**Preventive services bypass the deductible** (standard practice; encoded in adjudicator).

---

## PHI & Security Architecture

Health data (PHI under HIPAA) handled as follows:

| Field | Entity | Sensitivity | Storage |
|-------|---------|-------------|---------|
| member_id | Member | PHI | Encrypted (Fernet/AES-128) |
| name | Member | PHI | Encrypted |
| date_of_birth | Member | PHI | Encrypted |
| email | Member | PHI | Encrypted |
| diagnosis_code | LineItem | PHI | Encrypted |
| procedure_code | LineItem | Clinical | Plaintext (not PHI per se) |
| billed_amount | LineItem | Financial | Plaintext |

**Encryption:** Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256). Key stored in environment variable in dev; in production, use AWS KMS with envelope encryption.

**Logging:** PHI fields never appear in log output. Log statements reference only claim_number, member_id (UUID), and line_item_id — never name, DOB, or diagnosis codes.

**API exposure:**
- `GET /claims/member/:id` (list) — diagnosis codes **excluded**
- `GET /claims/:id` (detail) — diagnosis codes **included** (detail view, requires auth in prod)
- `GET /claims/:id/explain` — explanation text only, no raw PHI

**Production gaps (documented in self-review):**
- KMS envelope encryption not yet implemented (env var only)
- Field-level access control (ABAC) not implemented
- Audit log for PHI access queries not implemented

---

## Concurrency Model

**Annual limits are a shared resource.** Two claims for the same member + service type + year can race to consume the same pool of $5,000.

Solution: `SELECT FOR UPDATE` on the `annual_usages` row in `AnnualUsageRepository.get_for_update()`. PostgreSQL acquires a row-level exclusive lock for the transaction duration. Concurrent adjudications for the same (policy, service_type, year) serialize on this lock.

This is a deliberate CP (Consistency over Availability) choice: under partition or slow DB, adjudication blocks rather than allowing double-spend. Appropriate for financial data.

**Trade-off:** High-concurrency scenarios (many claims for the same service type in a year) will serialize. At realistic claim volumes (thousands/day, not millions/second), this is not a bottleneck. A future optimisation is to buffer usages in Redis with atomic INCR and reconcile to Postgres on a schedule — but that adds complexity and introduces eventual consistency, which requires explicit modeling.
