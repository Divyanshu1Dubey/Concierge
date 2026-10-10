import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { authApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const uid = params.get('uid') || '';
  const token = params.get('token') || '';
  const isInvite = params.get('invite') === '1';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) return setError('Use at least 8 characters.');
    if (password !== confirm) return setError('The passwords do not match.');
    setIsLoading(true);
    try {
      await authApi.confirmPasswordReset({ uid, token, new_password: password, new_password_confirm: confirm });
      setDone(true);
    } catch (err) {
      setError(apiErrorMessage(err, 'This link is invalid or has expired.'));
    } finally {
      setIsLoading(false);
    }
  };

  const inputClass =
    'w-full px-4 py-3 bg-white border border-stone-300 rounded-xl text-[15px] text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 transition';

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center px-5 py-12">
      <div className="w-full max-w-[400px] animate-rise">
        <Link to="/" className="flex items-center gap-2.5 mb-10 w-fit" aria-label="HeyJarvis Concierge home">
          <span className="w-9 h-9 rounded-[10px] bg-forest-800 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-forest-100" aria-hidden="true" />
          </span>
          <span className="font-display text-[19px] text-forest-900">HeyJarvis Concierge</span>
        </Link>

        <h1 className="text-[32px] leading-tight font-normal text-forest-900">
          {isInvite ? 'Set up your account' : 'Choose a new password'}
        </h1>

        {!uid || !token ? (
          <div className="mt-6 space-y-4">
            <p className="text-[15px] text-stone-700">This link is incomplete. Please use the full link from your email.</p>
            <Link to="/forgot-password" className="text-[14px] font-medium text-forest-800 link-quiet">Request a new link</Link>
          </div>
        ) : done ? (
          <div className="mt-6 space-y-4" role="status">
            <p className="text-[15px] text-stone-700">Your password has been set. You can now sign in.</p>
            <Link
              to="/login"
              className="inline-flex px-5 py-2.5 bg-forest-800 hover:bg-forest-900 text-white rounded-full text-[14px] font-medium transition-colors"
            >
              Sign in
            </Link>
          </div>
        ) : (
          <>
            <p className="text-[15px] text-stone-600 mt-2">
              {isInvite ? 'Create a password to access your practice dashboard.' : 'Enter a new password for your account.'}
            </p>
            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              <div>
                <label htmlFor="new-password" className="block text-[13px] font-medium text-stone-700 mb-1.5">New password</label>
                <input id="new-password" type="password" autoComplete="new-password" required value={password}
                  onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" className={inputClass} />
              </div>
              <div>
                <label htmlFor="confirm-password" className="block text-[13px] font-medium text-stone-700 mb-1.5">Confirm password</label>
                <input id="confirm-password" type="password" autoComplete="new-password" required value={confirm}
                  onChange={(e) => setConfirm(e.target.value)} className={inputClass} />
              </div>
              <p className="text-[12.5px] text-stone-500">Avoid common passwords and anything based on your name or email.</p>
              {error && (
                <p role="alert" className="text-[13.5px] text-red-800 bg-red-50 border border-red-200 rounded-xl px-3.5 py-2.5">{error}</p>
              )}
              <button type="submit" disabled={isLoading}
                className="w-full px-4 py-3 bg-forest-800 hover:bg-forest-900 text-white rounded-full font-medium text-[15px] transition-colors disabled:opacity-60">
                {isLoading ? 'Saving…' : isInvite ? 'Create password' : 'Set new password'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
