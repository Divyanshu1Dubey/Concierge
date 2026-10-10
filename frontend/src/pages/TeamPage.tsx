import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { practicesApi } from '@/services/api';
import { apiErrorMessage, asList } from '@/utils/api';
import { useAuthStore } from '@/stores/authStore';
import {
  Users, UserPlus, Trash2, Mail, KeyRound, Copy
} from 'lucide-react';

const ROLE_OPTIONS = [
  { value: 'PRACTICE_ADMIN', label: 'Practice Admin' },
  { value: 'FRONT_DESK', label: 'Front Desk' },
];

const normalizeRole = (role: string) => {
  const r = (role || '').toUpperCase();
  if (r === 'AGENCY_ADMIN') return 'AGENCY_ADMIN';
  if (['PRACTICE_ADMIN', 'ADMIN', 'OWNER'].includes(r)) return 'PRACTICE_ADMIN';
  return 'FRONT_DESK';
};

const ROLE_BADGES: Record<string, string> = {
  AGENCY_ADMIN: 'bg-purple-100 text-purple-800',
  PRACTICE_ADMIN: 'bg-blue-100 text-blue-800',
  FRONT_DESK: 'bg-teal-100 text-teal-800',
};

export default function TeamPage() {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('FRONT_DESK');
  const [inviteFirstName, setInviteFirstName] = useState('');
  const [inviteLastName, setInviteLastName] = useState('');
  const [invitePassword, setInvitePassword] = useState('');
  const [tempCredential, setTempCredential] = useState<{ email: string; password: string } | null>(null);
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);

  const { data: teamData, isLoading, isError } = useQuery({
    queryKey: ['team'],
    queryFn: () => practicesApi.team(),
  });

  const members: any[] = asList(teamData);

  const resetInvite = () => {
    setShowInviteModal(false);
    setInviteEmail('');
    setInviteFirstName('');
    setInviteLastName('');
    setInvitePassword('');
    setInviteRole('FRONT_DESK');
  };

  const inviteMutation = useMutation({
    mutationFn: () =>
      practicesApi.inviteMember({
        email: inviteEmail.trim(),
        role: inviteRole,
        first_name: inviteFirstName.trim(),
        last_name: inviteLastName.trim(),
        ...(invitePassword ? { password: invitePassword } : {}),
      }),
    onSuccess: (data: any) => {
      if (data?.temporary_password) {
        // The invite email could not be sent; the admin shares this one-time password instead.
        setTempCredential({ email: data.email, password: data.temporary_password });
      } else if (data?.invite_sent) {
        toast.success(`Invite email sent to ${data.email}`);
      } else {
        toast.success(`Account created for ${data?.email || inviteEmail}`);
      }
      resetInvite();
      queryClient.invalidateQueries({ queryKey: ['team'] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not create the team member.')),
  });

  const updateRoleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) => practicesApi.updateMemberRole(id, role),
    onSuccess: () => {
      toast.success('Role updated');
      queryClient.invalidateQueries({ queryKey: ['team'] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not update role.')),
  });

  const resetLinkMutation = useMutation({
    mutationFn: (memberId: string) =>
      practicesApi.practiceUserAction(String(currentUser?.practice ?? ''), memberId, 'send_password_link'),
    onSuccess: (res: any) => toast.success(res?.message || 'Password link sent'),
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not send the password link.')),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (id: string) => practicesApi.removeMember(id),
    onSuccess: () => {
      toast.success('Team member deactivated');
      setConfirmRemoveId(null);
      queryClient.invalidateQueries({ queryKey: ['team'] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not remove team member.')),
  });

  const handleInvite = () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(inviteEmail.trim())) {
      toast.error('Enter a valid email address.');
      return;
    }
    if (invitePassword && invitePassword.length < 8) {
      toast.error('Password must be at least 8 characters.');
      return;
    }
    inviteMutation.mutate();
  };

  return (
    <div className="space-y-6 max-w-5xl">
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
          Add Team Member
        </button>
      </div>

      <div className="grid sm:grid-cols-2 gap-3 text-xs">
        <div className="p-3 bg-blue-50/50 border border-blue-100 rounded-xl">
          <span className="font-bold text-blue-900 block mb-1">PRACTICE ADMIN</span>
          <p className="text-blue-700">Practice settings, business rules, widget, email delivery, templates, team and security.</p>
        </div>
        <div className="p-3 bg-teal-50/50 border border-teal-100 rounded-xl">
          <span className="font-bold text-teal-900 block mb-1">FRONT DESK</span>
          <p className="text-teal-700">Request inbox, conversations, patient replies and internal notes.</p>
        </div>
      </div>

      {tempCredential && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-900 space-y-2">
          <div className="flex items-center gap-2 font-semibold">
            <KeyRound className="w-4 h-4" />
            Temporary password for {tempCredential.email}
          </div>
          <p className="text-xs">The invite email could not be sent, so here is a one-time password. It is shown only once: share it securely and ask them to change it after signing in.</p>
          <div className="flex items-center gap-2">
            <code className="px-2 py-1 bg-white border border-amber-200 rounded font-mono">{tempCredential.password}</code>
            <button
              onClick={() => navigator.clipboard.writeText(tempCredential.password).then(() => toast.success('Copied'), () => toast.error('Copy failed'))}
              className="p-1.5 rounded hover:bg-amber-100"
              title="Copy"
            >
              <Copy className="w-4 h-4" />
            </button>
            <button onClick={() => setTempCredential(null)} className="ml-auto text-xs underline">Dismiss</button>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
            <Users className="w-5 h-5 text-teal-600" />
            Team Members ({members.length})
          </h2>
        </div>

        {isLoading ? (
          <div className="p-12 text-center text-gray-400 text-sm">Loading staff members...</div>
        ) : isError ? (
          <div className="p-12 text-center text-red-600 text-sm">Could not load the team. Please refresh.</div>
        ) : members.length === 0 ? (
          <div className="p-12 text-center text-gray-400 text-sm">No team members yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Staff Name</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Email</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Role</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {members.map((m: any) => {
                  const role = normalizeRole(m.role);
                  const isSelf = currentUser?.id === m.id;
                  const locked = isSelf || role === 'AGENCY_ADMIN';
                  return (
                    <tr key={m.id} className="hover:bg-gray-50 transition">
                      <td className="px-6 py-4 text-sm font-semibold text-gray-900">
                        {`${m.first_name || ''} ${m.last_name || ''}`.trim() || 'Staff Member'}
                        {isSelf && <span className="ml-2 text-xs text-gray-400">(you)</span>}
                      </td>
                      <td className="px-6 py-4 text-gray-600 font-mono text-xs">{m.email}</td>
                      <td className="px-6 py-4">
                        {locked ? (
                          <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${ROLE_BADGES[role]}`}>
                            {role === 'AGENCY_ADMIN' ? 'Agency Admin' : ROLE_OPTIONS.find((o) => o.value === role)?.label}
                          </span>
                        ) : (
                          <select
                            value={role}
                            disabled={updateRoleMutation.isPending}
                            onChange={(e) => updateRoleMutation.mutate({ id: m.id, role: e.target.value })}
                            className={`text-xs font-bold px-2.5 py-1 rounded-full border border-gray-200 focus:outline-none ${ROLE_BADGES[role]}`}
                          >
                            {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                          </select>
                        )}
                      </td>
                      <td className="px-6 py-4 text-xs">
                        {m.is_active ? <span className="text-emerald-700">Active</span> : <span className="text-gray-400">Deactivated</span>}
                      </td>
                      <td className="px-6 py-4 text-right whitespace-nowrap">
                        {!locked && m.is_active && currentUser?.practice && (
                          <button
                            onClick={() => resetLinkMutation.mutate(m.id)}
                            disabled={resetLinkMutation.isPending}
                            className="mr-2 text-xs font-medium text-teal-700 hover:text-teal-900 link-quiet"
                            title="Email a password reset link"
                          >
                            Send reset link
                          </button>
                        )}
                        {!locked && m.is_active && (
                          confirmRemoveId === m.id ? (
                            <span className="inline-flex items-center gap-2 text-xs">
                              <button
                                onClick={() => removeMemberMutation.mutate(m.id)}
                                disabled={removeMemberMutation.isPending}
                                className="px-2 py-1 bg-red-600 text-white rounded"
                              >
                                Confirm
                              </button>
                              <button onClick={() => setConfirmRemoveId(null)} className="px-2 py-1 border rounded">Cancel</button>
                            </span>
                          ) : (
                            <button
                              onClick={() => setConfirmRemoveId(m.id)}
                              className="text-red-500 hover:text-red-700 p-1"
                              title="Deactivate member"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )
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

      {showInviteModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center gap-2">
              <Mail className="w-5 h-5 text-teal-600" />
              <h3 className="text-lg font-bold text-gray-900">Add Team Member</h3>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">First Name</label>
                <input type="text" value={inviteFirstName} onChange={(e) => setInviteFirstName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Last Name</label>
                <input type="text" value={inviteLastName} onChange={(e) => setInviteLastName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Email Address (login)</label>
              <input type="email" placeholder="colleague@yourpractice.com" value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Initial Password <span className="font-normal text-gray-400">(optional; leave blank to email an invite link)</span></label>
              <input type="password" autoComplete="new-password" value={invitePassword}
                onChange={(e) => setInvitePassword(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Role</label>
              <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
                {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>

            <div className="flex justify-end gap-3 pt-3">
              <button onClick={resetInvite}
                className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-semibold text-gray-700 hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleInvite} disabled={!inviteEmail || inviteMutation.isPending}
                className="px-5 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50">
                {inviteMutation.isPending ? 'Sending…' : invitePassword ? 'Create Account' : 'Send Invite'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
