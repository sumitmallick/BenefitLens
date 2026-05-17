"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { claimsApi, disputesApi, type Dispute } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { LoadingSpinner } from "@/components/LoadingSpinner";

function formatDate(dateStr: string) {
  try {
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function DisputeCard({ dispute }: { dispute: Dispute }) {
  return (
    <div className="border border-gray-200 rounded-xl p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-900">
            Dispute #{dispute.id.slice(0, 8)}
          </span>
          <StatusBadge status={dispute.status} />
        </div>
        <span className="text-xs text-gray-400">{formatDate(dispute.submitted_at)}</span>
      </div>

      <div>
        <p className="text-xs font-medium text-gray-500 mb-0.5">Reason</p>
        <p className="text-sm text-gray-800">{dispute.reason}</p>
      </div>

      {dispute.resolution_notes && (
        <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Resolution Notes
          </p>
          <p className="text-sm text-gray-700">{dispute.resolution_notes}</p>
          {dispute.resolved_at && (
            <p className="text-xs text-gray-400 mt-1">
              Resolved on {formatDate(dispute.resolved_at)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function DisputePage() {
  const { id: claimId } = useParams<{ id: string }>();
  const router = useRouter();

  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<Error | null>(null);
  const [success, setSuccess] = useState(false);

  const {
    data: claim,
    isLoading: claimLoading,
    error: claimError,
  } = useQuery({
    queryKey: ["claim", claimId],
    queryFn: () => claimsApi.getById(claimId),
    enabled: !!claimId,
  });

  const {
    data: disputes,
    isLoading: disputesLoading,
    error: disputesError,
    refetch: refetchDisputes,
  } = useQuery({
    queryKey: ["disputes", claimId],
    queryFn: () => disputesApi.listByClaim(claimId),
    enabled: !!claimId,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) {
      setSubmitError(new Error("Please provide a reason for the dispute."));
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      await disputesApi.submit(claimId, {
        reason: reason.trim(),
      });
      setSuccess(true);
      setReason("");
      await refetchDisputes();
    } catch (err) {
      setSubmitError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setSubmitting(false);
    }
  };

  if (claimLoading) {
    return <LoadingSpinner message="Loading claim..." />;
  }

  if (claimError) {
    return (
      <div className="max-w-3xl mx-auto">
        <ErrorAlert error={claimError} title="Failed to load claim" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400">
        <Link href="/" className="hover:text-gray-600">Home</Link>
        <span>/</span>
        <Link href={`/claims/${claimId}`} className="hover:text-gray-600">
          Claim {claim?.claim_number}
        </Link>
        <span>/</span>
        <span className="text-gray-700 font-medium">Dispute</span>
      </nav>

      {/* Claim summary */}
      {claim && (
        <div className="card p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="page-title mb-1">File a Dispute</h1>
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span>Claim {claim.claim_number}</span>
                <StatusBadge status={claim.status} size="sm" />
              </div>
            </div>
            <Link href={`/claims/${claimId}`} className="btn-secondary">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Back to Claim
            </Link>
          </div>

          {/* Claim amounts */}
          {(() => {
            const billed = parseFloat(claim.total_billed);
            const covered = parseFloat(claim.total_covered);
            const fmt = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
            return (
              <div className="mt-4 grid grid-cols-3 gap-3">
                <div className="rounded-lg bg-gray-50 px-4 py-3">
                  <p className="text-xs text-gray-400">Total Billed</p>
                  <p className="font-semibold text-gray-900">{fmt(billed)}</p>
                </div>
                <div className="rounded-lg bg-green-50 px-4 py-3">
                  <p className="text-xs text-gray-400">Covered</p>
                  <p className="font-semibold text-green-700">{fmt(covered)}</p>
                </div>
                <div className="rounded-lg bg-orange-50 px-4 py-3">
                  <p className="text-xs text-gray-400">Member Owes</p>
                  <p className="font-semibold text-orange-700">{fmt(billed - covered)}</p>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* Success message */}
      {success && (
        <div className="rounded-xl bg-green-50 border border-green-200 p-5 flex items-start gap-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
            <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-green-900">Dispute submitted successfully</h3>
            <p className="text-sm text-green-700 mt-1">
              Your dispute has been filed and is now under review. You can track its status below.
            </p>
          </div>
        </div>
      )}

      {/* Dispute form */}
      <div className="card p-6 space-y-5">
        <h2 className="section-title flex items-center gap-2">
          <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          New Dispute
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label" htmlFor="reason">
              Reason for Dispute <span className="text-red-500">*</span>
            </label>
            <input
              id="reason"
              type="text"
              className="input"
              placeholder="e.g. Service was covered under my policy but was incorrectly denied"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          </div>

          {submitError && (
            <ErrorAlert error={submitError} title="Failed to submit dispute" />
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn-danger"
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
                      d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                  Submit Dispute
                </>
              )}
            </button>
            <Link href={`/claims/${claimId}`} className="btn-secondary">
              Cancel
            </Link>
          </div>
        </form>
      </div>

      {/* Existing disputes */}
      <div className="space-y-4">
        <h2 className="section-title flex items-center gap-2">
          <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          Disputes on this Claim
        </h2>

        {disputesLoading && <LoadingSpinner message="Loading disputes..." />}
        {disputesError && (
          <ErrorAlert error={disputesError} title="Failed to load disputes" />
        )}
        {!disputesLoading && !disputesError && disputes && (
          <>
            {disputes.length === 0 ? (
              <div className="card p-8 text-center text-gray-400 text-sm">
                No disputes filed for this claim yet.
              </div>
            ) : (
              <div className="space-y-3">
                {disputes.map((d) => (
                  <DisputeCard key={d.id} dispute={d} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
