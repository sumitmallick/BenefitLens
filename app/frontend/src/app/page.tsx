import Link from "next/link";

const steps = [
  {
    step: "01",
    title: "Run Demo Setup",
    description:
      "Visit the Demo Setup page to automatically create a test member and a comprehensive insurance policy. The system will return a Member ID and Policy ID you'll use in the next step.",
    href: "/demo",
    linkLabel: "Go to Demo Setup",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
        />
      </svg>
    ),
  },
  {
    step: "02",
    title: "Submit a Claim",
    description:
      "Use the Member ID and Policy ID from step 1 to submit a multi-line insurance claim. Add service line items (specialist visit, lab work, etc.) with billed amounts. The system adjudicates it in real time.",
    href: "/claims/new",
    linkLabel: "Submit Claim",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    ),
  },
  {
    step: "03",
    title: "Review Adjudication",
    description:
      "After submission, view each line item's adjudication result — COVERED, PARTIALLY COVERED, or DENIED — with amounts and explanations. See the full claim explanation powered by the AI explain endpoint.",
    href: "/claims/new",
    linkLabel: "View Claims",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
        />
      </svg>
    ),
  },
  {
    step: "04",
    title: "Dispute a Claim",
    description:
      "If a claim is denied or partially approved, file a dispute with a written reason. Track dispute status (OPEN → UNDER REVIEW → RESOLVED) and see whether it's UPHELD or DENIED.",
    href: "/claims/new",
    linkLabel: "Learn More",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
        />
      </svg>
    ),
  },
];

const features = [
  {
    title: "Real-Time Adjudication",
    description:
      "Claims are adjudicated instantly against policy coverage rules, with per-line-item status tracking.",
  },
  {
    title: "AI-Powered Explanations",
    description:
      "Every claim decision includes a natural-language explanation of why each line item was approved or denied.",
  },
  {
    title: "Dispute Management",
    description:
      "Members can file disputes and track them from submission through resolution with full audit trail.",
  },
  {
    title: "Comprehensive Coverage Rules",
    description:
      "Support for deductibles, copays, coverage percentages, prior auth requirements, and annual benefit limits.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-16">
      {/* Hero */}
      <section className="text-center py-12 px-4">
        <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 text-xs font-semibold px-3 py-1.5 rounded-full mb-6 border border-blue-100">
          <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
          Live API Integration
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-gray-900 mb-4 tracking-tight">
          Insurance Claims
          <span className="text-blue-600"> Processing System</span>
        </h1>
        <p className="text-lg text-gray-500 max-w-2xl mx-auto mb-8">
          A full-stack claims adjudication platform. Submit insurance claims,
          get real-time coverage decisions, request AI explanations, and manage
          disputes — all backed by a live REST API.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link href="/demo" className="btn-primary px-6 py-2.5 text-base">
            Get Started with Demo
          </Link>
          <Link href="/claims/new" className="btn-secondary px-6 py-2.5 text-base">
            Submit a Claim
          </Link>
        </div>
      </section>

      {/* Steps */}
      <section>
        <h2 className="text-2xl font-bold text-gray-900 text-center mb-10">
          How It Works
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((s) => (
            <div key={s.step} className="card p-6 flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0">
                  {s.icon}
                </div>
                <span className="text-3xl font-black text-gray-100">{s.step}</span>
              </div>
              <div>
                <h3 className="font-semibold text-gray-900 mb-1">{s.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">
                  {s.description}
                </p>
              </div>
              <Link
                href={s.href}
                className="mt-auto text-sm font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                {s.linkLabel}
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="bg-white rounded-2xl border border-gray-200 p-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-8 text-center">
          Platform Features
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {features.map((f) => (
            <div key={f.title} className="flex items-start gap-4 p-4 rounded-xl bg-gray-50">
              <div className="w-2 h-2 mt-2 rounded-full bg-blue-500 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-gray-900 mb-1">{f.title}</h3>
                <p className="text-sm text-gray-500">{f.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* API info banner */}
      <section className="rounded-xl border border-blue-100 bg-blue-50 p-6 flex items-start gap-4">
        <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
          <svg className="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div>
          <h3 className="font-semibold text-blue-900 mb-1">Backend API Required</h3>
          <p className="text-sm text-blue-700">
            This frontend connects to a live backend at{" "}
            <code className="bg-blue-100 px-1.5 py-0.5 rounded font-mono text-xs">
              http://localhost:8000
            </code>
            . Make sure the API server is running before using the application.
            All data is real — nothing is mocked or simulated.
          </p>
        </div>
      </section>
    </div>
  );
}
