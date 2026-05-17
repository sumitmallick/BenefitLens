"use client";

/**
 * AuthContext — JWT-based authentication with RBAC awareness.
 *
 * Roles: ADMIN | CLAIM_PROCESSOR | PATIENT | PROVIDER
 *
 * Token is stored in localStorage under TOKEN_KEY.
 * On mount, the stored token is validated against /api/v1/auth/me.
 */

import { createContext, useContext, useEffect, useState, ReactNode } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "claimsiq_auth_token";

export type UserRole = "ADMIN" | "CLAIM_PROCESSOR" | "PATIENT" | "PROVIDER";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  member_id?: string | null;
  provider_npi?: string | null;
  provider_name?: string | null;
  is_active: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  /** Called after register so both user+token land in context at once */
  setSession: (user: AuthUser, token: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Validate stored token on mount
  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
    if (!stored) {
      setIsLoading(false);
      return;
    }
    fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((userData: AuthUser | null) => {
        if (userData) {
          setToken(stored);
          setUser(userData);
        } else {
          localStorage.removeItem(TOKEN_KEY);
        }
      })
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const form = new URLSearchParams();
    form.append("username", email.trim().toLowerCase());
    form.append("password", password);

    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error((body as { detail?: string }).detail || "Login failed. Check your credentials.");
    }

    const data: { access_token: string; user: AuthUser } = await res.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    setToken(data.access_token);
    setUser(data.user);
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  };

  const setSession = (user: AuthUser, token: string) => {
    localStorage.setItem(TOKEN_KEY, token);
    setToken(token);
    setUser(user);
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, setSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

/** Convenience: read the stored token without React (for API calls). */
export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/** Role-based permission helpers */
export const can = {
  viewAllClaims: (role: UserRole) => role === "ADMIN" || role === "CLAIM_PROCESSOR",
  submitClaims: (role: UserRole) => role === "ADMIN" || role === "CLAIM_PROCESSOR" || role === "PROVIDER",
  manageMembersAndPolicies: (role: UserRole) => role === "ADMIN" || role === "CLAIM_PROCESSOR",
  resolveDisputes: (role: UserRole) => role === "ADMIN" || role === "CLAIM_PROCESSOR",
  manageUsers: (role: UserRole) => role === "ADMIN",
  viewStats: (role: UserRole) => role === "ADMIN" || role === "CLAIM_PROCESSOR",
};

export const ROLE_LABELS: Record<UserRole, string> = {
  ADMIN: "Administrator",
  CLAIM_PROCESSOR: "Claims Processor",
  PATIENT: "Patient",
  PROVIDER: "Healthcare Provider",
};

export const ROLE_COLORS: Record<UserRole, string> = {
  ADMIN: "bg-purple-100 text-purple-700 border-purple-200",
  CLAIM_PROCESSOR: "bg-blue-100 text-blue-700 border-blue-200",
  PATIENT: "bg-emerald-100 text-emerald-700 border-emerald-200",
  PROVIDER: "bg-amber-100 text-amber-700 border-amber-200",
};
