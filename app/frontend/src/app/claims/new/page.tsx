"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { claimsApi, membersApi, policiesApi, type ClaimLineItemInput } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ErrorAlert } from "@/components/ErrorAlert";
import Link from "next/link";

const SERVICE_TYPES = [
  "SPECIALIST_VISIT",
  "PREVENTIVE",
  "EMERGENCY",
  "MENTAL_HEALTH",
  "LAB_WORK",
  "INPATIENT",
  "OUTPATIENT",
  "PHARMACY",
  "PHYSICAL_THERAPY",
  "IMAGING",
];

interface LineItemForm extends ClaimLineItemInput {
  _key: number;
}

function makeEmptyLine(key: number): LineItemForm {
  return {
    _key: key,
    service_type: "SPECIALIST_VISIT",
    diagnosis_code: "",
    procedure_code: "",
    billed_amount: 0,
    service_date: new Date().toISOString().split("T")[0],
    description: "",
  };
}

let keyCounter = 1;

// ─── Filing guide ─────────────────────────────────────────────────────────────

function FilingGuide() {
  const [open, setOpen] = useState(true);

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 text-left"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-blue-900">How to fill this form</p>
            <p className="text-xs text-blue-600 mt-0.5">
              Codes, formats, and what to expect after submitting — click to {open ? "collapse" : "expand"}
            </p>
          </div>
        </div>
        <svg
          className={`w-5 h-5 text-blue-500 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-5 border-t border-blue-200 pt-4">
          {/* Provider section */}
          <div>
            <p className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-2">
              Provider Information
            </p>
            <div className="space-y-2 text-sm text-blue-900">
              <div className="flex gap-2">
                <span className="font-semibold min-w-[110px]">Provider Name</span>
                <span className="text-blue-700">
                  The clinic, hospital, or practitioner who provided the service.
                  Use the full legal name as it appears on your invoice.
                  <span className="ml-1 italic">e.g. City Medical Center, Dr. Jane Smith MD</span>
                </span>
              </div>
              <div className="flex gap-2">
                <span className="font-semibold min-w-[110px]">Provider NPI</span>
                <span className="text-blue-700">
                  The 10-digit National Provider Identifier. Find it on your Explanation of Benefits (EOB),
                  the provider&apos;s website, or ask the front desk.
                  <span className="ml-1 italic">e.g. 1234567890</span>
                </span>
              </div>
            </div>
          </div>

          {/* Diagnosis codes */}
          <div>
            <p className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-2">
              ICD-10 Diagnosis Codes
            </p>
            <p className="text-sm text-blue-700 mb-2">
              ICD-10 codes identify the medical condition being treated. They appear on your
              EOB or the provider&apos;s superbill. Both dot and no-dot formats are accepted.
            </p>
            <div className="rounded-lg bg-white/60 border border-blue-200 overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-blue-100">
                  <tr>
                    <th className="text-left px-3 py-2 text-blue-800 font-semibold">Code</th>
                    <th className="text-left px-3 py-2 text-blue-800 font-semibold">Meaning</th>
                    <th className="text-left px-3 py-2 text-blue-800 font-semibold">Format</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-blue-100">
                  {[
                    ["Z00.00", "Routine general medical exam", "With dot"],
                    ["Z0000",  "Same as above, no dot", "Without dot"],
                    ["Z090",   "Follow-up after surgery", "3 + 1 digit"],
                    ["S321XA", "Pelvic fracture, initial encounter", "7-char trauma"],
                    ["J06.9",  "Acute upper respiratory infection", "With dot"],
                  ].map(([code, meaning, fmt]) => (
                    <tr key={code} className="hover:bg-blue-50">
                      <td className="px-3 py-1.5 font-mono font-semibold text-blue-900">{code}</td>
                      <td className="px-3 py-1.5 text-slate-700">{meaning}</td>
                      <td className="px-3 py-1.5 text-slate-500 italic">{fmt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-blue-600 mt-1.5">
              Format: one letter + two digits + optional suffix (with or without dot).
              Your EOB or provider&apos;s invoice will list the exact code.
            </p>
          </div>

          {/* Procedure codes */}
          <div>
            <p className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-2">
              CPT Procedure Codes
            </p>
            <p className="text-sm text-blue-700 mb-2">
              CPT codes describe the service or procedure performed. 5-digit codes found on your EOB.
              This field is optional — leave blank if you don&apos;t have the code.
            </p>
            <div className="rounded-lg bg-white/60 border border-blue-200 overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-blue-100">
                  <tr>
                    <th className="text-left px-3 py-2 text-blue-800 font-semibold">Code</th>
                    <th className="text-left px-3 py-2 text-blue-800 font-semibold">Procedure</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-blue-100">
                  {[
                    ["99213", "Office/outpatient visit, low complexity"],
                    ["99385", "Preventive visit, age 18–39"],
                    ["80053", "Comprehensive metabolic panel (lab)"],
                    ["71046", "Chest X-ray, 2 views (imaging)"],
                    ["97110", "Therapeutic exercise (physical therapy)"],
                    ["90837", "Psychotherapy, 60 min (mental health)"],
                  ].map(([code, procedure]) => (
                    <tr key={code} className="hover:bg-blue-50">
                      <td className="px-3 py-1.5 font-mono font-semibold text-blue-900">{code}</td>
                      <td className="px-3 py-1.5 text-slate-700">{procedure}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* After submission */}
          <div>
            <p className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-2">
              What Happens After You Submit
            </p>
            <ol className="space-y-1.5 text-sm text-blue-700">
              {[
                "Your claim is adjudicated instantly against your policy coverage rules.",
                "Each service line item gets a decision: Covered, Partially Covered, or Denied.",
                "You'll see the exact covered amount, copay, and deductible applied per line.",
                "If a line item is denied, you'll receive a plain-English explanation.",
                "You can file a dispute on any denied or partially-covered line within 60 days.",
              ].map((step, i) => (
                <li key={i} className="flex gap-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-200 text-blue-800 text-xs font-bold flex items-center justify-center">
                    {i + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </div>

          {/* Disclaimer */}
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-800 leading-relaxed">
            <span className="font-semibold">Disclaimer:</span> This platform processes claims for
            demonstration and internal use. Adjudication results are based on the coverage rules
            configured in your policy and are not a guarantee of payment. Always verify coverage
            with your insurer before incurring medical expenses. Do not enter real Protected Health
            Information (PHI) in a non-production environment.
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Patient insurance summary card (read-only) ───────────────────────────────

function PatientInsuranceSummary({
  memberName,
  policyNumber,
}: {
  memberName: string;
  policyNumber: string;
}) {
  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 px-5 py-4 flex items-center gap-4">
      <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
        <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
          />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-slate-800 truncate">{memberName}</p>
        <p className="text-sm text-slate-500">Policy: {policyNumber}</p>
      </div>
      <Link href="/my-insurance" className="text-xs font-semibold text-blue-600 hover:text-blue-700 whitespace-nowrap">
        View card →
      </Link>
    </div>
  );
}

// ─── Not linked state ─────────────────────────────────────────────────────────

function InsuranceNotLinked() {
  return (
    <div className="max-w-lg mx-auto text-center py-16 space-y-4">
      <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto">
        <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
          />
        </svg>
      </div>
      <h2 className="text-xl font-bold text-slate-800">Insurance Not Linked</h2>
      <p className="text-slate-500 leading-relaxed">
        Your insurance hasn&apos;t been linked yet. Contact your insurer or healthcare
        provider and ask them to link your member record to your ClaimsIQ account.
      </p>
      <Link href="/" className="btn-secondary mt-2">
        Back to Dashboard
      </Link>
    </div>
  );
}

// ─── Main form inner ──────────────────────────────────────────────────────────

function ClaimFormInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();

  const isPatient = user?.role === "PATIENT";
  const patientMemberId = user?.member_id ?? null;

  // For patients: fetch member + policies automatically
  const { data: patientMember, isLoading: patientMemberLoading } = useQuery({
    queryKey: ["member", patientMemberId],
    queryFn: () => membersApi.getById(patientMemberId!),
    enabled: isPatient && !!patientMemberId,
  });

  const { data: patientPolicies, isLoading: patientPoliciesLoading } = useQuery({
    queryKey: ["policies", patientMemberId],
    queryFn: () => policiesApi.list({ member_id: patientMemberId! }),
    enabled: isPatient && !!patientMemberId,
  });

  // Active policy for patient
  const activePolicy =
    patientPolicies?.find((p) => p.status === "ACTIVE") ?? patientPolicies?.[0] ?? null;

  // Form state — seed from URL params for all roles; overridden for patients once data loads
  const [memberId, setMemberId] = useState(searchParams.get("member_id") ?? "");
  const [policyId, setPolicyId] = useState(searchParams.get("policy_id") ?? "");
  const [providerName, setProviderName] = useState("");
  const [providerNpi, setProviderNpi] = useState("");
  const [lineItems, setLineItems] = useState<LineItemForm[]>([makeEmptyLine(keyCounter++)]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // When patient data loads, auto-fill member + policy IDs
  useEffect(() => {
    if (isPatient && patientMemberId && !searchParams.get("member_id")) {
      setMemberId(patientMemberId);
    }
  }, [isPatient, patientMemberId, searchParams]);

  useEffect(() => {
    if (isPatient && activePolicy && !searchParams.get("policy_id")) {
      setPolicyId(activePolicy.id);
    }
  }, [isPatient, activePolicy, searchParams]);

  const addLine = useCallback(() => {
    setLineItems((prev) => [...prev, makeEmptyLine(keyCounter++)]);
  }, []);

  const removeLine = useCallback((key: number) => {
    setLineItems((prev) => prev.filter((l) => l._key !== key));
  }, []);

  const updateLine = useCallback(
    (key: number, field: keyof Omit<LineItemForm, "_key">, value: string | number) => {
      setLineItems((prev) =>
        prev.map((l) => (l._key === key ? { ...l, [field]: value } : l))
      );
    },
    []
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!memberId.trim()) {
      setError(new Error("Member ID is required."));
      return;
    }
    if (!policyId.trim()) {
      setError(new Error("Policy ID is required."));
      return;
    }
    if (!providerName.trim()) {
      setError(new Error("Provider name is required."));
      return;
    }
    if (!/^\d{10}$/.test(providerNpi.trim())) {
      setError(new Error("Provider NPI must be exactly 10 digits."));
      return;
    }
    if (lineItems.length === 0) {
      setError(new Error("At least one line item is required."));
      return;
    }
    for (const li of lineItems) {
      if (!li.diagnosis_code.trim()) {
        setError(new Error("Diagnosis code is required for all line items."));
        return;
      }
      if (li.billed_amount <= 0) {
        setError(new Error("Billed amount must be greater than 0 for all line items."));
        return;
      }
    }

    setSubmitting(true);
    try {
      const payload = {
        member_id: memberId.trim(),
        policy_id: policyId.trim(),
        provider_name: providerName.trim(),
        provider_npi: providerNpi.trim(),
        line_items: lineItems.map(({ _key, ...rest }) => ({
          ...rest,
          procedure_code: rest.procedure_code || "00000",
          description: rest.description || "",
        })),
      };

      const claim = await claimsApi.submit(payload);
      router.push(`/claims/${claim.id}`);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setSubmitting(false);
    }
  };

  const totalBilled = lineItems.reduce((sum, l) => sum + (Number(l.billed_amount) || 0), 0);

  // ── Patient with no member_id linked ──────────────────────────────────────
  if (isPatient && !patientMemberId) {
    return <InsuranceNotLinked />;
  }

  // ── Loading patient data ───────────────────────────────────────────────────
  if (isPatient && (patientMemberLoading || patientPoliciesLoading)) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <div className="flex items-center gap-3 text-slate-500">
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          Loading your insurance details…
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="page-title mb-2">Submit a Claim</h1>
        <p className="text-gray-500">
          Enter member &amp; policy information and add service line items. The claim will be
          adjudicated in real time against the policy coverage rules.
        </p>
      </div>

      <FilingGuide />

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Member & Policy */}
        <div className="card p-6 space-y-5">
          <h2 className="section-title flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            Member &amp; Policy
          </h2>

          {/* Patient: read-only insurance summary */}
          {isPatient ? (
            <div className="space-y-3">
              {patientMember && activePolicy ? (
                <PatientInsuranceSummary
                  memberName={patientMember.name}
                  policyNumber={activePolicy.policy_number}
                />
              ) : (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-700">
                  No active policy found for your account. Contact your insurer or administrator.
                </div>
              )}

              {/* Provider fields still needed even for patients */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                <div>
                  <label className="label" htmlFor="providerName">
                    Provider Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="providerName"
                    type="text"
                    className="input"
                    placeholder="e.g. City Medical Center"
                    value={providerName}
                    onChange={(e) => setProviderName(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="label" htmlFor="providerNpi">
                    Provider NPI <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="providerNpi"
                    type="text"
                    className="input"
                    placeholder="10-digit NPI (e.g. 1234567890)"
                    value={providerNpi}
                    onChange={(e) => setProviderNpi(e.target.value)}
                    maxLength={10}
                    required
                  />
                  <p className="mt-1 text-xs text-gray-400">
                    Found on your Explanation of Benefits (EOB) or provider&apos;s office.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            /* Staff / Provider: show raw UUID inputs */
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="label" htmlFor="memberId">
                  Member ID <span className="text-red-500">*</span>
                </label>
                <input
                  id="memberId"
                  type="text"
                  className="input"
                  placeholder="e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6"
                  value={memberId}
                  onChange={(e) => setMemberId(e.target.value)}
                  required
                />
                <p className="mt-1 text-xs text-gray-400">
                  Find member IDs in the{" "}
                  <Link href="/members" className="text-blue-600 hover:underline">
                    Members directory
                  </Link>
                </p>
              </div>
              <div>
                <label className="label" htmlFor="policyId">
                  Policy ID <span className="text-red-500">*</span>
                </label>
                <input
                  id="policyId"
                  type="text"
                  className="input"
                  placeholder="e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6"
                  value={policyId}
                  onChange={(e) => setPolicyId(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="label" htmlFor="providerName">
                  Provider Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="providerName"
                  type="text"
                  className="input"
                  placeholder="e.g. City Medical Center"
                  value={providerName}
                  onChange={(e) => setProviderName(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="label" htmlFor="providerNpi">
                  Provider NPI <span className="text-red-500">*</span>
                </label>
                <input
                  id="providerNpi"
                  type="text"
                  className="input"
                  placeholder="10-digit NPI (e.g. 1234567890)"
                  value={providerNpi}
                  onChange={(e) => setProviderNpi(e.target.value)}
                  maxLength={10}
                  required
                />
              </div>
            </div>
          )}
        </div>

        {/* Line Items */}
        <div className="card p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="section-title flex items-center gap-2">
              <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              Service Line Items
            </h2>
            <span className="text-sm text-gray-500">
              {lineItems.length} item{lineItems.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="space-y-4">
            {lineItems.map((li, idx) => (
              <div
                key={li._key}
                className="rounded-xl border border-gray-200 p-4 bg-gray-50 space-y-4"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-700">
                    Line Item #{idx + 1}
                  </span>
                  {lineItems.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeLine(li._key)}
                      className="text-xs text-red-500 hover:text-red-700 flex items-center gap-1"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                      Remove
                    </button>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div>
                    <label className="label">
                      Service Type <span className="text-red-500">*</span>
                    </label>
                    <select
                      className="input bg-white"
                      value={li.service_type}
                      onChange={(e) => updateLine(li._key, "service_type", e.target.value)}
                      required
                    >
                      {SERVICE_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t.replace(/_/g, " ")}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="label">
                      Diagnosis Code <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. Z00.00 or Z0000"
                      value={li.diagnosis_code}
                      onChange={(e) => updateLine(li._key, "diagnosis_code", e.target.value.toUpperCase())}
                      required
                    />
                    <p className="mt-1 text-xs text-gray-400">
                      ICD-10 code from your EOB or provider invoice. Dot optional: <span className="font-mono">Z09.0</span> and <span className="font-mono">Z090</span> both work.
                    </p>
                  </div>

                  <div>
                    <label className="label">Procedure Code</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. 99213 (optional)"
                      value={li.procedure_code}
                      onChange={(e) => updateLine(li._key, "procedure_code", e.target.value)}
                    />
                    <p className="mt-1 text-xs text-gray-400">
                      5-digit CPT code from your EOB. Leave blank if unknown.
                    </p>
                  </div>

                  <div>
                    <label className="label">
                      Billed Amount ($) <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="number"
                      className="input"
                      placeholder="0.00"
                      min="0.01"
                      step="0.01"
                      value={li.billed_amount || ""}
                      onChange={(e) =>
                        updateLine(li._key, "billed_amount", parseFloat(e.target.value) || 0)
                      }
                      required
                    />
                  </div>

                  <div>
                    <label className="label">
                      Service Date <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="date"
                      className="input"
                      value={li.service_date}
                      onChange={(e) => updateLine(li._key, "service_date", e.target.value)}
                      required
                    />
                  </div>

                  <div>
                    <label className="label">Description</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="Optional service description"
                      value={li.description}
                      onChange={(e) => updateLine(li._key, "description", e.target.value)}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={addLine}
            className="btn-secondary w-full border-dashed"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Line Item
          </button>
        </div>

        {/* Summary */}
        <div className="card p-5 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500">Total Billed</p>
            <p className="text-2xl font-bold text-gray-900">
              ${totalBilled.toFixed(2)}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">
              {lineItems.length} line item{lineItems.length !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <Link
              href={isPatient ? "/my-claims" : "/"}
              className="btn-secondary"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary px-6"
            >
              {submitting ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Submitting...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Submit Claim
                </>
              )}
            </button>
          </div>
        </div>

        {error && <ErrorAlert error={error} title="Claim submission failed" />}
      </form>
    </div>
  );
}

export default function NewClaimPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-gray-400">Loading form...</div>}>
      <ClaimFormInner />
    </Suspense>
  );
}
