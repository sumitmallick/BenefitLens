import { ApiError } from "@/lib/api";

interface ErrorAlertProps {
  error: unknown;
  title?: string;
}

export function ErrorAlert({ error, title = "An error occurred" }: ErrorAlertProps) {
  let message = "Something went wrong. Please try again.";

  if (error instanceof ApiError) {
    const body = error.body;
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = detail
          .map((d) =>
            typeof d === "object" && d !== null && "msg" in d
              ? String((d as { msg: unknown }).msg)
              : String(d)
          )
          .join(", ");
      }
    } else {
      message = `${error.status} ${error.statusText}`;
    }
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex-shrink-0">
          <svg
            className="h-5 w-5 text-red-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-red-800">{title}</h3>
          <p className="mt-1 text-sm text-red-700">{message}</p>
        </div>
      </div>
    </div>
  );
}
