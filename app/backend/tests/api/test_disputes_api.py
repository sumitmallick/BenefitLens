"""
Integration tests for the dispute workflow.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import create_test_member, create_test_policy

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def member(client: AsyncClient) -> dict:
    return await create_test_member(client)


@pytest_asyncio.fixture
async def policy(client: AsyncClient, member: dict) -> dict:
    return await create_test_policy(client, member["id"])


@pytest_asyncio.fixture
async def denied_claim(client: AsyncClient, member: dict, policy: dict) -> dict:
    """Create a claim that will be denied (dental, not covered)."""
    today = date.today()
    resp = await client.post("/api/v1/claims/", json={
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
    assert resp.status_code == 201
    return resp.json()


class TestDisputeWorkflow:
    async def test_member_can_dispute_denied_claim(
        self, client: AsyncClient, denied_claim: dict
    ):
        claim_id = denied_claim["id"]
        resp = await client.post(f"/api/v1/disputes/claims/{claim_id}", json={
            "reason": "My plan booklet says dental exams under code D0120 are covered when medically necessary.",
        })
        assert resp.status_code == 201, resp.text
        dispute = resp.json()
        assert dispute["status"] == "SUBMITTED"
        assert dispute["claim_id"] == claim_id

    async def test_dispute_transitions_claim_to_disputed(
        self, client: AsyncClient, denied_claim: dict
    ):
        claim_id = denied_claim["id"]
        await client.post(f"/api/v1/disputes/claims/{claim_id}", json={
            "reason": "I believe this should be covered per my policy documents.",
        })

        # Claim should now be in DISPUTED state
        resp = await client.get(f"/api/v1/claims/{claim_id}")
        assert resp.json()["status"] == "DISPUTED"

    async def test_dispute_can_be_denied(
        self, client: AsyncClient, denied_claim: dict
    ):
        claim_id = denied_claim["id"]
        dispute_resp = await client.post(f"/api/v1/disputes/claims/{claim_id}", json={
            "reason": "I want to appeal this decision.",
        })
        dispute_id = dispute_resp.json()["id"]

        resolve_resp = await client.post(f"/api/v1/disputes/{dispute_id}/resolve", json={
            "outcome": "DENIED",
            "notes": "Reviewed policy document section 4.2. Dental services excluded from base plan.",
        })
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "DENIED"
        assert resolve_resp.json()["resolution_notes"] is not None

    async def test_dispute_can_be_upheld(
        self, client: AsyncClient, denied_claim: dict
    ):
        claim_id = denied_claim["id"]
        dispute_resp = await client.post(f"/api/v1/disputes/claims/{claim_id}", json={
            "reason": "Member provided documentation showing dental rider is active.",
        })
        dispute_id = dispute_resp.json()["id"]

        resolve_resp = await client.post(f"/api/v1/disputes/{dispute_id}/resolve", json={
            "outcome": "UPHELD",
            "notes": "Dental rider confirmed active. Claim should be reprocessed.",
        })
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "UPHELD"

    async def test_dispute_specific_line_item(
        self, client: AsyncClient, member: dict, policy: dict
    ):
        """Member can dispute a single line item, not the entire claim."""
        today = date.today()
        submit = await client.post("/api/v1/claims/", json={
            "member_id": member["id"],
            "policy_id": policy["id"],
            "provider_name": "Multi-Specialty",
            "provider_npi": "1234567890",
            "line_items": [
                {
                    "service_type": "PREVENTIVE",
                    "service_date": str(today),
                    "billed_amount": "150.00",
                    "diagnosis_code": "Z00.00",
                    "procedure_code": "99395",
                    "description": "Annual checkup",
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
        claim = submit.json()
        claim_id = claim["id"]
        denied_line = next(li for li in claim["line_items"] if li["status"] == "DENIED")

        resp = await client.post(f"/api/v1/disputes/claims/{claim_id}", json={
            "reason": "The dental item should be covered.",
            "line_item_id": denied_line["id"],
        })
        assert resp.status_code == 201
        assert resp.json()["line_item_id"] == denied_line["id"]

    async def test_list_disputes_for_claim(
        self, client: AsyncClient, denied_claim: dict
    ):
        claim_id = denied_claim["id"]
        await client.post(f"/api/v1/disputes/claims/{claim_id}", json={
            "reason": "First dispute attempt.",
        })

        resp = await client.get(f"/api/v1/disputes/claims/{claim_id}")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_cannot_resolve_with_invalid_outcome(
        self, client: AsyncClient, denied_claim: dict
    ):
        claim_id = denied_claim["id"]
        dispute_resp = await client.post(f"/api/v1/disputes/claims/{claim_id}", json={
            "reason": "Testing invalid outcome.",
        })
        dispute_id = dispute_resp.json()["id"]

        resp = await client.post(f"/api/v1/disputes/{dispute_id}/resolve", json={
            "outcome": "MAYBE",
            "notes": "Not sure about this one.",
        })
        assert resp.status_code == 422
