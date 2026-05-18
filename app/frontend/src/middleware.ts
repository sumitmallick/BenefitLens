/**
 * Next.js Edge Middleware — server-side route protection.
 *
 * Reads the `claimsiq_session` cookie set by auth.tsx on login.
 * If missing, redirects unauthenticated users to /login before
 * the page ever renders — eliminates the client-side flash of
 * protected content that LayoutShell alone can't prevent.
 *
 * Security note:
 *   This middleware only checks cookie *presence*, not JWT validity.
 *   The actual JWT signature is verified by the FastAPI backend on
 *   every API call. This is intentional: Edge runtime cannot load
 *   Node.js crypto to verify HMAC-SHA256 signatures. The middleware
 *   is a UX guard, not a security boundary.
 *
 * Auth pages (/login, /register) and static assets are always allowed.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always allow auth pages and API routes
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const sessionCookie = request.cookies.get("claimsiq_session");

  if (!sessionCookie) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    // Preserve the original destination so we can redirect back after login
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Run on all routes except Next.js internals and static files
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|icon|logo\\.svg|.*\\.png$).*)",
  ],
};
