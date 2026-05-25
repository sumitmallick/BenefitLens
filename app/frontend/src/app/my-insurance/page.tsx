"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { membersApi, policiesApi, type Policy, type CoverageRule } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LoadingSpinner } from "@/components/LoadingSpinner";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(s: string) {
  try {
    return new Date(s).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return s;
  }
}

function formatCurrency(v: string | number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    typeof v === "string" ? parseFloat(v) : v
  );
}

function pickActivePolicy(policies: Policy[]): Policy | null {
  if (!policies.length) return null;
  const active = policies.find((p) => p.status === "ACTIVE");
  return active ?? policies[0];
}

// ─── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const colours: Record<string, string> = {
    ACTIVE: "bg-emerald-100 text-emerald-700 border-emerald-200",
    EXPIRED: "bg-red-100 text-red-700 border-red-200",
    CANCELLED: "bg-slate-100 text-slate-500 border-slate-200",
    SUSPENDED: "bg-amber-100 text-amber-700 border-amber-200",
  };
  const cls = colours[status] ?? "bg-slate-100 text-slate-500 border-slate-200";
  return (
    <span className={`inline-flex items-center text-xs font-semibold px-2.5 py-0.5 rounded-full border ${cls}`}>
      {status}
    </span>
  );
}

// ─── Insurance card (dark blue header) ────────────────────────────────────────

function InsuranceCard({
  memberName,
  planMemberId,
  policyNumber,
  effectiveDate,
  expirationDate,
  status,
}: {
  memberName: string;
  planMemberId: string;
  policyNumber: string;
  effectiveDate: string;
  expirationDate: string;
  status: string;
}) {
  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{
        background: "linear-gradient(135deg, #1e3a5f 0%, #1d4ed8 60%, #2563eb 100%)",
        boxShadow: "0 8px 32px rgba(29,78,216,0.35)",
      }}
    >
      {/* Card top */}
      <div className="px-7 pt-6 pb-4 flex items-start justify-between">
        <div>
          <p className="text-blue-200 text-xs font-semibold uppercase tracking-widest mb-1">
            ClaimsIQ Health Plan
          </p>
          <p className="text-white text-2xl font-bold tracking-tight">{memberName}</p>
          <p className="text-blue-200 text-sm mt-0.5">Member ID: {planMemberId}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <StatusBadge status={status} />
          {/* Card chip decorative */}
          <div className="w-10 h-7 rounded-md bg-yellow-300/70 border border-yellow-200/40 mt-1" />
        </div>
      </div>

      {/* Divider */}
      <div className="mx-7 border-t border-blue-400/30" />

      {/* Card bottom row */}
      <div className="px-7 py-4 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3">
        <div>
          <p className="text-blue-300 text-xs uppercase tracking-wider font-semibold">Policy Number</p>
          <p className="text-white font-mono font-semibold text-sm mt-0.5">{policyNumber}</p>
        </div>
        <div>
          <p className="text-blue-300 text-xs uppercase tracking-wider font-semibold">Effective</p>
          <p className="text-white font-semibold text-sm mt-0.5">{formatDate(effectiveDate)}</p>
        </div>
        <div>
          <p className="text-blue-300 text-xs uppercase tracking-wider font-semibold">Expires</p>
          <p className="text-white font-semibold text-sm mt-0.5">{formatDate(expirationDate)}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Deductible progress bar ───────────────────────────────────────────────────

function DeductibleBar({
  met,
  total,
  label,
}: {
  met: number;
  total: number;
  label: string;
}) {
  const pct = total > 0 ? Math.min((met / total) * 100, 100) : 0;
  const color = pct >= 100 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-blue-500";
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <span className="text-sm font-semibold text-slate-800 tabular-nums">
          {formatCurrency(met)} / {formatCurrency(total)}
        </span>
      </div>
      <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-400 mt-1">{pct.toFixed(0)}% met this plan year</p>
    </div>
  );
}

