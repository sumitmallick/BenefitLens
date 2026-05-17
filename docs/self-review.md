# Self-Review

## What's good

**Domain model is coherent.** The adjudicator is a pure function (no I/O) that takes a LineItem + AdjudicationContext and returns a result. I can run every adjudication scenario as a pure unit test in milliseconds without a database. The 10-step decision sequence mirrors real-world claims processing order, which means it's debuggable by domain experts, not just engineers.

**State machines actually enforce transitions.** `InvalidTransition` is raised — not silently ignored — when you try to pay a denied claim or resubmit a voided one. The CI tests verify this. The state machine definitions are data (dicts of frozensets), so adding a new transition is a 1-line change with automatic test coverage from the `CLAIM_TRANSITIONS` dict shape.

**PHI is treated as PHI, not just as strings.** Encryption at the infrastructure layer, excluded from list responses, never logged. The `phi_` column prefix convention means anyone reviewing a migration can see the sensitivity at a glance.

**Tests encode domain rules, not HTTP behaviors.** `test_adjudicator.py` reads like a specification: "when a member with a $500 deductible submits a specialist visit for $250, the deductible consumes the entire billed amount and covered_amount is $0." The test verifies this, not just that the response status is 200.

**Explanations are useful.** Every adjudication result includes a plain-English explanation that names the policy, the limit amounts, and the cost-sharing applied. Not "DENIED: code 4002" — "Your annual benefit limit of $2,000 for SPECIALIST_VISIT has been fully used for benefit year 2026."

**SELECT FOR UPDATE on AnnualUsage.** This is the hardest concurrency bug in the system and the code handles it correctly. Two concurrent adjudications for the same annual limit serialize on the row lock.

## What's rough

**The adjudicator mutates the Policy (deductible_met) in place.** This is a design smell. The adjudicator should return immutable results and the application service should apply mutations. In the current code, if two line items in the same claim share a deductible, the second line item sees the mutated `deductible_met` from the first. This is actually correct behavior, but it's implicit state mutation in what claims to be a pure function. I'd clean this up by passing deductible state explicitly.

**Out-of-pocket maximum is not enforced.** The field exists on Policy and the Terraform infra is there. The adjudicator simply doesn't check it. This is a real coverage gap — members in production would be paying more than their OOP max. I'd implement this as the next story. It requires summing all member cost-sharing across all claims in the benefit year — an additional AnnualUsage-like table for OOP tracking.

**The repository layer has too much logic.** `_map_line_item` uses `LineItem.__new__()` to bypass `__post_init__` validation for DB round-trips. This is a hack. The right solution is a separate `LineItemORM.to_domain()` factory that reconstructs the entity safely without re-running construction-time validation. I ran out of time to do this cleanly.

**Preauth is a check without infrastructure.** The adjudicator correctly denies claims requiring preauth when `preauth_granted=False`. But there's no API or data model for recording preauth grants. Every service with `requires_preauth=True` will be auto-denied. In the demo I set `requires_preauth=False` on all coverage rules. This is the most significant functional gap.

**No Redis cache actually implemented.** The config supports Redis caching and the Redis container runs in Docker Compose. But the repository implementations always hit Postgres — I didn't implement the cache-aside pattern for policy lookups. The infrastructure is wired; the application code is not. This was a time trade-off: caching correctness (especially invalidation around policy updates) requires more thought than the demo needed.

**Frontend is functional but not polished.** It calls the real API, demonstrates all flows, and shows adjudication results with status badges. It's not a product-quality UI. Error states are minimal. Loading states are basic.

**30+ tests but missing a few scenarios:**
- Annual limit at exactly the limit boundary (off-by-one risk)
- Concurrent adjudication test (would require threading in pytest; skipped)
- Negative: submitting a claim with a future effective date
- Retroactive policy cancellation (not modeled at all)

**Git history is good but not perfect.** The TDD intent is visible: domain tests appear before domain implementation. The API integration tests appear in the same commit as the application service, not after — I should have committed the failing API tests first, then the service implementation to make them pass. I noticed this after the fact.

## What I'd do next (priority order)

1. Fix the adjudicator's implicit Policy mutation — return an `AdjudicationDelta` value object instead
2. Implement out-of-pocket max tracking (requires OOPUsage table, similar to AnnualUsage)
3. Build preauth recording API + data model
4. Implement Redis cache for policy lookups with TTL-based invalidation
5. Add audit log for PHI access (which user, when, which fields)
6. Move to async adjudication (SQS/Kafka-based job queue) for production scale
7. Add the missing test cases (boundary conditions, concurrency)
8. KMS envelope encryption for the PHI key

## On the AI collaboration

I used Claude Code throughout. The domain model emerged through conversation — I drafted the CoverageRule structure, Claude Code suggested the `excluded_diagnosis_codes` field (which I'd missed), and I pushed back on using a DSL for rules (it suggested a small rules engine, I argued flat data was sufficient for this scope). The adjudicator decision sequence I wrote myself after thinking through the real-world workflow; Claude Code helped refine the deductible/copay/coverage_percentage ordering.

I caught two mistakes Claude Code made:
1. It initially wrote `adjudication.covered_amount == line_item.billed_amount` for the COVERED vs. PARTIALLY_COVERED distinction, which would fail when per-visit limits cap below billed. I rewrote to compare the calculated covered amount against zero, not billed.
2. It generated `@dataclass_workaround = None` (an invalid Python statement) in adjudicator.py. I caught this immediately and removed it.

The JSONL session logs are in `ai-artifacts/`.
