import { useEffect, useState } from 'react';
import { Bot } from 'lucide-react';
import { api, apiErrorMessage } from '@/utils/api';
import type { User } from '@/types';
import { useAuthStore } from '@/stores/authStore';

interface DemoAccount {
  email: string;
  password: string;
  role: string;
  label: string;
}

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('expired')
      ? 'Your session expired. Please sign in again.'
      : ''
  );
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);
  const login = useAuthStore((state) => state.login);

  useEffect(() => {
    // Demo logins are only offered when the backend explicitly enables demo mode.
    api.get('/auth/config/')
      .then((res) => setDemoAccounts(res.data?.demo_accounts_enabled ? res.data.demo_accounts || [] : []))
      .catch(() => setDemoAccounts([]));
  }, []);

  const signIn = async (loginEmail: string, loginPassword: string) => {
    setIsLoading(true);
    setError('');

    try {
      const response = await api.post('/auth/login/', { email: loginEmail, password: loginPassword });
      const { access, refresh, user } = response.data as { access: string; refresh: string; user: User };
      login(access, user, refresh);
      window.location.href = '/dashboard';
    } catch (err: any) {
      if (err?.response?.status === 429) {
        setError('Too many sign-in attempts. Please wait a minute and try again.');
      } else {
        setError(apiErrorMessage(err, 'Login failed. Check your credentials.'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    signIn(email, password);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-4">
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-teal-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-teal-500 to-cyan-600 rounded-2xl mb-4 shadow-lg shadow-teal-500/30">
            <Bot className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">HeyJarvis</h1>
          <p className="text-slate-400 mt-2 text-sm">AI Dental Front Desk Platform</p>
        </div>

        <div className="bg-white/5 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/10 p-8">
          <div className="text-center mb-8">
            <h2 className="text-xl font-semibold text-white">Welcome back</h2>
            <p className="text-sm text-slate-400 mt-1">Sign in to your practice dashboard</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Email</label>
              <input
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500/50 text-sm transition-all"
                placeholder="name@practice.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Password</label>
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500/50 text-sm transition-all"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-sm text-red-400 bg-red-400/10 rounded-lg px-3 py-2">{error}</p>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gradient-to-r from-teal-500 to-cyan-600 text-white rounded-xl font-medium text-sm hover:from-teal-600 hover:to-cyan-700 transition-all shadow-lg shadow-teal-500/25 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <div className="animate-spin rounded-full h-5 w-5 border-2 border-white/30 border-t-white" />
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          {demoAccounts.length > 0 && (
            <div className="mt-6 pt-6 border-t border-white/10">
              <p className="text-xs text-slate-400 mb-3 text-center">Demo environment: one-click sign in</p>
              <div className="grid gap-2">
                {demoAccounts.map((acct) => (
                  <button
                    key={acct.email}
                    type="button"
                    disabled={isLoading}
                    onClick={() => signIn(acct.email, acct.password)}
                    className="w-full text-left px-4 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-sm text-slate-200 transition-all disabled:opacity-50"
                  >
                    <span className="font-medium">{acct.label}</span>
                    <span className="block text-xs text-slate-500">{acct.email}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-slate-600 mt-6">HeyJarvis — AI Dental Concierge Platform</p>
      </div>
    </div>
  );
}
