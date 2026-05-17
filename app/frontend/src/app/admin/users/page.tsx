"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { authApi, type AuthUser } from "@/lib/api";
import { useAuth, ROLE_LABELS, ROLE_COLORS, type UserRole } from "@/lib/auth";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ErrorAlert } from "@/components/ErrorAlert";
import { useRouter } from "next/navigation";

const ALL_ROLES: UserRole[] = ["ADMIN", "CLAIM_PROCESSOR", "PATIENT", "PROVIDER"];

export default function UsersPage() {
  const { user } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("All");
  const [pendingRole, setPendingRole] = useState<{ userId: string; role: string } | null>(null);

  // Redirect non-admins
  if (user && user.role !== "ADMIN") {
    router.replace("/");
    return null;
  }

  const { data: users, isLoading, error } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => authApi.listUsers(),
  });

  const roleUpdateMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      authApi.updateRole(userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      setPendingRole(null);
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: (userId: string) => authApi.deactivateUser(userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const filtered = users?.filter((u) => {
    if (roleFilter !== "All" && u.role !== roleFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">User Management</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {users ? `${users.length} platform users` : "Manage user accounts and roles"}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="card p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          {["All", ...ALL_ROLES].map((r) => (
            <button
              key={r}
              onClick={() => setRoleFilter(r)}
              className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-all duration-150 ${
                roleFilter === r
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}
            >
              {r === "All" ? "All Roles" : ROLE_LABELS[r as UserRole]}
              {r !== "All" && users && (
                <span className="ml-1.5 opacity-70">
                  ({users.filter((u) => u.role === r).length})
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
            fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            className="input pl-10"
            placeholder="Search by name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="card p-8"><LoadingSpinner message="Loading users…" /></div>
      ) : error ? (
        <ErrorAlert error={error} title="Failed to load users" />
      ) : filtered && filtered.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Linked Entity</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold flex-shrink-0">
                          {u.full_name.split(" ").map((n) => n[0]).slice(0, 2).join("").toUpperCase()}
                        </div>
                        <div>
                          <p className="font-semibold text-slate-800 text-sm">{u.full_name}</p>
                          <p className="text-xs text-slate-400">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td>
                      {pendingRole?.userId === u.id ? (
                        <div className="flex items-center gap-2">
                          <select
                            className="input py-1 text-xs"
                            defaultValue={u.role}
                            onChange={(e) => setPendingRole({ userId: u.id, role: e.target.value })}
                          >
                            {ALL_ROLES.map((r) => (
                              <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                            ))}
                          </select>
                          <button
                            onClick={() => roleUpdateMutation.mutate(pendingRole)}
                            disabled={roleUpdateMutation.isPending}
                            className="text-xs font-semibold text-emerald-600 hover:text-emerald-700"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setPendingRole(null)}
                            className="text-xs font-semibold text-slate-400 hover:text-slate-600"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${ROLE_COLORS[u.role as UserRole]}`}>
                          {ROLE_LABELS[u.role as UserRole]}
                        </span>
                      )}
                    </td>
                    <td>
                      <div className="text-xs text-slate-500">
                        {u.member_id && (
                          <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded">
                            Member: {u.member_id.slice(0, 8)}…
                          </span>
                        )}
                        {u.provider_npi && (
                          <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded">
                            NPI: {u.provider_npi}
                          </span>
                        )}
                        {!u.member_id && !u.provider_npi && (
                          <span className="text-slate-400">—</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${
                        u.is_active
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-slate-100 text-slate-500 border border-slate-200"
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? "bg-emerald-500" : "bg-slate-400"}`} />
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center gap-3">
                        {u.id !== user?.id && (
                          <>
                            <button
                              onClick={() => setPendingRole({ userId: u.id, role: u.role })}
                              className="text-xs font-semibold text-blue-600 hover:text-blue-700"
                            >
                              Change Role
                            </button>
                            {u.is_active && (
                              <>
                                <span className="text-slate-300">|</span>
                                <button
                                  onClick={() => {
                                    if (confirm(`Deactivate ${u.full_name}?`)) {
                                      deactivateMutation.mutate(u.id);
                                    }
                                  }}
                                  className="text-xs font-semibold text-red-500 hover:text-red-700"
                                >
                                  Deactivate
                                </button>
                              </>
                            )}
                          </>
                        )}
                        {u.id === user?.id && (
                          <span className="text-xs text-slate-400">You</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <p className="text-sm font-semibold text-slate-700 mb-1">No users found</p>
          <p className="text-xs text-slate-400">Adjust your filters to see users.</p>
        </div>
      )}
    </div>
  );
}
