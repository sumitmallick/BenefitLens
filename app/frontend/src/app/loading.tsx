export default function GlobalLoading() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
      {/* Spinner */}
      <div className="relative h-12 w-12">
        <div className="absolute inset-0 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
      </div>

      {/* Skeleton rows — gives the page a sense of shape while loading */}
      <div className="w-full max-w-2xl space-y-3 px-4">
        <div className="h-4 animate-pulse rounded bg-gray-200" style={{ width: "60%" }} />
        <div className="h-4 animate-pulse rounded bg-gray-200" style={{ width: "80%" }} />
        <div className="h-4 animate-pulse rounded bg-gray-200" style={{ width: "45%" }} />
      </div>
    </div>
  );
}
