"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  getTeamMembers,
  inviteTeamMember,
  removeTeamMember,
  type TeamMemberItem,
  type TeamMembersResponse,
} from "@/lib/api";

const ROLE_BADGE: Record<string, string> = {
  owner: "bg-yellow-600/60 text-yellow-200",
  admin: "bg-purple-700/60 text-purple-200",
  member: "bg-gray-700 text-gray-300",
};

function getInitials(email: string): string {
  return email.slice(0, 2).toUpperCase();
}

export default function TeamPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [teamData, setTeamData] = useState<TeamMembersResponse | null>(null);
  const [loadingTeam, setLoadingTeam] = useState(true);
  const [teamError, setTeamError] = useState<string | null>(null);

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"member" | "admin">("member");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteMsg, setInviteMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Remove
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removeMsg, setRemoveMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.push("/login");
  }, [authLoading, user, router]);

  const loadTeam = useCallback(() => {
    setTeamError(null);
    getTeamMembers()
      .then(setTeamData)
      .catch((e: Error) => setTeamError(e.message))
      .finally(() => setLoadingTeam(false));
  }, []);

  useEffect(() => {
    if (user && user.plan === "business") {
      loadTeam();
    } else if (user) {
      setLoadingTeam(false);
    }
  }, [user, loadTeam]);

  if (authLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950">
        <div className="text-purple-400 animate-pulse text-xl">Loading...</div>
      </div>
    );
  }

  // Not on business plan
  if (user.plan !== "business") {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center px-6">
        <div className="max-w-md w-full text-center bg-gray-900 border border-gray-800 rounded-2xl p-10">
          <div className="text-5xl mb-4">👥</div>
          <h1 className="text-2xl font-bold text-white mb-3">Team Seats</h1>
          <p className="text-gray-400 mb-6">
            Team management is available on the{" "}
            <span className="text-yellow-400 font-semibold">Business plan</span>. Upgrade to invite
            team members and manage access.
          </p>
          <Link
            href="/dashboard/billing"
            className="inline-block bg-purple-600 hover:bg-purple-500 text-white font-bold px-6 py-3 rounded-xl transition"
          >
            Upgrade to Business →
          </Link>
          <div className="mt-4">
            <Link href="/dashboard" className="text-sm text-gray-500 hover:text-gray-300 transition">
              ← Back to Dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviteLoading(true);
    setInviteMsg(null);
    try {
      await inviteTeamMember(inviteEmail.trim(), inviteRole);
      setInviteMsg({ type: "success", text: `Invitation sent to ${inviteEmail.trim()}.` });
      setInviteEmail("");
      setInviteRole("member");
      loadTeam();
    } catch (err: unknown) {
      setInviteMsg({ type: "error", text: (err as Error).message });
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRemove = async (member: TeamMemberItem) => {
    setRemovingId(member.id);
    setRemoveMsg(null);
    try {
      await removeTeamMember(member.id);
      setRemoveMsg({ type: "success", text: `${member.email} removed from team.` });
      loadTeam();
    } catch (err: unknown) {
      setRemoveMsg({ type: "error", text: (err as Error).message });
    } finally {
      setRemovingId(null);
    }
  };

  const seatsUsed = teamData?.seats_used ?? 0;
  const seatsLimit = teamData?.seats_limit ?? 25;
  const members = teamData?.members ?? [];

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-purple-400 font-bold text-xl">
              ⚡ KT OS
            </Link>
            <span className="text-gray-600">|</span>
            <span className="text-sm text-gray-400">Team</span>
          </div>
          <Link href="/dashboard" className="text-sm text-gray-500 hover:text-gray-300 transition">
            ← Dashboard
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10">
        {/* Title + Seats count */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Team Members</h1>
            <p className="text-sm text-gray-500 mt-1">
              Manage who has access to your workspace.
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-2 text-center">
            <div className="text-xl font-bold text-white">
              {seatsUsed}
              <span className="text-gray-500 font-normal text-sm"> / {seatsLimit}</span>
            </div>
            <div className="text-xs text-gray-500">seats</div>
          </div>
        </div>

        {teamError && (
          <div className="bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg px-4 py-3 mb-6">
            {teamError}
          </div>
        )}

        {/* Invite Form */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-6">
          <h2 className="text-sm font-semibold text-gray-400 uppercase mb-4">Invite Member</h2>
          <form onSubmit={handleInvite} className="flex flex-col sm:flex-row gap-3">
            <input
              type="email"
              required
              placeholder="colleague@company.com"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              className="flex-1 bg-gray-800 border border-gray-700 text-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-purple-600"
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as "member" | "admin")}
              className="bg-gray-800 border border-gray-700 text-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-purple-600"
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <button
              type="submit"
              disabled={inviteLoading}
              className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg px-5 py-2 transition whitespace-nowrap"
            >
              {inviteLoading ? "Sending…" : "Send Invite"}
            </button>
          </form>
          {inviteMsg && (
            <p
              className={`text-sm mt-3 ${
                inviteMsg.type === "success" ? "text-green-400" : "text-red-400"
              }`}
            >
              {inviteMsg.text}
            </p>
          )}
        </div>

        {/* Remove feedback */}
        {removeMsg && (
          <div
            className={`mb-4 text-sm px-4 py-3 rounded-lg border ${
              removeMsg.type === "success"
                ? "bg-green-900/30 border-green-700/50 text-green-400"
                : "bg-red-900/30 border-red-700/50 text-red-400"
            }`}
          >
            {removeMsg.text}
          </div>
        )}

        {/* Members Table */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-left">
                <th className="px-4 py-3 text-gray-500 font-medium">Member</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Role</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Status</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Invited</th>
                <th className="px-4 py-3 text-gray-500 font-medium" />
              </tr>
            </thead>
            <tbody>
              {loadingTeam ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-gray-500 animate-pulse">
                    Loading team...
                  </td>
                </tr>
              ) : members.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-gray-500">
                    No team members yet. Invite someone above.
                  </td>
                </tr>
              ) : (
                members.map((m) => (
                  <tr key={m.id} className="border-b border-gray-800/50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-purple-800 flex items-center justify-center text-xs font-bold text-purple-100 shrink-0">
                          {getInitials(m.email)}
                        </div>
                        <span className="text-gray-200">{m.email}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          ROLE_BADGE[m.role] ?? "bg-gray-700 text-gray-300"
                        }`}
                      >
                        {m.role}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          m.accepted
                            ? "bg-green-900/40 text-green-400"
                            : "bg-yellow-900/40 text-yellow-400"
                        }`}
                      >
                        {m.accepted ? "accepted" : "pending"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(m.invited_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleRemove(m)}
                        disabled={removingId === m.id}
                        className="text-xs text-red-400 hover:text-red-300 disabled:opacity-40 transition"
                      >
                        {removingId === m.id ? "Removing…" : "Remove"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
