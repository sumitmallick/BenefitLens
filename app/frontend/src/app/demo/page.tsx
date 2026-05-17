"use client";

import { useState } from "react";
import Link from "next/link";
import { membersApi, policiesApi, type Member, type Policy, type ApiError } from "@/lib/api";
import { ErrorAlert } from "@/components/ErrorAlert";
import { LoadingSpinner } from "@/components/LoadingSpinner";

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
      className="ml-2 text-xs px-2 py-0.5 rounded bg-gray-100 hover:bg-gray-200 text-gray-600 border border-gray-200 transition-colors"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function IdDisplay({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
      <div className="flex items-center gap-1">
        <code className="text-sm font-mono bg-gray-50 border border-gray-200 rounded px-2.5 py-1.5 text-gray-800 flex-1 break-all">
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
    requires_prior_auth: false,
    annual_deductible: 500,
    copay: 40,
    max_annual_benefit: 5000,
  },
  {
    service_type: "PREVENTIVE",
    coverage_percentage: 100,
    requires_prior_auth: false,
    annual_deductible: 0,
    copay: 0,
    max_annual_benefit: 2000,
  },
  {
    service_type: "EMERGENCY",
    coverage_percentage: 90,
    requires_prior_auth: false,
    annual_deductible: 500,
    copay: 150,
    max_annual_benefit: 50000,
  },
  {
    service_type: "MENTAL_HEALTH",
    coverage_percentage: 80,
    requires_prior_auth: true,
    annual_deductible: 500,
    copay: 30,
    max_annual_benefit: 3000,
  },
  {
    service_type: "LAB_WORK",
    coverage_percentage: 85,
    requires_prior_auth: false,
    annual_deductible: 200,
    copay: 20,
    max_annual_benefit: 2500,
  },
];

export default function DemoSetupPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<DemoResult | null>(null);

  const runSetup = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      // Step 1: Create member
      const today = new Date();
      const dob = `${today.getFullYear() - 34}-06-15`;
      const member = await membersApi.create({
        name: "Alex Johnson",
        date_of_birth: dob,
        member_id: `MBR-DEMO-${Date.now()}`,
      });

      // Step 2: Create comprehensive policy
      const effectiveDate = `${today.getFullYear()}-01-01`;
      const terminationDate = `${today.getFullYear()}-12-31`;
      const policy = await policiesApi.create({
        member_id: member.id,
        policy_number: `POL-DEMO-${Date.now()}`,
        plan_name: "Comprehensive Care Plan (Demo)",
        effective_date: effectiveDate,
        termination_date: terminationDate,
        coverage_rules: COVERAGE_RULES,
      });

      setResult({ member, policy });
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="page-title mb-2">Demo Setup</h1>
        <p className="text-gray-500">
          Automatically provision a test member and a comprehensive insurance policy
          against the live API. Use the generated IDs to submit and adjudicate claims.
        </p>
      </div>

      {/* Policy preview card */}
      <div className="card p-6 space-y-4">
        <h2 className="section-title">What will be created</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div className="rounded-lg bg-blue-50 border border-blue-100 p-4">
            <p className="font-semibold text-blue-900 mb-1">Test Member</p>
            <p className="text-blue-700">Name: Alex Johnson</p>
            <p className="text-blue-700">DOB: 34 years old</p>
          </div>
          <div className="rounded-lg bg-purple-50 border border-purple-100 p-4">
            <p className="font-semibold text-purple-900 mb-1">Comprehensive Care Plan</p>
            <p className="text-purple-700">Effective this calendar year</p>
            <p className="text-purple-700">5 service types covered</p>
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-gray-700 mb-3">Coverage Rules</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">Service</th>
                  <th className="text-right py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">Coverage</th>
                  <th className="text-right py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">Deductible</th>
                  <th className="text-right py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">Copay</th>
                  <th className="text-right py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">Prior Auth</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {COVERAGE_RULES.map((rule) => (
                  <tr key={rule.service_type}>
                    <td className="py-2 pr-4 font-medium text-gray-900">
                      {rule.service_type.replace(/_/g, " ")}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-700">{rule.coverage_percentage}%</td>
                    <td className="py-2 pr-4 text-right text-gray-700">${rule.annual_deductible}</td>
                    <td className="py-2 pr-4 text-right text-gray-700">${rule.copay}</td>
                    <td className="py-2 text-right">
                      {rule.requires_prior_auth ? (
                        <span className="text-amber-600 font-medium">Yes</span>
                      ) : (
                        <span className="text-green-600 font-medium">No</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Action button */}
      {!result && (
        <div className="flex justify-center">
          <button
            onClick={runSetup}
            disabled={loading}
            className="btn-primary px-8 py-3 text-base"
          >
            {loading ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Creating...
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Run Demo Setup
              </>
            )}
          </button>
        </div>
      )}

      {loading && <LoadingSpinner message="Calling API to create member and policy..." />}

      {error && (
        <ErrorAlert
          error={error}
          title="Setup failed — is the backend running at http://localhost:8000?"
        />
      )}

      {/* Result */}
      {result && (
        <div className="space-y-6">
          {/* Success banner */}
          <div className="rounded-xl bg-green-50 border border-green-200 p-5 flex items-start gap-4">
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
              <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-green-900">Demo setup complete!</h3>
              <p className="text-sm text-green-700 mt-1">
                Member and policy created successfully via the API. Copy the IDs below and use
                them when submitting a claim.
              </p>
            </div>
          </div>

          {/* IDs */}
          <div className="card p-6 space-y-5">
            <h2 className="section-title">Generated IDs — use these in the Claim Form</h2>

            <IdDisplay label="Member ID" value={result.member.id} />
            <IdDisplay label="Policy ID" value={result.policy.id} />

            <div className="border-t border-gray-100 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm text-gray-600">
              <div>
                <span className="font-medium">Member name:</span> {result.member.name}
              </div>
              <div>
                <span className="font-medium">Policy number:</span> {result.policy.policy_number}
              </div>
              <div>
                <span className="font-medium">Plan:</span> {result.policy.plan_name}
              </div>
              <div>
                <span className="font-medium">Effective:</span> {result.policy.effective_date}{" "}
                {result.policy.termination_date ? `– ${result.policy.termination_date}` : ""}
              </div>
            </div>
          </div>

          {/* Actions */}
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
              Create Another Demo
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