// ─── Coverage rules table ──────────────────────────────────────────────────────

function CoverageTable({ rules }: { rules: CoverageRule[] }) {
  if (!rules.length) {
    return <p className="text-sm text-slate-400 italic">No coverage rules on file.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Service Type</th>
            <th className="text-right">Coverage %</th>
            <th className="text-right">Copay</th>
            <th className="text-right">Annual Limit</th>
            <th className="text-center">Preauth Req.</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r, i) => (
            <tr key={i}>
              <td>
                <span className="font-medium text-slate-800">
                  {r.service_type.replace(/_/g, " ")}
                </span>
                {r.network_restriction && (
                  <span className="ml-2 text-xs text-slate-400">({r.network_restriction})</span>
                )}
              </td>
              <td className="text-right font-semibold text-emerald-700">
                {r.coverage_percentage}%
              </td>
              <td className="text-right tabular-nums">
                {r.copay != null ? formatCurrency(r.copay) : <span className="text-slate-400">—</span>}
              </td>
              <td className="text-right tabular-nums">
                {r.annual_limit != null
                  ? formatCurrency(r.annual_limit)
                  : <span className="text-slate-400">—</span>}
              </td>
              <td className="text-center">
                {r.requires_preauth ? (
                  <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">
                    Yes
                  </span>
                ) : (
                  <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-400">
                    No
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Sample coverage for the preview ─────────────────────────────────────────
// Mirrors a realistic Silver-tier plan so the patient sees exactly what the
// live portal looks like once their insurer activates their record.

const SAMPLE_COVERAGE: CoverageRule[] = [
  { service_type: "PREVENTIVE",        coverage_percentage: 100, copay: 0,   annual_limit: 2000,  requires_preauth: false },
  { service_type: "SPECIALIST_VISIT",  coverage_percentage: 80,  copay: 50,  annual_limit: 5000,  requires_preauth: false },
  { service_type: "EMERGENCY",         coverage_percentage: 80,  copay: 250, annual_limit: 50000, requires_preauth: false },
  { service_type: "MENTAL_HEALTH",     coverage_percentage: 80,  copay: 30,  annual_limit: 3000,  requires_preauth: true  },
  { service_type: "LAB_WORK",          coverage_percentage: 85,  copay: 20,  annual_limit: 2500,  requires_preauth: false },
  { service_type: "PHYSICAL_THERAPY",  coverage_percentage: 70,  copay: 40,  annual_limit: 2000,  requires_preauth: true  },
  { service_type: "IMAGING",           coverage_percentage: 80,  copay: 75,  annual_limit: 5000,  requires_preauth: true  },
];

// ─── Insurance pending activation (replaces blank "not linked" state) ─────────

function InsurancePendingActivation({ userName, userEmail }: { userName: string; userEmail: string }) {
  const planYear = new Date().getFullYear();

  return (
    <div className="max-w-3xl mx-auto space-y-6">

      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-title mb-1">My Insurance</h1>
          <p className="text-sm text-slate-500">Your digital insurance card and coverage details</p>
        </div>
      </div>

      {/* Activation banner */}
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 flex items-start gap-3">
        <svg className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
        </svg>
        <div>
          <p className="text-sm font-semibold text-amber-800">Insurance Pending Activation</p>
          <p className="text-sm text-amber-700 mt-0.5">
            Your member record hasn&apos;t been linked yet. The preview below shows exactly
            what your portal will look like once your insurer activates your account.
          </p>
        </div>
      </div>

      {/* Preview card — same component, pending state */}
      <div className="relative">
        {/* Frosted-glass "pending" overlay */}
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl"
          style={{ backdropFilter: "blur(1px)", background: "rgba(15,23,42,0.18)" }}>
          <div className="flex items-center gap-2 bg-white/90 border border-slate-200 rounded-full px-4 py-2 shadow-lg">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-sm font-semibold text-slate-700">Pending Activation</span>
          </div>
        </div>

        <div
          className="rounded-2xl overflow-hidden"
          style={{
            background: "linear-gradient(135deg, #1e3a5f 0%, #1d4ed8 60%, #2563eb 100%)",
            boxShadow: "0 8px 32px rgba(29,78,216,0.25)",
          }}
        >
          <div className="px-7 pt-6 pb-4 flex items-start justify-between">
            <div>
              <p className="text-blue-200 text-xs font-semibold uppercase tracking-widest mb-1">
                ClaimsIQ Health Plan
              </p>
              <p className="text-white text-2xl font-bold tracking-tight">{userName}</p>
              <p className="text-blue-200 text-sm mt-0.5">Member ID: MBR-PENDING</p>
            </div>
            <div className="flex flex-col items-end gap-1.5">
              <span className="inline-flex items-center text-xs font-semibold px-2.5 py-0.5 rounded-full border bg-amber-100 text-amber-700 border-amber-200">
                PENDING
              </span>
              <div className="w-10 h-7 rounded-md bg-yellow-300/40 border border-yellow-200/30 mt-1" />
            </div>
          </div>
          <div className="mx-7 border-t border-blue-400/30" />
          <div className="px-7 py-4 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3">
            <div>
              <p className="text-blue-300 text-xs uppercase tracking-wider font-semibold">Policy Number</p>
              <p className="text-white/50 font-mono font-semibold text-sm mt-0.5">Pending Assignment</p>
            </div>
            <div>
              <p className="text-blue-300 text-xs uppercase tracking-wider font-semibold">Effective</p>
              <p className="text-white/50 font-semibold text-sm mt-0.5">Jan 1, {planYear}</p>
            </div>
            <div>
              <p className="text-blue-300 text-xs uppercase tracking-wider font-semibold">Expires</p>
              <p className="text-white/50 font-semibold text-sm mt-0.5">Dec 31, {planYear}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Sample deductible tracker */}
      <div className="card p-6 space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="section-title">Deductible &amp; Out-of-Pocket</h2>
          <span className="text-xs font-medium text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
            Sample — Plan Year {planYear}
          </span>
        </div>

        {/* Deductible */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-sm font-medium text-slate-700">Annual Deductible</span>
            <span className="text-sm font-semibold text-slate-800 tabular-nums">$0 / $1,500</span>
          </div>
          <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full rounded-full bg-blue-500/30 w-0" />
          </div>
          <p className="text-xs text-slate-400 mt-1">0% met — resets Jan 1 each year</p>
        </div>

        {/* OOP */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-sm font-medium text-slate-700">Out-of-Pocket Maximum</span>
            <span className="text-sm font-semibold text-slate-800 tabular-nums">$0 / $6,000</span>
          </div>
          <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full rounded-full bg-emerald-500/30 w-0" />
          </div>
          <p className="text-xs text-slate-400 mt-1">Once reached, plan covers 100% of eligible costs</p>
        </div>
      </div>

      {/* Sample coverage table */}
      <div className="card p-6 space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="section-title">What&apos;s Covered</h2>
          <span className="text-xs font-medium text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
            Sample Plan Preview
          </span>
        </div>
        <CoverageTable rules={SAMPLE_COVERAGE} />
        <p className="text-xs text-slate-400">
          * Actual coverage rules will be set by your insurer when your account is activated.
          Costs shown after deductible unless marked otherwise.
        </p>
      </div>

      {/* Activation steps */}
      <div className="card p-6 space-y-5">
        <h2 className="section-title">How to Activate Your Insurance Portal</h2>
        <ol className="space-y-4">
          {[
            {
              step: "1",
              title: "Contact your insurer or healthcare provider",
              desc: "Call the member services number on the back of your physical insurance card, or visit your provider's patient enrollment desk.",
            },
            {
              step: "2",
              title: "Provide your ClaimsIQ account email",
              desc: (
                <span>
                  Give them your registered email:{" "}
                  <code className="text-xs bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5 text-slate-700 font-mono">
                    {userEmail}
                  </code>
                </span>
              ),
            },
            {
              step: "3",
              title: "They link your member record",
              desc: "Your insurer or a ClaimsIQ administrator will enroll your member record and link it to this account — no action needed from you.",
            },
            {
              step: "4",
              title: "Your card activates",
              desc: "You'll see your real insurance card, live deductible tracker, and coverage details here — typically within 24–48 business hours.",
            },
          ].map(({ step, title, desc }) => (
            <li key={step} className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold flex items-center justify-center">
                {step}
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800">{title}</p>
                <p className="text-sm text-slate-500 mt-0.5">{desc}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function MyInsurancePage() {
  const { user, isLoading: authLoading } = useAuth();

  const memberId = user?.member_id ?? null;

  const { data: member, isLoading: memberLoading } = useQuery({
    queryKey: ["member", memberId],
    queryFn: () => membersApi.getById(memberId!),
    enabled: !!memberId,
  });

  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: ["policies", memberId],
    queryFn: () => policiesApi.list({ member_id: memberId! }),
    enabled: !!memberId,
  });

  if (authLoading || (memberId && (memberLoading || policiesLoading))) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <LoadingSpinner message="Loading your insurance information..." />
      </div>
    );
  }

  if (!memberId) {
    return (
      <InsurancePendingActivation
        userName={user?.full_name ?? "Member"}
        userEmail={user?.email ?? ""}
      />
    );
  }

  const policy = pickActivePolicy(policies ?? []);

  const deductibleMet = parseFloat(String(policy?.deductible_met ?? "0"));
  const deductibleAmount = parseFloat(String(policy?.deductible_amount ?? "0"));
  const oopMax = policy?.out_of_pocket_max != null
    ? parseFloat(String(policy.out_of_pocket_max))
    : null;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-title mb-1">My Insurance</h1>
          <p className="text-sm text-slate-500">Your digital insurance card and coverage details</p>
        </div>
        {policy && (
          <Link
            href={`/claims/new?member_id=${memberId}&policy_id=${policy.id}`}
            className="btn-primary"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Submit a Claim
          </Link>
        )}
      </div>

      {/* No policies yet */}
      {!policy && (
        <div className="card p-8 text-center space-y-2">
          <p className="font-semibold text-slate-700">No active policy found</p>
          <p className="text-sm text-slate-400">
            Your member record is linked, but no policy has been issued yet.
            Contact your insurer or administrator.
          </p>
        </div>
      )}

      {/* Digital insurance card */}
      {policy && member && (
        <>
          <InsuranceCard
            memberName={member.name}
            planMemberId={member.member_id}
            policyNumber={policy.policy_number}
            effectiveDate={policy.effective_date}
            expirationDate={policy.expiration_date}
            status={policy.status}
          />

          {/* Deductibles & OOP */}
          <div className="card p-6 space-y-5">
            <h2 className="section-title">Deductible &amp; Out-of-Pocket</h2>
            <DeductibleBar
              met={deductibleMet}
              total={deductibleAmount}
              label="Annual Deductible"
            />
            {oopMax != null && oopMax > 0 && (
              <DeductibleBar
                met={deductibleMet}
                total={oopMax}
                label="Out-of-Pocket Maximum"
              />
            )}
          </div>

          {/* Coverage rules */}
          <div className="card p-6 space-y-5">
            <h2 className="section-title">Coverage Rules</h2>
            <CoverageTable rules={policy.coverage_rules} />
          </div>

          {/* Submit claim CTA */}
          <div className="card p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <p className="font-semibold text-slate-800">Ready to submit a claim?</p>
              <p className="text-sm text-slate-500 mt-0.5">
                Your member and policy details will be pre-filled automatically.
              </p>
            </div>
            <Link
              href={`/claims/new?member_id=${memberId}&policy_id=${policy.id}`}
              className="btn-primary whitespace-nowrap"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 4v16m8-8H4" />
              </svg>
              Submit a Claim
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
