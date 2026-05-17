import type { ClaimStatus, LineItemStatus, DisputeStatus } from "@/lib/api";

type AnyStatus = ClaimStatus | LineItemStatus | DisputeStatus | string;

const statusConfig: Record<string, { label: string; classes: string }> = {
  // Claim statuses
  APPROVED: {
    label: "Approved",
    classes: "bg-green-100 text-green-800 border border-green-200",
  },
  DENIED: {
    label: "Denied",
    classes: "bg-red-100 text-red-800 border border-red-200",
  },
  PARTIALLY_APPROVED: {
    label: "Partially Approved",
    classes: "bg-yellow-100 text-yellow-800 border border-yellow-200",
  },
  DISPUTED: {
    label: "Disputed",
    classes: "bg-orange-100 text-orange-800 border border-orange-200",
  },
  PENDING: {
    label: "Pending",
    classes: "bg-gray-100 text-gray-700 border border-gray-200",
  },
  UNDER_REVIEW: {
    label: "Under Review",
    classes: "bg-blue-100 text-blue-800 border border-blue-200",
  },
  // Line item statuses
  COVERED: {
    label: "Covered",
    classes: "bg-green-100 text-green-800 border border-green-200",
  },
  PARTIALLY_COVERED: {
    label: "Partially Covered",
    classes: "bg-yellow-100 text-yellow-800 border border-yellow-200",
  },
  // Dispute statuses
  OPEN: {
    label: "Open",
    classes: "bg-blue-100 text-blue-800 border border-blue-200",
  },
  RESOLVED: {
    label: "Resolved",
    classes: "bg-green-100 text-green-800 border border-green-200",
  },
  // Dispute resolutions
  UPHELD: {
    label: "Upheld",
    classes: "bg-green-100 text-green-800 border border-green-200",
  },
};

interface StatusBadgeProps {
  status: AnyStatus;
  size?: "sm" | "md" | "lg";
}

export function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const config = statusConfig[status] ?? {
    label: status,
    classes: "bg-gray-100 text-gray-700 border border-gray-200",
  };

  const sizeClasses = {
    sm: "text-xs px-2 py-0.5 rounded",
    md: "text-sm px-2.5 py-1 rounded-md",
    lg: "text-base px-3 py-1.5 rounded-lg font-semibold",
  }[size];

  return (
    <span className={`inline-flex items-center font-medium ${sizeClasses} ${config.classes}`}>
      {config.label}
    </span>
  );
}
