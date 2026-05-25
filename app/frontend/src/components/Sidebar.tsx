"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth, can, ROLE_LABELS, ROLE_COLORS, type UserRole } from "@/lib/auth";

interface NavItem {
  href: string;
  label: string;
  exact?: boolean;
  icon: React.ReactNode;
  badge?: string;
}

// ── Icons (inline SVG) ────────────────────────────────────────────────────

const HomeIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
  </svg>
);

const ClaimsIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

const MembersIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

const PlusIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
  </svg>
);

const UsersIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
  </svg>
);

const DisputeIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </svg>
);

const ShieldIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
  </svg>
);

// ── Role-based nav config ─────────────────────────────────────────────────

function buildNav(role: UserRole): { title: string; items: NavItem[] }[] {
  const common: NavItem = {
    href: "/",
    label: "Dashboard",
    exact: true,
    icon: <HomeIcon />,
  };

  if (role === "ADMIN") {
    return [
      {
        title: "Overview",
        items: [common],
      },
      {
        title: "Operations",
        items: [
          { href: "/members", label: "Members", icon: <MembersIcon /> },
          { href: "/claims", label: "Claims Queue", icon: <ClaimsIcon /> },
        ],
      },
      {
        title: "Actions",
        items: [
          { href: "/members/new", label: "Register Member", icon: <MembersIcon /> },
          { href: "/claims/new", label: "Submit Claim", icon: <PlusIcon />, badge: "New" },
        ],
      },
      {
        title: "Administration",
        items: [
          { href: "/admin/users", label: "User Management", icon: <UsersIcon /> },
        ],
      },
    ];
  }

  if (role === "CLAIM_PROCESSOR") {
    return [
      { title: "Overview", items: [common] },
      {
        title: "Operations",
        items: [
          { href: "/claims", label: "Claims Queue", icon: <ClaimsIcon /> },
          { href: "/members", label: "Members", icon: <MembersIcon /> },
        ],
      },
      {
        title: "Actions",
        items: [
          { href: "/members/new", label: "Register Member", icon: <MembersIcon /> },
          { href: "/claims/new", label: "Submit Claim", icon: <PlusIcon />, badge: "New" },
        ],
      },
    ];
  }

  if (role === "PROVIDER") {
    return [
      { title: "Overview", items: [common] },
      {
        title: "Claims",
        items: [
          { href: "/claims/new", label: "Submit New Claim", icon: <PlusIcon />, badge: "New" },
          { href: "/claims", label: "My Submissions", icon: <ClaimsIcon /> },
        ],
      },
    ];
  }

  // PATIENT
  return [
    {
      title: "My Account",
      items: [
        { href: "/my-insurance", label: "My Insurance", icon: <ShieldIcon /> },
        { href: "/claims", label: "My Claims", icon: <ClaimsIcon /> },
      ],
    },
  ];
}

// ── Sidebar component ──────────────────────────────────────────────────────

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  if (!user) return null;

  const navSections = buildNav(user.role as UserRole);

  const isActive = (item: NavItem) =>
    item.exact ? pathname === item.href : pathname.startsWith(item.href);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const initials = user.full_name
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <aside
      className="fixed inset-y-0 left-0 z-50 flex flex-col"
      style={{ width: "var(--sidebar-width)", background: "var(--color-sidebar)" }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-slate-800">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-bold text-white leading-none">ClaimsIQ</p>
          <p className="text-xs text-slate-500 mt-0.5">Claims Platform</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {navSections.map((section) => (
          <div key={section.title}>
            <p className="nav-section-label mb-2">{section.title}</p>
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`nav-item ${isActive(item) ? "nav-item-active" : ""}`}
                >
                  {item.icon}
                  <span className="flex-1">{item.label}</span>
                  {item.badge && (
                    <span className="text-xs bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded font-medium">
                      {item.badge}
                    </span>
                  )}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* User footer */}
      <div className="px-3 py-4 border-t border-slate-800 space-y-3">
        {/* Role badge */}
        <div className="px-1">
          <span className={`text-xs font-semibold px-2 py-1 rounded-full border ${ROLE_COLORS[user.role as UserRole]}`}>
            {ROLE_LABELS[user.role as UserRole]}
          </span>
        </div>

        {/* User info + logout */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-slate-300 truncate">{user.full_name}</p>
            <p className="text-xs text-slate-600 truncate">{user.email}</p>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-500 hover:text-white hover:bg-slate-700 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}
