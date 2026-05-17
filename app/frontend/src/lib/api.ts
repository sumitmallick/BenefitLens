const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("claimsiq_auth_token");
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Member {
  id: string;
  member_id: string;
  name: string;
}

export interface CreateMemberPayload {
  member_id: string;
  name: string;
  date_of_birth: string;
  email: string;
}

export interface CoverageRule {
  service_type: string;
  coverage_percentage: number;
  annual_limit?: number;
  per_visit_limit?: number;
  copay?: number;
  requires_preauth: boolean;
  network_restriction?: string;
  excluded_diagnosis_codes?: string[];
}

export interface Policy {
  id: string;
  member_id: string;
  policy_number: string;
  effective_date: string;
  expiration_date: string;
  status: string;
  deductible_amount: number;
  deductible_met: number;
  out_of_pocket_max?: number;
  coverage_rules: CoverageRule[];
}

export interface CreatePolicyPayload {
  member_id: string;
  policy_number: string;
  effective_date: string;
  expiration_date: string;
  deductible_amount: number;
  out_of_pocket_max: number;
  coverage_rules: CoverageRule[];
}

export interface ClaimLineItemInput {
  service_type: string;
  diagnosis_code: string;
  procedure_code: string;
  billed_amount: number;
  service_date: string;
  description?: string;
}

export interface CreateClaimPayload {
  member_id: string;
  policy_id: string;
  provider_name: string;
  provider_npi: string;
  line_items: ClaimLineItemInput[];
}

export type ClaimStatus =
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "APPROVED"
  | "PARTIALLY_APPROVED"
  | "DENIED"
  | "DISPUTED"
  | "PAID"
  | "VOIDED";

export type LineItemStatus = "COVERED" | "DENIED" | "PARTIALLY_COVERED" | "PENDING";
export type DisputeStatus = "OPEN" | "UNDER_REVIEW" | "RESOLVED";

// Pydantic v2 serializes Decimal fields as strings in JSON responses.
// All monetary amounts are strings and must be parsed with parseFloat() before arithmetic.
export interface AdjudicationResult {
  covered_amount: string;
  denial_reason?: string | null;
  explanation: string;
  deductible_applied: string;
  copay_applied: string;
  adjudicated_at: string;
}

export interface AdjudicatedLineItem {
  id: string;
  service_type: string;
  service_date: string;
  billed_amount: string;
  procedure_code: string;
  description: string;
  status: string;
  diagnosis_code?: string;  // only in detail view (ClaimDetailResponse)
  adjudication: AdjudicationResult | null;
}

export interface Claim {
  id: string;
  claim_number: string;
  member_id: string;
  policy_id: string;
  submitted_at: string;
  status: string;
  provider_name: string;
  provider_npi: string;
  total_billed: string;
  total_covered: string;
  line_items: AdjudicatedLineItem[];
}

// LineItemExplanation from /explain endpoint — amounts are Decimal serialized as strings
export interface LineItemExplanation {
  line_item_id: string;
  service_type: string;
  service_date: string;
  status: string;
  billed_amount: string;
  covered_amount: string;
  denial_reason?: string | null;
  explanation: string;
}

export interface ClaimExplanation {
  claim_number: string;
  claim_status: string;
  total_billed: string;
  total_covered: string;
  line_item_explanations: LineItemExplanation[];
}

export interface Dispute {
  id: string;
  claim_id: string;
  line_item_id?: string | null;
  reason: string;
  status: string;
  submitted_at: string;
  resolved_at?: string | null;
  resolution_notes?: string | null;
}

export interface CreateDisputePayload {
  reason: string;
  line_item_id?: string;
}

export interface ResolveDisputePayload {
  outcome: string;  // "UPHELD" or "DENIED"
  notes: string;
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
  const token = getToken();
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

export interface PlatformStats {
  members: { total: number };
  policies: { total: number; active: number };
  claims: {
    total: number;
    this_month: number;
    by_status: Record<string, number>;
  };
  approval_rate: number;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: "ADMIN" | "CLAIM_PROCESSOR" | "PATIENT" | "PROVIDER";
  member_id?: string | null;
  provider_npi?: string | null;
  provider_name?: string | null;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  role: string;
  member_id?: string;
  provider_npi?: string;
  provider_name?: string;
}

export const authApi = {
  /** OAuth2 form-encoded login → JWT */
  login: async (email: string, password: string): Promise<TokenResponse> => {
    const form = new URLSearchParams();
    form.append("username", email.trim().toLowerCase());
    form.append("password", password);
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, res.statusText, body);
    }
    return res.json();
  },

  register: (payload: RegisterPayload): Promise<TokenResponse> =>
    request<TokenResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  me: (): Promise<AuthUser> => request<AuthUser>("/api/v1/auth/me"),

  listUsers: (): Promise<AuthUser[]> => request<AuthUser[]>("/api/v1/auth/users"),

  updateRole: (userId: string, role: string): Promise<AuthUser> =>
    request<AuthUser>(`/api/v1/auth/users/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),

  deactivateUser: (userId: string): Promise<AuthUser> =>
    request<AuthUser>(`/api/v1/auth/users/${userId}/deactivate`, {
      method: "PATCH",
    }),
};

// ─── Members ──────────────────────────────────────────────────────────────────

export const membersApi = {
  list: (params?: { limit?: number; offset?: number }): Promise<Member[]> =>
    request<Member[]>(`/api/v1/members?limit=${params?.limit ?? 50}&offset=${params?.offset ?? 0}`),

  create: (payload: CreateMemberPayload): Promise<Member> =>
    request<Member>("/api/v1/members", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getById: (id: string): Promise<Member> =>
    request<Member>(`/api/v1/members/${id}`),
};

// ─── Policies ─────────────────────────────────────────────────────────────────

export const policiesApi = {
  list: (params?: { member_id?: string; limit?: number }): Promise<Policy[]> => {
    const qs = new URLSearchParams();
    if (params?.member_id) qs.set("member_id", params.member_id);
    if (params?.limit) qs.set("limit", String(params.limit));
    return request<Policy[]>(`/api/v1/policies?${qs}`);
  },

  create: (payload: CreatePolicyPayload): Promise<Policy> =>
    request<Policy>("/api/v1/policies", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// ─── Stats ────────────────────────────────────────────────────────────────────

export const statsApi = {
  get: (): Promise<PlatformStats> => request<PlatformStats>("/api/v1/stats"),
};

// ─── Claims ───────────────────────────────────────────────────────────────────

export const claimsApi = {
  list: (params?: { limit?: number; offset?: number }): Promise<Claim[]> =>
    request<Claim[]>(`/api/v1/claims/?limit=${params?.limit ?? 50}&offset=${params?.offset ?? 0}`),

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
