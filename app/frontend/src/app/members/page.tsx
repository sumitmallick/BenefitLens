"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { membersApi, type Member } from "@/lib/api";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ErrorAlert } from "@/components/ErrorAlert";

function MemberRow({ member }: { member: Member }) {
  const initials = member.name
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <tr>
      <td>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold flex-shrink-0">
            {initials}
          </div>
          <div>
            <p className="font-semibold text-slate-800">{member.name}</p>
            <p className="text-xs text-slate-400 font-mono">{member.member_id}</p>
          </div>
        </div>
      </td>
      <td>
        <code className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
          {member.id.slice(0, 8)}…
        </code>
      </td>
      <td>
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          Active
        </span>
      </td>
      <td>
        <div className="flex items-center gap-2">
          <Link
            href={`/claims/new?member_id=${member.id}`}
            className="text-xs font-semibold text-blue-600 hover:text-blue-700"
          >
            Submit Claim
          </Link>
          <span className="text-slate-300">|</span>
          <Link
            href={`/claims?member_id=${member.id}`}
            className="text-xs font-semibold text-slate-500 hover:text-slate-700"
          >
            View Claims
          </Link>
        </div>
      </td>
    </tr>
  );
}

export default function MembersPage() {
  const [search, setSearch] = useState("");

  const { data: members, isLoading, error } = useQuery({
    queryKey: ["members"],
    queryFn: () => membersApi.list({ limit: 100 }),
  });

  const filtered = members?.filter((m) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return m.name.toLowerCase().includes(q) || m.member_id.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Member Registry</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {members ? `${members.length} registered members` : "Manage enrolled members"}
          </p>
        </div>
        <Link href="/members/new" className="btn-primary">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
          Register Member
        </Link>
      </div>

      {/* Search */}
      <div className="card p-4">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            className="input pl-10"
            placeholder="Search by member name or ID…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="card p-8">
          <LoadingSpinner message="Loading member registry…" />
        </div>
      ) : error ? (
        <ErrorAlert error={error} title="Failed to load members" />
      ) : filtered && filtered.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>System ID</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((m) => (
                  <MemberRow key={m.id} member={m} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-12 text-center">
          <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <p className="text-base font-semibold text-slate-700 mb-1">
            {search ? "No members match your search" : "No members registered"}
          </p>
          <p className="text-sm text-slate-500 mb-6">
            {search
              ? "Try adjusting your search term."
              : "Register the first member to start processing claims."}
          </p>
          {!search && (
            <Link href="/members/new" className="btn-primary">Register First Member</Link>
          )}
        </div>
      )}
    </div>
  );
}
