const API_BASE = "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Member {
  id: string;
  name: string;
  date_of_birth: string;
  member_id?: string;
}

export interface CreateMemberPayload {
  name: string;
  date_of_birth: string;
  member_id?: string;
}

export interface CoverageRule {
  service_type: string;
  coverage_percentage: number;
  requires_prior_auth: boolean;
  annual_deductible?: number;
  copay?: number;
  max_annual_benefit?: number;
}

export interface Policy {
  id: string;
  member_id: string;
  policy_number: string;
  plan_name: string;
  effective_date: string;
  termination_date?: string;
  coverage_rules: CoverageRule[];
}

export interface CreatePolicyPayload {
  member_id: string;
  policy_number: string;
  plan_name: string;
  effective_date: string;
  termination_date?: string;
  coverage_rules: CoverageRule[];
}

export interface ClaimLineItemInput {
  service_type: string;
  diagnosis_code: string;
  procedure_code?: string;
  billed_amount: number;
  service_date: string;
  description?: string;
}

export interface CreateClaimPayload {
  member_id: string;
  policy_id: string;
  claim_number?: string;
  submission_date?: string;
  line_items: ClaimLineItemInput[];
}

export type LineItemStatus = "COVERED" | "DENIED" | "PARTIALLY_COVERED" | "PENDING";
export type ClaimStatus = "PENDING" | "APPROVED" | "DENIED" | "PARTIALLY_APPROVED" | "DISPUTED" | "UNDER_REVIEW";
export type DisputeStatus = "OPEN" | "UNDER_REVIEW" | "RESOLVED";
export type DisputeResolution = "UPHELD" | "DENIED";

export interface AdjudicatedLineItem {
  id: string;
  service_type: string;
  diagnosis_code: string;
  procedure_code?: string;
  billed_amount: number;
  covered_amount: number;
  status: LineItemStatus;
  denial_reason?: string;
  explanation?: string;
  service_date: string;
  description?: string;
}

export interface Claim {
  id: string;
  claim_number: string;
  member_id: string;
  policy_id: string;
  submission_date: string;
  status: ClaimStatus;
  total_billed: number;
  total_covered: number;
  line_items: AdjudicatedLineItem[];
  adjudication_notes?: string;
}

export interface LineItemExplanation {
  line_item_id: string;
  service_type: string;
  status: LineItemStatus;
  billed_amount: number;
  covered_amount: number;
  explanation: string;
  policy_rule_applied?: string;
  denial_reason?: string;
}

export interface ClaimExplanation {
  claim_id: string;
  claim_number: string;
  overall_status: ClaimStatus;
  line_item_explanations: LineItemExplanation[];
  summary?: string;
}

export interface Dispute {
  id: string;
  claim_id: string;
  reason: string;
  description?: string;
  status: DisputeStatus;
  resolution?: DisputeResolution;
  resolution_notes?: string;
  created_at: string;
  resolved_at?: string;
}

export interface CreateDisputePayload {
  reason: string;
  description?: string;
}

export interface ResolveDisputePayload {
  resolution: DisputeResolution;
  resolution_notes?: string;
}

// ─── Error Handling ───────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: unknown
  ) {
    super(`API Error ${status}: ${statusText}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new ApiError(res.status, res.statusText, body);
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

// ─── Members ──────────────────────────────────────────────────────────────────

export const membersApi = {
  create: (payload: CreateMemberPayload): Promise<Member> =>
    request<Member>("/api/v1/members", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// ─── Policies ─────────────────────────────────────────────────────────────────

export const policiesApi = {
  create: (payload: CreatePolicyPayload): Promise<Policy> =>
    request<Policy>("/api/v1/policies", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// ─── Claims ───────────────────────────────────────────────────────────────────

export const claimsApi = {
  submit: (payload: CreateClaimPayload): Promise<Claim> =>
    request<Claim>("/api/v1/claims/", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getById: (id: string): Promise<Claim> =>
    request<Claim>(`/api/v1/claims/${id}`),

  explain: (id: string): Promise<ClaimExplanation> =>
    request<ClaimExplanation>(`/api/v1/claims/${id}/explain`),

  listByMember: (memberId: string): Promise<Claim[]> =>
    request<Claim[]>(`/api/v1/claims/member/${memberId}`),
};

// ─── Disputes ─────────────────────────────────────────────────────────────────

export const disputesApi = {
  submit: (claimId: string, payload: CreateDisputePayload): Promise<Dispute> =>
    request<Dispute>(`/api/v1/disputes/claims/${claimId}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  resolve: (disputeId: string, payload: ResolveDisputePayload): Promise<Dispute> =>
    request<Dispute>(`/api/v1/disputes/${disputeId}/resolve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listByClaim: (claimId: string): Promise<Dispute[]> =>
    request<Dispute[]>(`/api/v1/disputes/claims/${claimId}`),
};
