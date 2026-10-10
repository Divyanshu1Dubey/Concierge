import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { authApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      await authApi.requestPasswordReset(email.trim());
      setSent(true);
    } catch (err: any) {
      setError(err?.response?.status === 429
        ? 'Too many requests. Please wait a little and try again.'
        : apiErrorMessage(err, 'Could not send the reset email. Please try again.'));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center px-5 py-12">
      <div className="w-full max-w-[400px] animate-rise">
        <Link to="/" className="flex items-center gap-2.5 mb-10 w-fit" aria-label="HeyJarvis Concierge home">
          <span className="w-9 h-9 rounded-[10px] bg-forest-800 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-forest-100" aria-hidden="true" />
          </span>
          <span className="font-display text-[19px] text-forest-900">HeyJarvis Concierge</span>
        </Link>

        <h1 className="text-[32px] leading-tight font-normal text-forest-900">Reset your password</h1>
        {sent ? (
          <div className="mt-6 space-y-4" role="status">
            <p className="text-[15px] text-stone-700 leading-relaxed">
              If an account exists for <strong>{email}</strong>, we've emailed a link to set a new password.
              The link expires in a few days and can be used once.
            </p>
            <p className="text-[13.5px] text-stone-500">Didn't get it? Check your spam folder, or ask your practice administrator to send a new link.</p>
            <Link to="/login" className="inline-block text-[14px] font-medium text-forest-800 link-quiet">Back to sign in</Link>
          </div>
        ) : (
          <>
            <p className="text-[15px] text-stone-600 mt-2">Enter your work email and we'll send you a reset link.</p>
            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              <div>
                <label htmlFor="reset-email" className="block text-[13px] font-medium text-stone-700 mb-1.5">Email</label>
                <input
                  id="reset-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@practice.com"
                  className="w-full px-4 py-3 bg-white border border-stone-300 rounded-xl text-[15px] text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 transition"
                />
              </div>
              {error && (
                <p role="alert" className="text-[13.5px] text-red-800 bg-red-50 border border-red-200 rounded-xl px-3.5 py-2.5">{error}</p>
              )}
              <button
                type="submit"
                disabled={isLoading}
                className="w-full px-4 py-3 bg-forest-800 hover:bg-forest-900 text-white rounded-full font-medium text-[15px] transition-colors disabled:opacity-60"
              >
                {isLoading ? 'Sending…' : 'Send reset link'}
              </button>
            </form>
            <p className="mt-8 text-[13.5px] text-stone-500">
              Remembered it? <Link to="/login" className="link-quiet text-forest-800">Back to sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
