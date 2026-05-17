"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  membersApi,
  policiesApi,
  type Member,
  type Policy,
  type CoverageRule,
} from "@/lib/api";
import { ErrorAlert } from "@/components/ErrorAlert";

// Standard coverage rule templates — clinicians pick from these
const SERVICE_TEMPLATES: CoverageRule[] = [
  { service_type: "PREVENTIVE", coverage_percentage: 100, requires_preauth: false, copay: 0, annual_limit: 2000 },
  { service_type: "SPECIALIST_VISIT", coverage_percentage: 80, requires_preauth: false, copay: 40, annual_limit: 5000 },
  { service_type: "EMERGENCY", coverage_percentage: 90, requires_preauth: false, copay: 150, annual_limit: 50000 },
  { service_type: "INPATIENT", coverage_percentage: 80, requires_preauth: true, copay: 250, annual_limit: 100000 },
  { service_type: "MENTAL_HEALTH", coverage_percentage: 80, requires_preauth: true, copay: 30, annual_limit: 3000 },
  { service_type: "LAB_WORK", coverage_percentage: 85, requires_preauth: false, copay: 20, annual_limit: 2500 },
  { service_type: "IMAGING", coverage_percentage: 80, requires_preauth: true, copay: 60, annual_limit: 5000 },
  { service_type: "PHARMACY", coverage_percentage: 75, requires_preauth: false, copay: 15, annual_limit: 3000 },
];

type Step = "member" | "policy" | "done";

interface Result {
  member: Member;
  policy: Policy;
}

