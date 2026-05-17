"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth, ROLE_LABELS, type UserRole } from "@/lib/auth";
import { authApi } from "@/lib/api";

type Step = 1 | 2 | 3;

const ROLES: { value: UserRole; label: string; description: string; icon: React.ReactNode }[] = [
  {
    value: "PATIENT",
    label: "Patient",
    description: "View and track your own insurance claims and coverage decisions",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    value: "PROVIDER",
    label: "Healthcare Provider",
    description: "Submit claims for your patients and track submission status",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    value: "CLAIM_PROCESSOR",
    label: "Claims Processor",
    description: "Process and adjudicate claims, manage the claims queue",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
  },
  {
    value: "ADMIN",
    label: "Administrator",
    description: "Full system access including user management and reporting",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

export default function RegisterPage() {
  const { setSession } = useAuth();
  const router = useRouter();

  const [step, setStep] = useState<Step>(1);
  const [role, setRole] = useState<UserRole>("PATIENT");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [memberId, setMemberId] = useState("");
  const [providerNpi, setProviderNpi] = useState("");
  const [providerName, setProviderName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const stepLabels = ["Account Type", "Your Details", "Role Details"];

  const handleNext = (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (step === 2) {
      if (password !== confirmPassword) {
        setError("Passwords do not match");
        return;
      }
      if (password.length < 8) {
        setError("Password must be at least 8 characters");
        return;
      }
      // Skip step 3 if no extra fields needed for PATIENT (member ID is optional)
      if (role === "ADMIN" || role === "CLAIM_PROCESSOR") {
        handleSubmit();
        return;
      }
    }

    setStep((s) => (s + 1) as Step);
  };

  const handleSubmit = async () => {
    setError("");
    setLoading(true);
    try {
      const payload: Parameters<typeof authApi.register>[0] = {
        email,
        password,
        full_name: fullName,
        role,
        ...(role === "PATIENT" && memberId ? { member_id: memberId } : {}),
        ...(role === "PROVIDER" ? { provider_npi: providerNpi, provider_name: providerName } : {}),
      };
      const res = await authApi.register(payload);
      setSession(res.user as Parameters<typeof setSession>[0], res.access_token);
      router.push("/");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Registration failed. Please try again.";
      setError(message);
      setLoading(false);
    }
  };

  const handleFinalSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSubmit();
  };

  return (
    <div className="w-full max-w-lg">
      <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-8 py-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 bg-white/20 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <span className="text-white font-bold text-lg">ClaimsIQ</span>
          </div>
          <h1 className="text-xl font-bold text-white">Create your account</h1>
          <p className="text-blue-200 text-sm mt-1">
            {ROLE_LABELS[role]} · Step {step} of {role === "ADMIN" || role === "CLAIM_PROCESSOR" ? 2 : 3}
          </p>

          {/* Step indicator */}
          <div className="flex items-center gap-2 mt-4">
            {stepLabels.slice(0, role === "ADMIN" || role === "CLAIM_PROCESSOR" ? 2 : 3).map((label, i) => {
              const n = i + 1;
              const done = step > n;
              const active = step === n;
              return (
                <div key={label} className="flex items-center gap-2">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                    done ? "bg-white text-blue-700" :
                    active ? "bg-blue-500 text-white ring-2 ring-white/30" :
                    "bg-blue-800/50 text-blue-300"
                  }`}>
                    {done ? "✓" : n}
                  </div>
                  <span className={`text-xs ${active ? "text-white font-semibold" : "text-blue-300"}`}>
                    {label}
                  </span>
                  {i < (role === "ADMIN" || role === "CLAIM_PROCESSOR" ? 1 : 2) && (
                    <div className={`h-px w-4 ${done ? "bg-white" : "bg-blue-700"}`} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Form */}
        <div className="px-8 py-7">
          {error && (
            <div className="mb-5 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 flex items-start gap-2">
              <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {error}
            </div>
          )}

          {/* Step 1: Role selection */}
          {step === 1 && (
            <form onSubmit={handleNext} className="space-y-4">
              <p className="text-sm text-slate-600 mb-4">
                Select the role that best describes how you&apos;ll use ClaimsIQ.
              </p>
              <div className="grid grid-cols-2 gap-3">
                {ROLES.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => setRole(r.value)}
                    className={`text-left p-4 rounded-xl border-2 transition-all duration-150 ${
                      role === r.value
                        ? "border-blue-600 bg-blue-50"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <div className={`mb-2 ${role === r.value ? "text-blue-600" : "text-slate-400"}`}>
                      {r.icon}
                    </div>
                    <p className={`text-sm font-semibold ${role === r.value ? "text-blue-900" : "text-slate-700"}`}>
                      {r.label}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5 leading-snug">{r.description}</p>
                  </button>
                ))}
              </div>
              <button type="submit" className="btn-primary w-full justify-center py-2.5 mt-2">
                Continue →
              </button>
            </form>
          )}

          {/* Step 2: Account details */}
          {step === 2 && (
            <form onSubmit={handleNext} className="space-y-4">
              <div>
                <label className="label" htmlFor="fullName">Full name</label>
                <input
                  id="fullName"
                  type="text"
                  required
                  className="input"
                  placeholder="Dr. Jane Smith"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="email">Email address</label>
                <input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  className="input"
                  placeholder="you@organization.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  required
                  className="input"
                  placeholder="Min. 8 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="confirmPassword">Confirm password</label>
                <input
                  id="confirmPassword"
                  type="password"
                  required
                  className="input"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setStep(1)} className="btn-secondary flex-1 justify-center">
                  ← Back
                </button>
                <button type="submit" className="btn-primary flex-1 justify-center">
                  {role === "ADMIN" || role === "CLAIM_PROCESSOR" ? "Create Account" : "Continue →"}
                </button>
              </div>
            </form>
          )}

          {/* Step 3: Role-specific details */}
          {step === 3 && (
            <form onSubmit={handleFinalSubmit} className="space-y-4">
              {role === "PATIENT" && (
                <>
                  <div className="rounded-lg bg-blue-50 border border-blue-100 px-4 py-3 text-sm text-blue-700">
                    <p className="font-semibold mb-1">Link your member record</p>
                    <p className="text-xs text-blue-600">
                      If you have a Member ID from your insurance plan, enter it here to link
                      your claims history. You can also skip this and link it later via your administrator.
                    </p>
                  </div>
                  <div>
                    <label className="label" htmlFor="memberId">
                      Member ID <span className="text-slate-400 font-normal">(optional)</span>
                    </label>
                    <input
                      id="memberId"
                      type="text"
                      className="input"
                      placeholder="e.g. MBR-2024-001234"
                      value={memberId}
                      onChange={(e) => setMemberId(e.target.value)}
                    />
                  </div>
                </>
              )}

              {role === "PROVIDER" && (
                <>
                  <div className="rounded-lg bg-amber-50 border border-amber-100 px-4 py-3 text-sm text-amber-700">
                    <p className="font-semibold mb-1">Provider identification</p>
                    <p className="text-xs text-amber-600">
                      Your NPI must match the provider NPI used when submitting claims. This links your
                      account to all claims submitted under your NPI.
                    </p>
                  </div>
                  <div>
                    <label className="label" htmlFor="providerName">Organization / Practice name</label>
                    <input
                      id="providerName"
                      type="text"
                      required
                      className="input"
                      placeholder="City Medical Center"
                      value={providerName}
                      onChange={(e) => setProviderName(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor="providerNpi">
                      NPI Number <span className="text-xs text-slate-400">(10 digits)</span>
                    </label>
                    <input
                      id="providerNpi"
                      type="text"
                      required
                      pattern="\d{10}"
                      maxLength={10}
                      className="input font-mono"
                      placeholder="1234567890"
                      value={providerNpi}
                      onChange={(e) => setProviderNpi(e.target.value.replace(/\D/g, ""))}
                    />
                  </div>
                </>
              )}

              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setStep(2)} className="btn-secondary flex-1 justify-center">
                  ← Back
                </button>
                <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
                  {loading ? (
                    <>
                      <span className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      Creating…
                    </>
                  ) : (
                    "Create Account"
                  )}
                </button>
              </div>
            </form>
          )}

          <p className="text-center text-sm text-slate-500 mt-5">
            Already have an account?{" "}
            <Link href="/login" className="text-blue-600 font-semibold hover:text-blue-700">
              Sign in
            </Link>
          </p>
        </div>
      </div>

      <p className="text-center text-xs text-slate-400 mt-6">
        ClaimsIQ — Enterprise Claims Management Platform
      </p>
    </div>
  );
}
