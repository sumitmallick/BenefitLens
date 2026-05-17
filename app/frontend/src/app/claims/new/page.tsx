"use client";

import { useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { claimsApi, type ClaimLineItemInput } from "@/lib/api";
import { ErrorAlert } from "@/components/ErrorAlert";

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

function ClaimFormInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [memberId, setMemberId] = useState(searchParams.get("member_id") ?? "");
  const [policyId, setPolicyId] = useState(searchParams.get("policy_id") ?? "");
  const [providerName, setProviderName] = useState("");
  const [providerNpi, setProviderNpi] = useState("");
  const [lineItems, setLineItems] = useState<LineItemForm[]>([makeEmptyLine(keyCounter++)]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);

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

    // Basic validation
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
        setError(new Error(`Diagnosis code is required for all line items.`));
        return;
      }
      if (li.billed_amount <= 0) {
        setError(new Error(`Billed amount must be greater than 0 for all line items.`));
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
                Get this from the{" "}
                <a href="/demo" className="text-blue-600 hover:underline">
                  Demo Setup page
                </a>
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
                      placeholder="e.g. Z00.00"
                      value={li.diagnosis_code}
                      onChange={(e) => updateLine(li._key, "diagnosis_code", e.target.value)}
                      required
                    />
                  </div>

                  <div>
                    <label className="label">Procedure Code</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. 99213"
                      value={li.procedure_code}
                      onChange={(e) => updateLine(li._key, "procedure_code", e.target.value)}
                    />
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
            <a href="/demo" className="btn-secondary">
              Back to Demo
            </a>
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