function CopyText({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="ml-2 text-xs px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-500 border border-slate-200 transition-colors"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

export default function RegisterMemberPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("member");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  // Member form state
  const [name, setName] = useState("");
  const [dob, setDob] = useState("");
  const [email, setEmail] = useState("");
  const [memberId, setMemberId] = useState(`MBR-${Date.now()}`);

  // Policy form state
  const [policyNumber, setPolicyNumber] = useState(`POL-${Date.now()}`);
  const [effectiveDate] = useState(new Date().toISOString().split("T")[0]);
  const [expirationDate] = useState(`${new Date().getFullYear()}-12-31`);
  const [deductible, setDeductible] = useState("500");
  const [oopMax, setOopMax] = useState("5000");
  const [selectedServices, setSelectedServices] = useState<Set<string>>(
    new Set(["PREVENTIVE", "SPECIALIST_VISIT", "EMERGENCY", "LAB_WORK"])
  );
  const [createdMember, setCreatedMember] = useState<Member | null>(null);

  const toggleService = (st: string) => {
    setSelectedServices((prev) => {
      const next = new Set(prev);
      if (next.has(st)) next.delete(st);
      else next.add(st);
      return next;
    });
  };

  const handleRegisterMember = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const member = await membersApi.create({
        member_id: memberId.trim(),
        name: name.trim(),
        date_of_birth: dob,
        email: email.trim(),
      });
      setCreatedMember(member);
      setStep("policy");
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createdMember) return;
    setLoading(true);
    setError(null);
    try {
      const coverageRules = SERVICE_TEMPLATES.filter((t) => selectedServices.has(t.service_type));
      const policy = await policiesApi.create({
        member_id: createdMember.id,
        policy_number: policyNumber.trim(),
        effective_date: effectiveDate,
        expiration_date: expirationDate,
        deductible_amount: parseFloat(deductible),
        out_of_pocket_max: parseFloat(oopMax),
        coverage_rules: coverageRules,
      });
      setResult({ member: createdMember, policy });
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Breadcrumb + Header */}
      <div>
        <nav className="flex items-center gap-2 text-sm text-slate-400 mb-4">
          <Link href="/members" className="hover:text-slate-600">Members</Link>
          <span>/</span>
          <span className="text-slate-700 font-medium">Register Member</span>
        </nav>
        <h1 className="page-title">Member Registration</h1>
        <p className="text-sm text-slate-500 mt-1">
          Enroll a new member and configure their insurance coverage.
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-0">
        {(["member", "policy", "done"] as Step[]).map((s, i) => {
          const labels = ["Patient Info", "Coverage Setup", "Complete"];
          const isActive = step === s;
          const isDone = (step === "policy" && s === "member") || step === "done";
          return (
            <div key={s} className="flex items-center flex-1">
              <div className={`flex items-center gap-2 ${i > 0 ? "flex-1" : ""}`}>
                {i > 0 && (
                  <div className={`flex-1 h-px ${isDone || isActive ? "bg-blue-500" : "bg-slate-200"}`} />
                )}
                <div className="flex items-center gap-2">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                    isDone ? "bg-emerald-500 text-white" :
                    isActive ? "bg-blue-600 text-white" :
                    "bg-slate-200 text-slate-500"
                  }`}>
                    {isDone ? "✓" : i + 1}
                  </div>
                  <span className={`text-sm font-medium ${isActive ? "text-slate-900" : isDone ? "text-emerald-700" : "text-slate-400"}`}>
                    {labels[i]}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {error && <ErrorAlert error={error} title="Registration failed" />}

      {/* Step 1: Member info */}
      {step === "member" && (
        <form onSubmit={handleRegisterMember} className="space-y-5">
          <div className="card p-6 space-y-5">
            <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-600 text-xs font-bold flex items-center justify-center">1</span>
              Patient Information
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <label className="label">Full Name <span className="text-red-500">*</span></label>
                <input
                  className="input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Sarah Mitchell"
                  required
                />
              </div>

              <div>
                <label className="label">Date of Birth <span className="text-red-500">*</span></label>
                <input
                  type="date"
                  className="input"
                  value={dob}
                  onChange={(e) => setDob(e.target.value)}
                  required
                />
              </div>

              <div>
                <label className="label">Contact Email <span className="text-red-500">*</span></label>
                <input
                  type="email"
                  className="input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="patient@example.com"
                  required
                />
              </div>

              <div className="sm:col-span-2">
                <label className="label">Member ID</label>
                <input
                  className="input font-mono"
                  value={memberId}
                  onChange={(e) => setMemberId(e.target.value)}
                  placeholder="Plan-issued member identifier"
                />
                <p className="text-xs text-slate-400 mt-1">Auto-generated. Edit if you have a pre-existing plan ID.</p>
              </div>
            </div>

            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800 flex items-start gap-2">
              <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span><strong>PHI Notice:</strong> All patient data is encrypted at rest using AES-128-CBC before storage. Access is logged for compliance.</span>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <Link href="/members" className="btn-secondary">Cancel</Link>
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? (
                <><span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />Saving…</>
              ) : "Continue to Coverage →"}
            </button>
          </div>
        </form>
      )}

      {/* Step 2: Policy setup */}
      {step === "policy" && createdMember && (
        <form onSubmit={handleCreatePolicy} className="space-y-5">
          {/* Member summary */}
          <div className="card p-4 flex items-center gap-3 bg-emerald-50 border-emerald-200">
            <div className="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center text-white text-xs font-bold">
              ✓
            </div>
            <div>
              <p className="text-sm font-semibold text-emerald-800">{createdMember.name} registered</p>
              <p className="text-xs text-emerald-600 font-mono">{createdMember.id}</p>
            </div>
          </div>

          <div className="card p-6 space-y-5">
            <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-600 text-xs font-bold flex items-center justify-center">2</span>
              Coverage Configuration
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="label">Annual Deductible ($)</label>
                <input
                  type="number"
                  className="input"
                  value={deductible}
                  onChange={(e) => setDeductible(e.target.value)}
                  min="0"
                  step="50"
                  required
                />
              </div>
              <div>
                <label className="label">Out-of-Pocket Maximum ($)</label>
                <input
                  type="number"
                  className="input"
                  value={oopMax}
                  onChange={(e) => setOopMax(e.target.value)}
                  min="100"
                  step="100"
                  required
                />
              </div>
              <div>
                <label className="label">Policy Number</label>
                <input
                  className="input font-mono"
                  value={policyNumber}
                  onChange={(e) => setPolicyNumber(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="label">Coverage Period</label>
                <input className="input" value={`${effectiveDate} → ${expirationDate}`} disabled />
              </div>
            </div>

            <div>
              <label className="label">Covered Service Types</label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {SERVICE_TEMPLATES.map((t) => {
                  const active = selectedServices.has(t.service_type);
                  return (
                    <button
                      key={t.service_type}
                      type="button"
                      onClick={() => toggleService(t.service_type)}
                      className={`text-left p-3 rounded-lg border text-xs transition-all duration-150 ${
                        active
                          ? "border-blue-500 bg-blue-50 text-blue-900"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold">{t.service_type.replace(/_/g, " ")}</span>
                        <span className={`w-4 h-4 rounded flex items-center justify-center text-xs ${active ? "bg-blue-600 text-white" : "border border-slate-300"}`}>
                          {active ? "✓" : ""}
                        </span>
                      </div>
                      <div className="text-slate-500 space-x-2">
                        <span>{t.coverage_percentage}% coverage</span>
                        {t.copay != null && t.copay > 0 && <span>· ${t.copay} copay</span>}
                        {t.requires_preauth && <span className="text-amber-600">· Pre-auth required</span>}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="flex justify-between gap-3">
            <button type="button" onClick={() => setStep("member")} className="btn-ghost">
              ← Back
            </button>
            <div className="flex gap-3">
              <button type="submit" disabled={loading || selectedServices.size === 0} className="btn-primary">
                {loading ? (
                  <><span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />Creating…</>
                ) : "Complete Registration →"}
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Step 3: Done */}
      {step === "done" && result && (
        <div className="space-y-5">
          <div className="card p-6 bg-emerald-50 border-emerald-200 flex items-start gap-4">
            <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
              <svg className="w-5 h-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-emerald-900 text-base">Registration complete</h3>
              <p className="text-sm text-emerald-700 mt-1">
                {result.member.name} has been enrolled with policy {result.policy.policy_number}.
                Use the IDs below to submit claims.
              </p>
            </div>
          </div>

          <div className="card p-6 space-y-4">
            <h3 className="text-sm font-semibold text-slate-700">Registration Details</h3>

            <div className="space-y-3">
              {[
                { label: "Member System ID", value: result.member.id },
                { label: "Policy ID", value: result.policy.id },
                { label: "Policy Number", value: result.policy.policy_number },
              ].map(({ label, value }) => (
                <div key={label}>
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">{label}</p>
                  <div className="flex items-center gap-2">
                    <code className="text-sm font-mono bg-slate-50 border border-slate-200 rounded px-3 py-1.5 text-slate-800 flex-1 break-all">
                      {value}
                    </code>
                    <CopyText value={value} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href={`/claims/new?member_id=${result.member.id}&policy_id=${result.policy.id}`}
              className="btn-primary"
            >
              Submit a Claim
            </Link>
            <Link href="/members" className="btn-secondary">
              Back to Members
            </Link>
            <button
              onClick={() => {
                setStep("member");
                setCreatedMember(null);
                setResult(null);
                setError(null);
                setName("");
                setDob("");
                setEmail("");
                setMemberId(`MBR-${Date.now()}`);
                setPolicyNumber(`POL-${Date.now()}`);
              }}
              className="btn-ghost"
            >
              Register Another
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
