"use client";

/**
 * /activate-insurance — hidden page (not in sidebar nav)
 *
 * Visiting this URL as a PATIENT automatically:
 *   1. Calls POST /api/v1/auth/me/activate-demo (idempotent)
 *   2. Updates the in-memory auth context with the returned user (now has member_id)
 *   3. Redirects to /my-insurance so the patient sees their live insurance card
 *
 * Non-PATIENT roles are bounced to / immediately.
 * Already-linked patients are bounced to /my-insurance immediately.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Stage = "loading" | "activating" | "done" | "already_linked" | "error";

export default function ActivateInsurancePage() {
  const { user, isLoading: authLoading, updateUser } = useAuth();
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("loading");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;

    if (!user) {
      router.replace("/login");
      return;
    }

    if (user.role !== "PATIENT") {
      router.replace("/");
      return;
    }

    if (user.member_id) {
      setStage("already_linked");
      const t = setTimeout(() => router.replace("/my-insurance"), 1200);
      return () => clearTimeout(t);
    }

    setStage("activating");

    authApi
      .activateDemo()
      .then((updatedUser) => {
        updateUser(updatedUser);
        setStage("done");
        setTimeout(() => router.replace("/my-insurance"), 1500);
      })
      .catch((err: unknown) => {
        setErrorMsg(
          err instanceof Error ? err.message : "Something went wrong — please try again."
        );
        setStage("error");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="max-w-sm w-full text-center space-y-6 px-4">
        {(stage === "loading" || stage === "activating") && (
          <>
            <div className="w-16 h-16 mx-auto rounded-full bg-blue-50 flex items-center justify-center">
              <svg
                className="w-8 h-8 text-blue-600 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                />
              </svg>
            </div>
            <div>
              <p className="text-lg font-semibold text-slate-800">
                {stage === "loading" ? "Loading…" : "Activating your insurance…"}
              </p>
              <p className="text-sm text-slate-500 mt-1">
                Setting up your member record and policy. This takes just a moment.
              </p>
            </div>
          </>
        )}

        {(stage === "done" || stage === "already_linked") && (
          <>
            <div className="w-16 h-16 mx-auto rounded-full bg-emerald-50 flex items-center justify-center">
              <svg
                className="w-8 h-8 text-emerald-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            </div>
            <div>
              <p className="text-lg font-semibold text-slate-800">
                {stage === "already_linked"
                  ? "Insurance already active"
                  : "Insurance activated!"}
              </p>
              <p className="text-sm text-slate-500 mt-1">
                Redirecting you to your insurance portal…
              </p>
            </div>
          </>
        )}

        {stage === "error" && (
          <>
            <div className="w-16 h-16 mx-auto rounded-full bg-red-50 flex items-center justify-center">
              <svg
                className="w-8 h-8 text-red-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
            <div>
              <p className="text-lg font-semibold text-slate-800">Activation failed</p>
              <p className="text-sm text-red-600 mt-1">{errorMsg}</p>
              <button
                onClick={() => {
                  setStage("activating");
                  setErrorMsg(null);
                  authApi
                    .activateDemo()
                    .then((u) => {
                      updateUser(u);
                      setStage("done");
                      setTimeout(() => router.replace("/my-insurance"), 1500);
                    })
                    .catch((err: unknown) => {
                      setErrorMsg(
                        err instanceof Error ? err.message : "Unknown error"
                      );
                      setStage("error");
                    });
                }}
                className="mt-4 btn-secondary"
              >
                Try again
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
