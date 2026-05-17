"use client";

/**
 * LayoutShell — route guard + conditional layout.
 *
 * - /login and /register render as centered auth pages (no sidebar)
 * - All other routes require authentication; unauthenticated users are
 *   redirected to /login
 * - Authenticated users see the full app shell: Sidebar + content area
 */

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/Sidebar";
import { LoadingSpinner } from "@/components/LoadingSpinner";

const AUTH_PATHS = ["/login", "/register"];

export function LayoutShell({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isAuthPage = AUTH_PATHS.some((p) => pathname.startsWith(p));

  useEffect(() => {
    if (!isLoading && !user && !isAuthPage) {
      router.replace("/login");
    }
    // Redirect logged-in users away from login/register
    if (!isLoading && user && isAuthPage) {
      router.replace("/");
    }
  }, [isLoading, user, isAuthPage, router]);

  // Auth pages: centered, no sidebar
  if (isAuthPage) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
        {children}
      </div>
    );
  }

  // Loading state while checking stored token
  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-100 flex items-center justify-center">
        <LoadingSpinner message="Loading…" />
      </div>
    );
  }

  // Unauthenticated — will redirect, render nothing
  if (!user) return null;

  // Full app shell
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div
        className="flex-1 flex flex-col min-h-screen overflow-hidden"
        style={{ marginLeft: "var(--sidebar-width)" }}
      >
        <main className="flex-1 overflow-y-auto">
          <div className="px-6 py-6 max-w-7xl mx-auto">{children}</div>
        </main>
      </div>
    </div>
  );
}
