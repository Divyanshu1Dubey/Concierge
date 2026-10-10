import { useState, useEffect } from 'react';
import { X, User as UserIcon, Mail, Phone, ShieldCheck, Save } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { authApi } from '@/services/api';
import toast from 'react-hot-toast';

interface ProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function ProfileModal({ isOpen, onClose }: ProfileModalProps) {
  const { user, setUser } = useAuthStore();

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 8) {
      toast.error('New password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match.');
      return;
    }
    setIsChangingPassword(true);
    try {
      await authApi.changePassword({ old_password: oldPassword, new_password: newPassword, new_password_confirm: confirmPassword });
      toast.success('Password updated.');
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setShowPassword(false);
    } catch (err: any) {
      const data = err?.response?.data || {};
      toast.error(
        (Array.isArray(data.old_password) && data.old_password[0]) ||
        (Array.isArray(data.non_field_errors) && data.non_field_errors.join(' ')) ||
        (Array.isArray(data.new_password) && data.new_password.join(' ')) ||
        data.error || data.detail || 'Could not change password.'
      );
    } finally {
      setIsChangingPassword(false);
    }
  };

  useEffect(() => {
    if (user) {
      setFirstName(user.first_name || '');
      setLastName(user.last_name || '');
      setPhone(user.phone || '');
    }
  }, [user, isOpen]);

  if (!isOpen || !user) return null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firstName.trim()) {
      toast.error('First name cannot be empty');
      return;
    }

    setIsSaving(true);
    try {
      const updated = await authApi.updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim(),
      });
      setUser(updated);
      toast.success('Profile and name updated successfully!');
      onClose();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to update profile';
      toast.error(msg);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fade-in">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-md overflow-hidden animate-scale-up">
        {/* Header */}
        <div className="bg-gradient-to-r from-slate-900 to-slate-800 p-5 text-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-teal-500/20 border border-teal-400/30 flex items-center justify-center text-teal-300 font-bold text-lg">
              {(firstName || user.email || 'U')[0].toUpperCase()}
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Edit Profile & Account</h2>
              <p className="text-xs text-slate-300 truncate">{user.email}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSave} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-slate-600 block mb-1.5">
                First Name
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="e.g. Dr. Sarah"
                  className="w-full px-3 py-2 pl-9 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 font-medium text-slate-900"
                  required
                />
                <UserIcon className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              </div>
            </div>

            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-slate-600 block mb-1.5">
                Last Name
              </label>
              <input
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="e.g. Brody"
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 font-medium text-slate-900"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-slate-600 block mb-1.5">
              Direct Phone Number
            </label>
            <div className="relative">
              <input
                type="text"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="(919) 555-0199"
                className="w-full px-3 py-2 pl-9 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 font-medium text-slate-900"
              />
              <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            </div>
          </div>

          {/* Readonly Account Details */}
          <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3.5 space-y-2 text-xs">
            <div className="flex items-center justify-between text-slate-600">
              <span className="flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-slate-400" />
                Login Email
              </span>
              <span className="font-semibold text-slate-900">{user.email}</span>
            </div>

            <div className="flex items-center justify-between text-slate-600">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
                Account Role
              </span>
              <span className="font-bold px-2 py-0.5 rounded bg-teal-100 text-teal-800 text-[10px]">
                {user.role || 'PRACTICE_ADMIN'}
              </span>
            </div>

            {user.practice_name && (
              <div className="flex items-center justify-between text-slate-600">
                <span>Practice</span>
                <span className="font-semibold text-slate-900 truncate max-w-[200px]">
                  {user.practice_name}
                </span>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-slate-200 hover:bg-slate-50 text-slate-700 text-sm font-semibold rounded-xl transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="px-5 py-2 bg-gradient-to-r from-teal-600 to-cyan-600 hover:from-teal-700 hover:to-cyan-700 text-white text-sm font-bold rounded-xl shadow-md transition flex items-center gap-1.5 disabled:opacity-50"
            >
              {isSaving ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  Save Changes
                </>
              )}
            </button>
          </div>
        </form>

        <div className="px-6 pb-6 -mt-2">
          {!showPassword ? (
            <button
              type="button"
              onClick={() => setShowPassword(true)}
              className="text-[13px] font-medium text-forest-700 hover:text-forest-900 link-quiet"
            >
              Change password
            </button>
          ) : (
            <form onSubmit={handleChangePassword} className="space-y-3 pt-4 border-t border-slate-200">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Change password</p>
              <input type="password" autoComplete="current-password" required placeholder="Current password" aria-label="Current password"
                value={oldPassword} onChange={(e) => setOldPassword(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500" />
              <input type="password" autoComplete="new-password" required placeholder="New password (min. 8 characters)" aria-label="New password"
                value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500" />
              <input type="password" autoComplete="new-password" required placeholder="Confirm new password" aria-label="Confirm new password"
                value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500" />
              <div className="flex gap-2 justify-end">
                <button type="button" onClick={() => setShowPassword(false)} className="px-3 py-2 text-sm text-slate-600 hover:text-slate-900">Cancel</button>
                <button type="submit" disabled={isChangingPassword}
                  className="px-4 py-2 bg-forest-800 hover:bg-forest-900 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                  {isChangingPassword ? 'Updating…' : 'Update password'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
