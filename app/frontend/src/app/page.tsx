"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { statsApi, claimsApi, type PlatformStats, type Claim } from "@/lib/api";
import { useAuth, can } from "@/lib/auth";
import { StatusBadge } from "@/components/StatusBadge";
import { LoadingSpinner } from "@/components/LoadingSpinner";

function formatCurrency(v: string | number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    typeof v === "string" ? parseFloat(v) : v
  );
}

function formatDate(s: string) {
  try {
    return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch { return s; }
}

function MetricCard({
  label,
  value,
  sub,
  iconBg,
  icon,
}: {
  label: string;
  value: string | number;
  sub?: string;
  iconBg: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="metric-card">
      <div className={`metric-icon ${iconBg}`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="metric-label">{label}</p>
        <p className="metric-value">{value}</p>
        {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function ClaimsDistribution({ stats }: { stats: PlatformStats }) {
  const byStatus = stats.claims.by_status;
  const total = stats.claims.total || 1;

  const bars = [
    { label: "Approved", key: "APPROVED", color: "bg-emerald-500" },
    { label: "Partial", key: "PARTIALLY_APPROVED", color: "bg-amber-500" },
    { label: "Denied", key: "DENIED", color: "bg-red-500" },
    { label: "Pending", key: "SUBMITTED", color: "bg-blue-400" },
    { label: "Disputed", key: "DISPUTED", color: "bg-orange-500" },
    { label: "Paid", key: "PAID", color: "bg-emerald-700" },
  ];

  return (
    <div className="card p-5">
      <h3 className="section-title mb-4">Claims by Status</h3>

      {/* Stacked bar */}
      <div className="flex h-3 rounded-full overflow-hidden mb-5 bg-slate-100">
        {bars.map(({ key, color }) => {
          const count = byStatus[key] ?? 0;
          const pct = (count / total) * 100;
          return pct > 0 ? (
            <div
              key={key}
              className={`${color} transition-all duration-500`}
              style={{ width: `${pct}%` }}
              title={`${key}: ${count}`}
            />
          ) : null;
        })}
      </div>

      <div className="space-y-2.5">
        {bars.map(({ label, key, color }) => {
          const count = byStatus[key] ?? 0;
          const pct = total > 0 ? ((count / total) * 100).toFixed(1) : "0.0";
          return (
            <div key={key} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-sm ${color} flex-shrink-0`} />
                <span className="text-slate-600">{label}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-slate-400 text-xs">{pct}%</span>
                <span className="font-semibold text-slate-800 tabular-nums w-8 text-right">{count}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ApprovalGauge({ rate }: { rate: number }) {
  const color = rate >= 70 ? "text-emerald-600" : rate >= 50 ? "text-amber-600" : "text-red-600";
  const bgColor = rate >= 70 ? "bg-emerald-50" : rate >= 50 ? "bg-amber-50" : "bg-red-50";
  const borderColor = rate >= 70 ? "border-emerald-200" : rate >= 50 ? "border-amber-200" : "border-red-200";

  return (
    <div className={`card p-5 ${bgColor} border ${borderColor}`}>
      <p className="section-title mb-3">Net Approval Rate</p>
      <div className="flex items-end gap-2 mb-3">
        <span className={`text-4xl font-bold tabular-nums ${color}`}>{rate.toFixed(1)}</span>
        <span className={`text-xl font-semibold ${color} mb-1`}>%</span>
      </div>
      <div className="h-2 bg-white/60 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            rate >= 70 ? "bg-emerald-500" : rate >= 50 ? "bg-amber-500" : "bg-red-500"
          }`}
          style={{ width: `${Math.min(rate, 100)}%` }}
        />
      </div>
      <p className="text-xs text-slate-500 mt-2">
        Approved + Partially Approved ÷ Adjudicated
      </p>
    </div>
  );
}

function RecentClaimsTable({ claims }: { claims: Claim[] }) {
  if (claims.length === 0) {
    return (
      <div className="card">
        <div className="p-8 text-center">
          <div className="w-12 h-12 bg-slate-100 rounded-xl flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-sm font-medium text-slate-600 mb-1">No claims yet</p>
          <p className="text-xs text-slate-400 mb-4">Claims submitted through the system will appear here.</p>
          <Link href="/claims/new" className="btn-primary">Submit First Claim</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <h3 className="section-title">Recent Claims</h3>
        <Link href="/claims" className="text-xs font-semibold text-blue-600 hover:text-blue-700">
          View all →
        </Link>
      </div>
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Claim Number</th>
              <th>Provider</th>
              <th>Status</th>
              <th className="text-right">Billed</th>
              <th className="text-right">Covered</th>
              <th>Submitted</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {claims.slice(0, 10).map((claim) => {
              const billed = parseFloat(claim.total_billed);
              const covered = parseFloat(claim.total_covered);
              return (
                <tr key={claim.id}>
                  <td>
                    <code className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-700">
                      {claim.claim_number}
                    </code>
                  </td>
                  <td>
                    <div className="font-medium text-slate-800 text-xs">{claim.provider_name}</div>
                    <div className="text-slate-400 text-xs">{claim.provider_npi}</div>
                  </td>
                  <td>
                    <StatusBadge status={claim.status} size="sm" />
                  </td>
                  <td className="text-right font-semibold tabular-nums">{formatCurrency(billed)}</td>
                  <td className="text-right font-semibold tabular-nums text-emerald-700">
                    {formatCurrency(covered)}
                  </td>
                  <td className="text-slate-500 text-xs whitespace-nowrap">
                    {formatDate(claim.submitted_at)}
                  </td>
                  <td>
                    <Link
                      href={`/claims/${claim.id}`}
                      className="text-xs font-semibold text-blue-600 hover:text-blue-700 whitespace-nowrap"
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const role = user?.role ?? "PATIENT";

  const isStaff = can.viewStats(role);           // ADMIN | CLAIM_PROCESSOR
  const canManageMembers = can.manageMembersAndPolicies(role); // ADMIN | CLAIM_PROCESSOR
  const canSubmit = can.submitClaims(role);      // ADMIN | CLAIM_PROCESSOR | PROVIDER

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: statsApi.get,
    refetchInterval: 30_000,
    enabled: isStaff,   // patients/providers never hit this endpoint
  });

  const { data: claims, isLoading: claimsLoading } = useQuery({
    queryKey: ["claims-recent"],
    queryFn: () => claimsApi.list({ limit: 10 }),
  });

  // ── Quick action cards — scoped by role ──────────────────────────────────
  type QuickAction = {
    href: string;
    title: string;
    desc: string;
    iconBg: string;
    iconColor: string;
    icon: React.ReactNode;
  };

  const allActions: (QuickAction & { show: boolean })[] = [
    {
      show: canManageMembers,
      href: "/members/new",
      title: "Register Member",
      desc: "Enroll a new patient with PHI-compliant intake",
      iconBg: "bg-blue-50",
      iconColor: "text-blue-600",
      icon: (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
      ),
    },
    {
      show: canSubmit,
      href: "/claims/new",
      title: "Submit Claim",
      desc: "File a multi-line insurance claim for adjudication",
      iconBg: "bg-violet-50",
      iconColor: "text-violet-600",
      icon: (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      ),
    },
    {
      show: canManageMembers,
      href: "/members",
      title: "Member Directory",
      desc: "Search and manage the patient registry",
      iconBg: "bg-emerald-50",
      iconColor: "text-emerald-600",
      icon: (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      ),
    },
  ];

  const visibleActions = allActions.filter((a) => a.show);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {isStaff ? "Real-time claims operations overview" : "Your claims at a glance"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {canManageMembers && (
            <Link href="/members/new" className="btn-secondary">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
              Register Member
            </Link>
          )}
          {canSubmit && (
            <Link href="/claims/new" className="btn-primary">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Submit Claim
            </Link>
          )}
        </div>
      </div>

      {/* KPI row — staff only */}
      {isStaff && (
        statsLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="card p-5 h-24">
                <div className="skeleton h-4 w-20 mb-3" />
                <div className="skeleton h-7 w-16" />
              </div>
            ))}
          </div>
        ) : stats ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              label="Total Members"
              value={stats.members.total.toLocaleString()}
              sub="Registered patients"
              iconBg="bg-blue-50"
              icon={
                <svg className="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              }
            />
            <MetricCard
              label="Active Policies"
              value={stats.policies.active.toLocaleString()}
              sub={`${stats.policies.total} total`}
              iconBg="bg-emerald-50"
              icon={
                <svg className="w-5 h-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
              }
            />
            <MetricCard
              label="Claims This Month"
              value={stats.claims.this_month.toLocaleString()}
              sub={`${stats.claims.total} total`}
              iconBg="bg-violet-50"
              icon={
                <svg className="w-5 h-5 text-violet-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              }
            />
            <MetricCard
              label="Approval Rate"
              value={`${stats.approval_rate.toFixed(1)}%`}
              sub="Approved + partial"
              iconBg="bg-amber-50"
              icon={
                <svg className="w-5 h-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              }
            />
          </div>
        ) : null
      )}

      {/* Claims distribution + approval gauge — staff only */}
      {isStaff && stats && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <ClaimsDistribution stats={stats} />
          </div>
          <ApprovalGauge rate={stats.approval_rate} />
        </div>
      )}

      {/* Recent claims table */}
      {claimsLoading ? (
        <div className="card p-6">
          <LoadingSpinner message="Loading recent claims..." />
        </div>
      ) : (
        <RecentClaimsTable claims={claims ?? []} />
      )}

      {/* Quick actions — only rendered when at least one action is visible */}
      {visibleActions.length > 0 && (
        <div className={`grid grid-cols-1 gap-4 ${visibleActions.length > 1 ? "sm:grid-cols-" + visibleActions.length : ""}`}>
          {visibleActions.map((action) => (
            <Link
              key={action.href}
              href={action.href}
              className="card p-5 flex items-start gap-4 hover:shadow-md transition-shadow duration-200 group"
            >
              <div className={`metric-icon ${action.iconBg} flex-shrink-0`}>
                <svg className={`w-5 h-5 ${action.iconColor}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {action.icon}
                </svg>
              </div>
              <div className="flex-1">
                <p className="font-semibold text-slate-800 group-hover:text-blue-600 transition-colors">
                  {action.title}
                </p>
                <p className="text-sm text-slate-500 mt-0.5">{action.desc}</p>
              </div>
              <svg className="w-4 h-4 text-slate-300 group-hover:text-blue-400 transition-colors flex-shrink-0 mt-0.5"
                fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
