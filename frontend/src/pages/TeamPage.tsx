import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { practicesApi } from '@/services/api';
import {
  Users, UserPlus, Trash2, Mail
} from 'lucide-react';

export default function TeamPage() {
  const queryClient = useQueryClient();
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviteFirstName, setInviteFirstName] = useState('');
  const [inviteLastName, setInviteLastName] = useState('');

  // Fetch team
  const { data: teamData, isLoading } = useQuery({
    queryKey: ['team'],
    queryFn: () => practicesApi.team(),
  });

  const members: any[] = teamData?.team || [];

  // Mutations
  const inviteMutation = useMutation({
    mutationFn: () =>
      practicesApi.inviteMember({
        email: inviteEmail,
        role: inviteRole,
        first_name: inviteFirstName,
        last_name: inviteLastName,
      }),
    onSuccess: () => {
      setShowInviteModal(false);
      setInviteEmail('');
      setInviteFirstName('');
      setInviteLastName('');
      queryClient.invalidateQueries({ queryKey: ['team'] });
    },
  });

  const updateRoleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) =>
      practicesApi.updateMemberRole(id, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team'] });
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: (id: string) => practicesApi.removeMember(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team'] });
    },
  });

  const getRoleBadge = (role: string) => {
    const r = (role || 'member').toLowerCase();
    const badges: Record<string, { color: string; label: string }> = {
      owner: { color: 'bg-purple-100 text-purple-800', label: 'Owner (Full Access)' },
      admin: { color: 'bg-blue-100 text-blue-800', label: 'Admin (Config & Ops)' },
      member: { color: 'bg-teal-100 text-teal-800', label: 'Member (Front Desk & Leads)' },
      viewer: { color: 'bg-gray-100 text-gray-700', label: 'Viewer (Read Only)' },
    };
    return badges[r] || badges.member;
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Team & Role Permissions</h1>
          <p className="text-gray-500 mt-1">Manage staff accounts, assign front desk members, and control access levels.</p>
        </div>
        <button
          onClick={() => setShowInviteModal(true)}
          className="flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-sm font-semibold transition shadow-sm"
        >
          <UserPlus className="w-4 h-4" />
          Invite Team Member
        </button>
      </div>

      {/* Role Definitions Guide Card */}
      <div className="grid sm:grid-cols-4 gap-3 text-xs">
        <div className="p-3 bg-purple-50/50 border border-purple-100 rounded-xl">
          <span className="font-bold text-purple-900 block mb-1">OWNER</span>
          <p className="text-purple-700">Full control over tenant, billing, key regeneration, and team.</p>
        </div>
        <div className="p-3 bg-blue-50/50 border border-blue-100 rounded-xl">
          <span className="font-bold text-blue-900 block mb-1">ADMIN</span>
          <p className="text-blue-700">Operations, business rules, widget appearance, SMTP configuration.</p>
        </div>
        <div className="p-3 bg-teal-50/50 border border-teal-100 rounded-xl">
          <span className="font-bold text-teal-900 block mb-1">MEMBER</span>
          <p className="text-teal-700">Front desk triage, response drafting, conversations, and leads.</p>
        </div>
        <div className="p-3 bg-gray-50 border border-gray-200 rounded-xl">
          <span className="font-bold text-gray-900 block mb-1">VIEWER</span>
          <p className="text-gray-600">Read-only visibility for reporting, audits, and performance metrics.</p>
        </div>
      </div>

      {/* Team Members Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
            <Users className="w-5 h-5 text-teal-600" />
            Active Team Members ({members.length})
          </h2>
        </div>

        {isLoading ? (
          <div className="p-12 text-center text-gray-400 text-sm">Loading staff members...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Staff Name</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Email</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Role</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {members.map((m: any) => {
                  const badge = getRoleBadge(m.role);
                  return (
                    <tr key={m.id} className="hover:bg-gray-50 transition">
                      <td className="px-6 py-4 text-sm font-semibold text-gray-900">
                        {m.first_name || m.last_name ? `${m.first_name || ''} ${m.last_name || ''}`.trim() : 'Staff Member'}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-600 font-mono text-xs">{m.email}</td>
                      <td className="px-6 py-4">
                        <select
                          value={m.role}
                          onChange={(e) => updateRoleMutation.mutate({ id: m.id, role: e.target.value })}
                          className={`text-xs font-bold px-2.5 py-1 rounded-full border border-gray-200 focus:outline-none ${badge.color}`}
                        >
                          <option value="owner">Owner</option>
                          <option value="admin">Admin</option>
                          <option value="member">Member</option>
                          <option value="viewer">Viewer</option>
                        </select>
                      </td>
                      <td className="px-6 py-4 text-right">
                        {m.role !== 'owner' && (
                          <button
                            onClick={() => removeMemberMutation.mutate(m.id)}
                            className="text-red-500 hover:text-red-700 p-1"
                            title="Remove Member"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Invite Member Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center gap-2">
              <Mail className="w-5 h-5 text-teal-600" />
              <h3 className="text-lg font-bold text-gray-900">Invite Team Member</h3>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">First Name</label>
                <input
                  type="text"
                  value={inviteFirstName}
                  onChange={(e) => setInviteFirstName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Last Name</label>
                <input
                  type="text"
                  value={inviteLastName}
                  onChange={(e) => setInviteLastName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                />
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Email Address</label>
              <input
                type="email"
                placeholder="colleague@raleighdentistry.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Assigned Role</label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
              >
                <option value="member">Member (Front Desk staff)</option>
                <option value="admin">Admin (Configuration & Settings)</option>
                <option value="viewer">Viewer (Read-only)</option>
                <option value="owner">Owner (Full tenant access)</option>
              </select>
            </div>

            <div className="flex justify-end gap-3 pt-3">
              <button
                onClick={() => setShowInviteModal(false)}
                className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-semibold text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => inviteMutation.mutate()}
                disabled={!inviteEmail || inviteMutation.isPending}
                className="px-5 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50"
              >
                {inviteMutation.isPending ? 'Sending Invite...' : 'Send Invitation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
