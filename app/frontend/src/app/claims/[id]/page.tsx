"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { claimsApi, type AdjudicatedLineItem } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { LoadingSpinner } from "@/components/LoadingSpinner";

function formatCurrency(amount: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(amount);
}

function formatDate(dateStr: string) {
  try {
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

function LineItemRow({ item }: { item: AdjudicatedLineItem }) {
  const billedAmount = parseFloat(item.billed_amount);
  const coveredAmount = parseFloat(item.adjudication?.covered_amount ?? "0");
  const coverageRatio =
    billedAmount > 0
      ? Math.min((coveredAmount / billedAmount) * 100, 100)
      : 0;

  return (
    <div className="border border-gray-200 rounded-xl p-5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-gray-900">
              {item.service_type.replace(/_/g, " ")}
            </span>
            <StatusBadge status={item.status} />
          </div>
          {item.description && (
            <p className="text-sm text-gray-500">{item.description}</p>
          )}
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-400 mb-0.5">Service date</p>
          <p className="text-sm font-medium text-gray-700">{formatDate(item.service_date)}</p>
        </div>
      </div>

      {/* Codes */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <span className="font-medium text-gray-600">Dx:</span>
          <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">
            {item.diagnosis_code}
          </code>
        </div>
        {item.procedure_code && (
          <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <span className="font-medium text-gray-600">CPT:</span>
            <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">
              {item.procedure_code}
            </code>
          </div>
        )}
      </div>

      {/* Amounts */}
      <div className="grid grid-cols-3 gap-4 pt-2 border-t border-gray-100">
        <div>
          <p className="text-xs text-gray-400 mb-0.5">Billed</p>
          <p className="font-semibold text-gray-900">{formatCurrency(billedAmount)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 mb-0.5">Covered</p>
          <p className={`font-semibold ${coveredAmount > 0 ? "text-green-700" : "text-red-600"}`}>
            {formatCurrency(coveredAmount)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 mb-0.5">Member Owes</p>
          <p className="font-semibold text-gray-700">
            {formatCurrency(billedAmount - coveredAmount)}
          </p>
        </div>
      </div>

      {/* Coverage bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Coverage</span>
          <span>{coverageRatio.toFixed(0)}%</span>
        </div>
        <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              item.status === "COVERED"
                ? "bg-green-500"
                : item.status === "PARTIALLY_COVERED"
                ? "bg-yellow-500"
                : "bg-red-400"
            }`}
            style={{ width: `${coverageRatio}%` }}
          />
        </div>
      </div>

      {/* Denial reason / explanation */}
      {item.adjudication?.denial_reason && (
        <div className="rounded-lg bg-red-50 border border-red-100 p-3 text-sm text-red-700">
          <span className="font-medium">Denial reason: </span>
          {item.adjudication.denial_reason}
        </div>
      )}
      {item.adjudication?.explanation && !item.adjudication?.denial_reason && (
        <div className="rounded-lg bg-blue-50 border border-blue-100 p-3 text-sm text-blue-700">
          <span className="font-medium">Note: </span>
          {item.adjudication.explanation}
        </div>
      )}
    </div>
  );
}

export default function ClaimDetailPage() {
  const { id } = useParams<{ id: string }>();

  const {
    data: claim,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["claim", id],
    queryFn: () => claimsApi.getById(id),
    enabled: !!id,
  });

  if (isLoading) {
    return <LoadingSpinner message="Loading claim details..." />;
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <ErrorAlert error={error} title="Failed to load claim" />
        <button onClick={() => refetch()} className="btn-secondary">
          Retry
        </button>
      </div>
    );
  }

  if (!claim) return null;

  const totalBilled = parseFloat(claim.total_billed);
  const totalCovered = parseFloat(claim.total_covered);
  const memberOwes = totalBilled - totalCovered;
  const coveragePct =
    totalBilled > 0
      ? ((totalCovered / totalBilled) * 100).toFixed(1)
      : "0";

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400">
        <Link href="/" className="hover:text-gray-600">Home</Link>
        <span>/</span>
        <span className="text-gray-700 font-medium">Claim {claim.claim_number}</span>
      </nav>

      {/* Claim header */}
      <div className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="page-title">Claim {claim.claim_number}</h1>
              <StatusBadge status={claim.status} size="lg" />
            </div>
            <p className="text-sm text-gray-500">
              Submitted {formatDate(claim.submitted_at)} &bull; Claim ID:{" "}
              <code className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">{claim.id}</code>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href={`/claims/${id}/explain`} className="btn-secondary">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              View Explanation
            </Link>
            {(claim.status === "DENIED" || claim.status === "PARTIALLY_APPROVED") && (
              <Link href={`/claims/${id}/dispute`} className="btn-danger">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                File Dispute
              </Link>
            )}
          </div>
        </div>

        {/* Summary grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="rounded-xl bg-gray-50 p-4">
            <p className="text-xs text-gray-400 mb-1">Total Billed</p>
            <p className="text-xl font-bold text-gray-900">
              {formatCurrency(totalBilled)}
            </p>
          </div>
          <div className="rounded-xl bg-green-50 p-4">
            <p className="text-xs text-gray-400 mb-1">Total Covered</p>
            <p className="text-xl font-bold text-green-700">
              {formatCurrency(totalCovered)}
            </p>
          </div>
          <div className="rounded-xl bg-orange-50 p-4">
            <p className="text-xs text-gray-400 mb-1">Member Owes</p>
            <p className="text-xl font-bold text-orange-700">
              {formatCurrency(memberOwes)}
            </p>
          </div>
          <div className="rounded-xl bg-blue-50 p-4">
            <p className="text-xs text-gray-400 mb-1">Coverage Rate</p>
            <p className="text-xl font-bold text-blue-700">{coveragePct}%</p>
          </div>
        </div>

      </div>

      {/* Line Items */}
      <div className="space-y-4">
        <h2 className="section-title flex items-center gap-2">
          <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          Service Line Items ({claim.line_items.length})
        </h2>
        {claim.line_items.length === 0 ? (
          <div className="card p-8 text-center text-gray-400">No line items found.</div>
        ) : (
          <div className="space-y-3">
            {claim.line_items.map((item) => (
              <LineItemRow key={item.id} item={item} />
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <Link href="/claims/new" className="btn-secondary">
          Submit Another Claim
        </Link>
        <Link href={`/claims/${id}/explain`} className="btn-primary">
          View Full Explanation
        </Link>
      </div>
    </div>
  );
}
