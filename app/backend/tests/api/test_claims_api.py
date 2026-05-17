"""
API-level integration tests for the claims lifecycle.

These tests hit real FastAPI routes against a real test DB.
They verify end-to-end behavior:
  - Claim submission triggers adjudication
  - Adjudication results are persisted and queryable
  - State transitions are enforced
  - Explanations are present for every line item
  - PHI (diagnosis code) appears in detail view, not list view
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import create_test_member, create_test_policy


pytestmark = pytest.mark.asyncio


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def member(client: AsyncClient) -> dict:
    return await create_test_member(client)


@pytest_asyncio.fixture
async def policy(client: AsyncClient, member: dict) -> dict:
    return await create_test_policy(client, member["id"])


# ── Claim submission ──────────────────────────────────────────────────────

class TestClaimSubmission:
    async def test_submit_claim_returns_201_with_adjudication(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        today = date.today()
        resp = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Metro Health Clinic",
            "provider_npi": "1234567890",
            "line_items": [
                {
                    "service_type": "PREVENTIVE",
                    "service_date": str(today),
                    "billed_amount": "150.00",
                    "diagnosis_code": "Z00.00",
                    "procedure_code": "99395",
                    "description": "Annual wellness exam",
                }
            ],
        })

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["claim_number"].startswith("CLM-")
        assert data["status"] in ("APPROVED", "PARTIALLY_APPROVED", "DENIED", "UNDER_REVIEW")
        assert len(data["line_items"]) == 1

    async def test_preventive_claim_is_fully_covered(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        """Preventive services bypass deductible and have 100% coverage."""
        today = date.today()
        resp = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Metro Health Clinic",
            "provider_npi": "1234567890",
            "line_items": [
                {
                    "service_type": "PREVENTIVE",
                    "service_date": str(today),
                    "billed_amount": "200.00",
                    "diagnosis_code": "Z00.00",
                    "procedure_code": "99395",
                    "description": "Annual physical",
                }
            ],
        })

        assert resp.status_code == 201, resp.text
        data = resp.json()
        line = data["line_items"][0]
        assert line["status"] == "COVERED"
        assert float(line["adjudication"]["covered_amount"]) == 200.00
        assert float(line["adjudication"]["deductible_applied"]) == 0.00
        assert data["status"] == "APPROVED"

    async def test_multi_line_claim_partial_approval(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        """
        5 line items: 1 preventive (covered), 1 specialist (partially — deductible),
        1 dental (not covered), 1 emergency (covered), 1 preventive (covered).
        """
        today = date.today()
        resp = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Multi-Specialty Group",
            "provider_npi": "9876543210",
            "line_items": [
                {
                    "service_type": "PREVENTIVE",
                    "service_date": str(today),
                    "billed_amount": "150.00",
                    "diagnosis_code": "Z00.00",
                    "procedure_code": "99395",
                    "description": "Preventive checkup",
                },
                {
                    "service_type": "SPECIALIST_VISIT",
                    "service_date": str(today),
                    "billed_amount": "300.00",
                    "diagnosis_code": "M54.5",
                    "procedure_code": "99213",
                    "description": "Specialist consult",
                },
                {
                    "service_type": "DENTAL",   # not covered under this policy
                    "service_date": str(today),
                    "billed_amount": "200.00",
                    "diagnosis_code": "K02.9",
                    "procedure_code": "D0120",
                    "description": "Dental exam",
                },
            ],
        })

        assert resp.status_code == 201, resp.text
        data = resp.json()
        statuses = {li["service_type"]: li["status"] for li in data["line_items"]}

        assert statuses["PREVENTIVE"] == "COVERED"
        assert statuses["DENTAL"] == "DENIED"
        # Specialist: may be denied (deductible) or partially covered
        assert data["status"] == "PARTIALLY_APPROVED"

    async def test_submit_claim_for_unknown_member_returns_404(
        self, client: AsyncClient, policy: dict
    ):
        resp = await client.post("/api/v1/claims/", json={
            "member_id": str(uuid.uuid4()),
            "policy_id": policy["id"],
            "provider_name": "Clinic",
            "provider_npi": "1234567890",
            "line_items": [{
                "service_type": "PREVENTIVE",
                "service_date": str(date.today()),
                "billed_amount": "100.00",
                "diagnosis_code": "Z00.00",
                "procedure_code": "99395",
                "description": "test",
            }],
        })
        assert resp.status_code == 404

    async def test_submit_claim_with_invalid_npi_returns_422(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        resp = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Clinic",
            "provider_npi": "INVALID",   # not 10 digits
            "line_items": [{
                "service_type": "PREVENTIVE",
                "service_date": str(date.today()),
                "billed_amount": "100.00",
                "diagnosis_code": "Z00.00",
                "procedure_code": "99395",
                "description": "test",
            }],
        })
        assert resp.status_code == 422

    async def test_submit_claim_with_zero_billed_amount_returns_422(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        resp = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Clinic",
            "provider_npi": "1234567890",
            "line_items": [{
                "service_type": "PREVENTIVE",
                "service_date": str(date.today()),
                "billed_amount": "0.00",
                "diagnosis_code": "Z00.00",
                "procedure_code": "99395",
                "description": "test",
            }],
        })
        assert resp.status_code == 422


# ── Claim retrieval ───────────────────────────────────────────────────────

class TestClaimRetrieval:
    async def test_get_claim_returns_detail_with_diagnosis_code(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        today = date.today()
        submit = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Metro Health",
            "provider_npi": "1234567890",
            "line_items": [{
                "service_type": "PREVENTIVE",
                "service_date": str(today),
                "billed_amount": "100.00",
                "diagnosis_code": "Z00.00",
                "procedure_code": "99395",
                "description": "Physical",
            }],
        })
        claim_id = submit.json()["id"]

        resp = await client.get(f"/api/v1/claims/{claim_id}")
        assert resp.status_code == 200
        data = resp.json()
        # Detail endpoint includes diagnosis code (PHI)
        assert "diagnosis_code" in data["line_items"][0]
        assert data["line_items"][0]["diagnosis_code"] == "Z00.00"

    async def test_list_member_claims_excludes_diagnosis_code(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        today = date.today()
        await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Metro Health",
            "provider_npi": "1234567890",
            "line_items": [{
                "service_type": "PREVENTIVE",
                "service_date": str(today),
                "billed_amount": "100.00",
                "diagnosis_code": "Z00.00",
                "procedure_code": "99395",
                "description": "Physical",
            }],
        })

        resp = await client.get(f"/api/v1/claims/member/{member['id']}")
        assert resp.status_code == 200
        claims = resp.json()
        assert len(claims) >= 1
        # List endpoint must NOT expose diagnosis codes
        for claim in claims:
            for li in claim["line_items"]:
                assert "diagnosis_code" not in li, "Diagnosis code leaked in list response!"

    async def test_get_nonexistent_claim_returns_404(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/claims/{uuid.uuid4()}")
        assert resp.status_code == 404


# ── Explanation endpoint ──────────────────────────────────────────────────

class TestExplanationEndpoint:
    async def test_explain_returns_explanation_for_every_line_item(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        today = date.today()
        submit = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Metro Health",
            "provider_npi": "1234567890",
            "line_items": [
                {
                    "service_type": "PREVENTIVE",
                    "service_date": str(today),
                    "billed_amount": "150.00",
                    "diagnosis_code": "Z00.00",
                    "procedure_code": "99395",
                    "description": "Annual exam",
                },
                {
                    "service_type": "DENTAL",
                    "service_date": str(today),
                    "billed_amount": "200.00",
                    "diagnosis_code": "K02.9",
                    "procedure_code": "D0120",
                    "description": "Dental exam",
                },
            ],
        })
        claim_id = submit.json()["id"]

        resp = await client.get(f"/api/v1/claims/{claim_id}/explain")
        assert resp.status_code == 200
        data = resp.json()
        assert "line_item_explanations" in data
        assert len(data["line_item_explanations"]) == 2

        for item in data["line_item_explanations"]:
            assert "explanation" in item
            assert len(item["explanation"]) > 0, "Explanation must not be empty"
            assert "status" in item
            assert "covered_amount" in item

    async def test_denied_explanation_contains_reason(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        """A DENTAL claim (not covered) must have a meaningful explanation."""
        today = date.today()
        submit = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Dental Clinic",
            "provider_npi": "5556667778",
            "line_items": [{
                "service_type": "DENTAL",
                "service_date": str(today),
                "billed_amount": "300.00",
                "diagnosis_code": "K02.9",
                "procedure_code": "D0120",
                "description": "Cavity filling",
            }],
        })
        claim_id = submit.json()["id"]

        resp = await client.get(f"/api/v1/claims/{claim_id}/explain")
        data = resp.json()
        item = data["line_item_explanations"][0]

        assert item["status"] == "DENIED"
        assert item["denial_reason"] is not None
        assert "not covered" in item["explanation"].lower() or "dental" in item["explanation"].lower()


# ── State machine enforcement ─────────────────────────────────────────────

class TestStateMachineEnforcement:
    async def test_cannot_pay_a_denied_claim_directly(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        """
        A fully denied claim must go through DISPUTED → DISPUTE_RESOLVED
        before PAID is valid. Attempting to pay a DENIED claim directly
        must return 409 Conflict.
        """
        today = date.today()
        submit = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Dental Clinic",
            "provider_npi": "5556667778",
            "line_items": [{
                "service_type": "DENTAL",
                "service_date": str(today),
                "billed_amount": "300.00",
                "diagnosis_code": "K02.9",
                "procedure_code": "D0120",
                "description": "Dental",
            }],
        })
        assert submit.json()["status"] == "DENIED"
        claim_id = submit.json()["id"]

        pay_resp = await client.post(f"/api/v1/claims/{claim_id}/pay")
        assert pay_resp.status_code == 409
