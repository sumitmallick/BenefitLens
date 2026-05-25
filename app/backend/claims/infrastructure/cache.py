"""
Redis cache-aside for ClaimsIQ hot paths.

Cache strategy:
  - Policy + coverage rules: TTL 5 min (policies change infrequently; adjudication
    reads them on every claim submission — the hottest read path in the system).
  - Cache key: claimsiq:policy:{policy_id}  — keyed by policy UUID, not by member.
    Rationale: after the membership_policies refactor a single member may be enrolled
    in multiple policies, and a single policy may cover multiple members.  Keying by
    policy_id is the natural, stable identifier that adjudication already uses.
  - On policy save/update: invalidate by policy_id.

Serialization: pure JSON with custom handlers for UUID, date, Decimal, Money.
Avoids pickle for security (cache-poisoning resistance).

PHI safety: no PHI (member names, diagnosis codes) is stored in the cache.
Policy objects contain only financial/structural data (amounts, dates, rules).

Usage:
    cache = PolicyCache(redis_client)
    policy = await cache.get(policy_id)
    if policy is None:
        policy = await repo.get(policy_id)
        await cache.set(policy_id, policy)
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

import structlog

from claims.domain.entities import CoverageRule, Policy
from claims.domain.value_objects import Money, NetworkType, PolicyStatus, ServiceType

logger = structlog.get_logger(__name__)

_POLICY_TTL = 300  # 5 minutes


# ── Serialisation ─────────────────────────────────────────────────────────

def _policy_to_json(policy: Policy) -> str:
    data = {
        "id": str(policy.id),
        "holder_member_id": str(policy.holder_member_id),
        "policy_number": policy.policy_number,
        "effective_date": policy.effective_date.isoformat(),
        "expiration_date": policy.expiration_date.isoformat(),
        "status": policy.status.value,
        "deductible_amount": str(policy.deductible_amount.amount),
        "deductible_met": str(policy.deductible_met.amount),
        "out_of_pocket_max": str(policy.out_of_pocket_max.amount) if policy.out_of_pocket_max else None,
        "oop_used": str(policy.oop_used.amount),
        "coverage_rules": [
            {
                "id": str(r.id),
                "policy_id": str(r.policy_id),
                "service_type": r.service_type.value,
                "coverage_percentage": str(r.coverage_percentage),
                "annual_limit": str(r.annual_limit.amount) if r.annual_limit else None,
                "per_visit_limit": str(r.per_visit_limit.amount) if r.per_visit_limit else None,
                "copay": str(r.copay.amount) if r.copay else None,
                "requires_preauth": r.requires_preauth,
                "network_restriction": r.network_restriction.value,
                "excluded_diagnosis_codes": r.excluded_diagnosis_codes,
            }
            for r in policy.coverage_rules
        ],
    }
    return json.dumps(data)


def _policy_from_json(raw: str) -> Policy:
    d = json.loads(raw)
    rules = [
        CoverageRule(
            id=uuid.UUID(r["id"]),
            policy_id=uuid.UUID(r["policy_id"]),
            service_type=ServiceType(r["service_type"]),
            coverage_percentage=Decimal(r["coverage_percentage"]),
            annual_limit=Money.of(r["annual_limit"]) if r["annual_limit"] else None,
            per_visit_limit=Money.of(r["per_visit_limit"]) if r["per_visit_limit"] else None,
            copay=Money.of(r["copay"]) if r["copay"] else None,
            requires_preauth=r["requires_preauth"],
            network_restriction=NetworkType(r["network_restriction"]),
            excluded_diagnosis_codes=r["excluded_diagnosis_codes"],
        )
        for r in d["coverage_rules"]
    ]
    return Policy(
        id=uuid.UUID(d["id"]),
        holder_member_id=uuid.UUID(d["holder_member_id"]),
        policy_number=d["policy_number"],
        effective_date=date.fromisoformat(d["effective_date"]),
        expiration_date=date.fromisoformat(d["expiration_date"]),
        status=PolicyStatus(d["status"]),
        deductible_amount=Money.of(d["deductible_amount"]),
        deductible_met=Money.of(d["deductible_met"]),
        out_of_pocket_max=Money.of(d["out_of_pocket_max"]) if d["out_of_pocket_max"] else None,
        oop_used=Money.of(d["oop_used"]),
        coverage_rules=rules,
    )


# ── Cache class ───────────────────────────────────────────────────────────

class PolicyCache:
    """
    Cache-aside wrapper for PolicyRepository.

    Keyed by policy_id (not member_id) because a single member may now be
    enrolled in multiple policies, and a single policy may cover multiple
    members.  The adjudicator already knows the policy_id before it fetches
    the policy, making this the natural cache key.

    Injected into the application service alongside the PolicyRepository.
    The repository remains unmodified; the service checks the cache first.
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def _key(self, policy_id: uuid.UUID) -> str:
        return f"claimsiq:policy:{policy_id}"

    async def get(self, policy_id: uuid.UUID) -> Optional[Policy]:
        """Return a cached policy by ID, or None on miss."""
        try:
            raw = await self._redis.get(self._key(policy_id))
            if raw:
                policy = _policy_from_json(raw)
                logger.debug("policy_cache_hit", policy_id=str(policy_id))
                return policy
        except Exception as exc:
            # Never let a cache failure block claim adjudication
            logger.warning("policy_cache_read_error", error=str(exc))
        logger.debug("policy_cache_miss", policy_id=str(policy_id))
        return None

    async def set(self, policy_id: uuid.UUID, policy: Policy) -> None:
        """Cache a policy by ID; silently skip on Redis errors."""
        try:
            await self._redis.setex(
                self._key(policy_id),
                _POLICY_TTL,
                _policy_to_json(policy),
            )
        except Exception as exc:
            logger.warning("policy_cache_write_error", error=str(exc))

    async def invalidate(self, policy_id: uuid.UUID) -> None:
        """Invalidate a cached policy (call on policy update/cancellation)."""
        try:
            await self._redis.delete(self._key(policy_id))
            logger.debug("policy_cache_invalidated", policy_id=str(policy_id))
        except Exception as exc:
            logger.warning("policy_cache_invalidate_error", error=str(exc))
