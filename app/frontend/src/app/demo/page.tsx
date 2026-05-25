"use client";

import { useState } from "react";
import Link from "next/link";
import { membersApi, policiesApi, type Member, type Policy } from "@/lib/api";
import { useAuth, can } from "@/lib/auth";

interface DemoResult {
  member: Member;
  policy: Policy;
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="ml-2 text-xs px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 border border-slate-200 transition-colors"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function IdDisplay({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</span>
      <div className="flex items-center gap-1">
        <code className="text-sm font-mono bg-slate-50 border border-slate-200 rounded px-2.5 py-1.5 text-slate-800 flex-1 break-all">
          {value}
        </code>
        <CopyButton value={value} />
      </div>
    </div>
  );
}

const COVERAGE_RULES = [
  {
    service_type: "SPECIALIST_VISIT",
    coverage_percentage: 80,
    requires_preauth: false,
    annual_limit: 5000,
    copay: 40,
  },
  {
    service_type: "PREVENTIVE",
    coverage_percentage: 100,
    requires_preauth: false,
    annual_limit: 2000,
    copay: 0,
  },
  {
    service_type: "EMERGENCY",
    coverage_percentage: 90,
    requires_preauth: false,
    annual_limit: 50000,
    copay: 150,
  },
  {
    service_type: "MENTAL_HEALTH",
    coverage_percentage: 80,
    requires_preauth: true,
    annual_limit: 3000,
    copay: 30,
  },
  {
    service_type: "LAB_WORK",
    coverage_percentage: 85,
    requires_preauth: false,
    annual_limit: 2500,
    copay: 20,
  },
];

export default function DemoSetupPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DemoResult | null>(null);

  // Only ADMIN and CLAIM_PROCESSOR can create members/policies
  if (user && !can.manageMembersAndPolicies(user.role as "ADMIN" | "CLAIM_PROCESSOR" | "PATIENT" | "PROVIDER")) {
    return (
      <div className="max-w-lg mx-auto mt-16 text-center space-y-4">
        <div className="w-14 h-14 bg-amber-100 rounded-full flex items-center justify-center mx-auto">
          <svg className="w-7 h-7 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-slate-800">Staff Access Required</h2>
        <p className="text-slate-500 text-sm">
          The demo setup page creates members and policies, which requires an{" "}
          <strong>Admin</strong> or <strong>Claim Processor</strong> account.
          You are currently logged in as <strong>{user.role}</strong>.
        </p>
        <Link href="/" className="btn-primary inline-flex">Back to Dashboard</Link>
      </div>
    );
  }

  const runSetup = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const today = new Date();
      const year = today.getFullYear();

      // Step 1: Create member
      const member = await membersApi.create({
        name: "Alex Johnson",
        date_of_birth: `${year - 34}-06-15`,
        member_id: `MBR-DEMO-${Date.now()}`,
        email: `alex.demo+${Date.now()}@example.com`,
      });

      // Step 2: Create policy linked to that member
      const policy = await policiesApi.create({
        member_id: member.id,
        policy_number: `POL-DEMO-${Date.now()}`,
        effective_date: `${year}-01-01`,
        expiration_date: `${year}-12-31`,
        deductible_amount: 500,
        out_of_pocket_max: 6000,
        coverage_rules: COVERAGE_RULES,
      });

      setResult({ member, policy });
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Unknown error — is the backend running?";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="page-title mb-2">Demo Setup</h1>
        <p className="text-slate-500">
          Provision a test member and a comprehensive insurance policy via the live API.
          Use the generated IDs to submit and adjudicate claims end-to-end.
        </p>
      </div>

      {/* Preview card */}
      <div className="card p-6 space-y-5">
        <h2 className="section-title">What will be created</h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div className="rounded-lg bg-blue-50 border border-blue-100 p-4">
            <p className="font-semibold text-blue-900 mb-1">Test Member</p>
            <p className="text-blue-700">Name: Alex Johnson</p>
            <p className="text-blue-700">Age: 34 years old</p>
          </div>
          <div className="rounded-lg bg-violet-50 border border-violet-100 p-4">
            <p className="font-semibold text-violet-900 mb-1">Comprehensive Care Plan</p>
            <p className="text-violet-700">Deductible: $500 · OOP max: $6,000</p>
            <p className="text-violet-700">5 service types covered</p>
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-slate-700 mb-3">Coverage Rules</p>
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Service</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Coverage</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Annual Limit</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Copay</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Preauth</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {COVERAGE_RULES.map((rule) => (
                  <tr key={rule.service_type} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 font-medium text-slate-800">
                      {rule.service_type.replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-600">{rule.coverage_percentage}%</td>
                    <td className="px-4 py-2.5 text-right text-slate-600">
                      ${rule.annual_limit.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-600">${rule.copay}</td>
                    <td className="px-4 py-2.5 text-right">
                      {rule.requires_preauth ? (
                        <span className="text-amber-600 font-medium">Yes</span>
                      ) : (
                        <span className="text-emerald-600 font-medium">No</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Run button */}
      {!result && (
        <div className="flex justify-center">
          <button
            onClick={runSetup}
            disabled={loading}
            className="btn-primary px-8 py-3 text-base disabled:opacity-60"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Creating…
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Run Demo Setup
              </span>
            )}
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-xl bg-red-50 border border-red-200 p-5">
          <p className="font-semibold text-red-800 mb-1">Setup failed</p>
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-6">
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-5 flex items-start gap-4">
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center">
              <svg className="w-5 h-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-emerald-900">Demo setup complete!</h3>
              <p className="text-sm text-emerald-700 mt-1">
                Member and policy created. Copy the IDs below and use them when submitting a claim.
              </p>
            </div>
          </div>

          <div className="card p-6 space-y-5">
            <h2 className="section-title">Generated IDs — use these in the Claim Form</h2>
            <IdDisplay label="Member ID" value={result.member.id} />
            <IdDisplay label="Policy ID" value={result.policy.id} />

            <div className="border-t border-slate-100 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm text-slate-600">
              <div><span className="font-medium">Member:</span> {result.member.name}</div>
              <div><span className="font-medium">Policy #:</span> {result.policy.policy_number}</div>
              <div><span className="font-medium">Effective:</span> {result.policy.effective_date}</div>
              <div><span className="font-medium">Expires:</span> {result.policy.expiration_date}</div>
              <div>
                <span className="font-medium">Deductible:</span>{" "}
                ${parseFloat(String(result.policy.deductible_amount)).toLocaleString()}
              </div>
              <div>
                <span className="font-medium">OOP Max:</span>{" "}
                {result.policy.out_of_pocket_max
                  ? `$${parseFloat(String(result.policy.out_of_pocket_max)).toLocaleString()}`
                  : "None"}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href={`/claims/new?member_id=${result.member.id}&policy_id=${result.policy.id}`}
              className="btn-primary"
            >
              Submit a Claim with These IDs
            </Link>
            <button
              onClick={() => { setResult(null); setError(null); }}
              className="btn-secondary"
            >
              Create Another
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
