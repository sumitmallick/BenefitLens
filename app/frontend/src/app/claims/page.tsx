"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { claimsApi, membersApi, type Claim } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ErrorAlert } from "@/components/ErrorAlert";

function formatCurrency(v: string | number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    typeof v === "string" ? parseFloat(v) : v
  );
}

function formatDate(s: string) {
  return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

const STATUS_FILTERS = ["All", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "PARTIALLY_APPROVED", "DENIED", "DISPUTED", "PAID"];

function ClaimsListInner() {
  const searchParams = useSearchParams();
  const memberIdParam = searchParams.get("member_id");

  const [statusFilter, setStatusFilter] = useState("All");
  const [search, setSearch] = useState("");

  const { data: claims, isLoading, error } = useQuery({
    queryKey: ["claims-all", memberIdParam],
    queryFn: () =>
      memberIdParam
        ? claimsApi.listByMember(memberIdParam)
        : claimsApi.list({ limit: 100 }),
  });

  const { data: member } = useQuery({
    queryKey: ["member", memberIdParam],
    queryFn: () => membersApi.getById(memberIdParam!),
    enabled: !!memberIdParam,
  });

  const filtered = claims?.filter((c) => {
    if (statusFilter !== "All" && c.status !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!c.claim_number.toLowerCase().includes(q) && !c.provider_name.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            {member ? `${member.name}'s Claims` : "Claims Queue"}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {claims ? `${claims.length} total claims` : "All submitted claims"}
            {member && (
              <Link href="/members" className="ml-2 text-blue-600 hover:text-blue-700">
                ← All members
              </Link>
            )}
          </p>
        </div>
        <Link href="/claims/new" className="btn-primary">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Submit Claim
        </Link>
      </div>

      {/* Filters */}
      <div className="card p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-all duration-150 ${
                statusFilter === s
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}
            >
              {s === "All" ? "All" : s.replace(/_/g, " ")}
              {s !== "All" && claims && (
                <span className="ml-1.5 opacity-70">
                  ({claims.filter((c) => c.status === s).length})
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
            fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            className="input pl-10"
            placeholder="Search by claim number or provider…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="card p-8"><LoadingSpinner message="Loading claims…" /></div>
      ) : error ? (
        <ErrorAlert error={error} title="Failed to load claims" />
      ) : filtered && filtered.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>Provider</th>
                  <th>Status</th>
                  <th className="text-right">Billed</th>
                  <th className="text-right">Covered</th>
                  <th className="text-right">Coverage %</th>
                  <th>Date</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((claim) => {
                  const billed = parseFloat(claim.total_billed);
                  const covered = parseFloat(claim.total_covered);
                  const pct = billed > 0 ? ((covered / billed) * 100).toFixed(0) : "0";
                  return (
                    <tr key={claim.id}>
                      <td>
                        <code className="text-xs font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                          {claim.claim_number}
                        </code>
                        <div className="text-xs text-slate-400 mt-0.5">
                          {claim.line_items.length} line item{claim.line_items.length !== 1 ? "s" : ""}
                        </div>
                      </td>
                      <td>
                        <p className="font-medium text-slate-800 text-sm">{claim.provider_name}</p>
                        <p className="text-xs text-slate-400 font-mono">{claim.provider_npi}</p>
                      </td>
                      <td><StatusBadge status={claim.status} size="sm" /></td>
                      <td className="text-right font-semibold tabular-nums">{formatCurrency(billed)}</td>
                      <td className="text-right font-semibold tabular-nums text-emerald-700">{formatCurrency(covered)}</td>
                      <td className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                Number(pct) >= 80 ? "bg-emerald-500" :
                                Number(pct) >= 50 ? "bg-amber-500" : "bg-red-500"
                              }`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-600 tabular-nums w-8 text-right">{pct}%</span>
                        </div>
                      </td>
                      <td className="text-slate-500 text-xs whitespace-nowrap">{formatDate(claim.submitted_at)}</td>
                      <td>
                        <Link href={`/claims/${claim.id}`} className="text-xs font-semibold text-blue-600 hover:text-blue-700">
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
      ) : (
        <div className="card p-12 text-center">
          <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-sm font-semibold text-slate-700 mb-1">No claims found</p>
          <p className="text-xs text-slate-400 mb-4">
            {statusFilter !== "All" ? "Try clearing the status filter." : "No claims have been submitted yet."}
          </p>
          <Link href="/claims/new" className="btn-primary">Submit First Claim</Link>
        </div>
      )}
    </div>
  );
}

export default function ClaimsPage() {
  return (
    <Suspense fallback={<LoadingSpinner message="Loading…" />}>
      <ClaimsListInner />
    </Suspense>
  );
}
