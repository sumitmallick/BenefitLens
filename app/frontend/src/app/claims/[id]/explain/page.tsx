"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { claimsApi, type LineItemExplanation } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { LoadingSpinner } from "@/components/LoadingSpinner";

function formatCurrency(amount: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(amount);
}

function ExplanationCard({ item }: { item: LineItemExplanation }) {
  const billedAmount = parseFloat(item.billed_amount);
  const coveredAmount = parseFloat(item.covered_amount);
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      {/* Card header */}
      <div
        className={`px-5 py-4 flex flex-wrap items-center justify-between gap-3 ${
          item.status === "COVERED"
            ? "bg-green-50 border-b border-green-100"
            : item.status === "PARTIALLY_COVERED"
            ? "bg-yellow-50 border-b border-yellow-100"
            : "bg-red-50 border-b border-red-100"
        }`}
      >
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-semibold text-gray-900">
            {item.service_type.replace(/_/g, " ")}
          </span>
          <StatusBadge status={item.status} />
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-500">
            Billed: <span className="font-semibold text-gray-800">{formatCurrency(billedAmount)}</span>
          </span>
          <span className="text-gray-500">
            Covered:{" "}
            <span
              className={`font-semibold ${
                coveredAmount > 0 ? "text-green-700" : "text-red-600"
              }`}
            >
              {formatCurrency(coveredAmount)}
            </span>
          </span>
        </div>
      </div>

      {/* Explanation body */}
      <div className="px-5 py-4 space-y-4">
        {/* Main explanation */}
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            Explanation
          </p>
          <p className="text-sm text-gray-700 leading-relaxed">{item.explanation}</p>
        </div>

        {/* Denial reason */}
        {item.denial_reason && (
          <div className="rounded-lg bg-red-50 border border-red-100 p-3">
            <p className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-1">
              Denial Reason
            </p>
            <p className="text-sm text-red-800">{item.denial_reason}</p>
          </div>
        )}

        {/* Line item ID */}
        <div className="text-xs text-gray-400">
          Line item ID:{" "}
          <code className="font-mono bg-gray-100 px-1 py-0.5 rounded">{item.line_item_id}</code>
        </div>
      </div>
    </div>
  );
}

export default function ClaimExplainPage() {
  const { id } = useParams<{ id: string }>();

  const {
    data: explanation,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["claim-explain", id],
    queryFn: () => claimsApi.explain(id),
    enabled: !!id,
  });

  if (isLoading) {
    return <LoadingSpinner message="Loading claim explanation..." />;
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <ErrorAlert error={error} title="Failed to load explanation" />
        <button onClick={() => refetch()} className="btn-secondary">
          Retry
        </button>
      </div>
    );
  }

  if (!explanation) return null;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400">
        <Link href="/" className="hover:text-gray-600">Home</Link>
        <span>/</span>
        <Link href={`/claims/${id}`} className="hover:text-gray-600">
          Claim {explanation.claim_number}
        </Link>
        <span>/</span>
        <span className="text-gray-700 font-medium">Explanation</span>
      </nav>

      {/* Page header */}
      <div className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="page-title mb-2">
              Claim Explanation
            </h1>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500">
                Claim {explanation.claim_number}
              </span>
              <StatusBadge status={explanation.claim_status} size="md" />
            </div>
          </div>
          <Link href={`/claims/${id}`} className="btn-secondary">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Claim
          </Link>
        </div>

        {/* Totals */}
        <div className="mt-5 grid grid-cols-2 gap-4 text-sm">
          <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
            <p className="text-xs text-gray-400 mb-1">Total Billed</p>
            <p className="font-semibold text-gray-900">
              {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(parseFloat(explanation.total_billed))}
            </p>
          </div>
          <div className="rounded-lg bg-green-50 border border-green-100 p-3">
            <p className="text-xs text-gray-400 mb-1">Total Covered</p>
            <p className="font-semibold text-green-700">
              {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(parseFloat(explanation.total_covered))}
            </p>
          </div>
        </div>
      </div>

      {/* Per-line-item explanations */}
      <div className="space-y-4">
        <h2 className="section-title flex items-center gap-2">
          <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Per-Line-Item Explanations ({explanation.line_item_explanations.length})
        </h2>

        {explanation.line_item_explanations.length === 0 ? (
          <div className="card p-8 text-center text-gray-400">
            No explanation data available for this claim.
          </div>
        ) : (
          <div className="space-y-3">
            {explanation.line_item_explanations.map((item) => (
              <ExplanationCard key={item.line_item_id} item={item} />
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <Link href={`/claims/${id}`} className="btn-secondary">
          Back to Claim Detail
        </Link>
        <Link href={`/claims/${id}/dispute`} className="btn-danger">
          File a Dispute
        </Link>
        <Link href="/claims/new" className="btn-primary">
          Submit Another Claim
        </Link>
      </div>
    </div>
  );
}
