import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Eye, EyeOff, Sparkles, Check, ArrowRight } from 'lucide-react';
import { api, apiErrorMessage } from '@/utils/api';
import type { User } from '@/types';
import { useAuthStore } from '@/stores/authStore';

const DEMO_LOGINS = [
  {
    role: 'Agency Admin',
    email: 'divyanshu@heyjarvis.ai',
    password: 'avisirheyjarvis2026',
    description: 'Every practice, onboarding, access requests',
    badge: 'Superuser',
    badgeColor: 'bg-purple-100 text-purple-800 border-purple-200',
  },
  {
    role: 'Doctor (Practice Admin)',
    email: 'doctor@heyjarvis-demo.com',
    password: 'DemoDoctor#2026',
    description: '"HeyJarvis Demo Dental": settings, team, requests',
    badge: 'Demo Dental',
    badgeColor: 'bg-teal-100 text-teal-800 border-teal-200',
  },
  {
    role: 'Front Desk',
    email: 'frontdesk@heyjarvis-demo.com',
    password: 'DemoFrontDesk#2026',
    description: 'Requests, conversations, replies',
    badge: 'Care Staff',
    badgeColor: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  },
];

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(() => {
    if (typeof window === 'undefined') return '';
    const params = new URLSearchParams(window.location.search);
    if (params.get('suspended')) return 'Your practice account is suspended. Please contact your HeyJarvis administrator.';
    if (params.get('expired')) return 'Your session expired. Please sign in again.';
    return '';
  });
  const [showPassword, setShowPassword] = useState(false);
  const login = useAuthStore((state) => state.login);

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
    if (!email.trim() || !password) {
      setError('Enter your email and password.');
      return;
    }
    signIn(email.trim(), password);
  };

  const fillDemoAccount = (demoEmail: string, demoPassword: string) => {
    setEmail(demoEmail);
    setPassword(demoPassword);
    setError('');
  };

  return (
    <div className="min-h-screen bg-cream grid lg:grid-cols-[1fr_1.05fr]">
      {/* Brand panel */}
      <aside className="hidden lg:flex flex-col justify-between bg-forest-900 text-forest-100 p-12 xl:p-16">
        <Link to="/" className="flex items-center gap-2.5 w-fit" aria-label="HeyJarvis Concierge home">
          <span className="w-9 h-9 rounded-[10px] bg-forest-700 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-forest-100" aria-hidden="true" />
          </span>
          <span className="leading-tight">
            <span className="font-display text-[19px] text-white block">HeyJarvis</span>
            <span className="text-[11px] text-forest-300 block">Concierge</span>
          </span>
        </Link>
        <div className="max-w-md">
          <p className="font-display text-[40px] leading-[1.1] text-white tracking-tight">
            Every patient inquiry deserves an answer.
          </p>
          <p className="mt-5 text-[15px] leading-relaxed text-forest-200">
            Your practice's requests, conversations and settings, all in one calm workspace.
          </p>

          <div className="mt-8 p-4 rounded-xl bg-forest-800/80 border border-forest-700/80 text-xs">
            <p className="font-semibold text-white flex items-center gap-1.5 mb-1">
              <Sparkles className="w-3.5 h-3.5 text-forest-200" aria-hidden="true" />
              Live Testing Logins Configured
            </p>
            <p className="text-forest-200 leading-relaxed">
              Use the demo account presets to test the platform as an Agency Administrator, Practice Doctor, or Front Desk staff.
            </p>
          </div>
        </div>
        <p className="text-[12.5px] text-forest-400">A HeyJarvis.ai product · Made for care teams</p>
      </aside>

      {/* Sign-in form */}
      <main className="flex items-center justify-center px-5 py-12 sm:px-8">
        <div className="w-full max-w-[420px] animate-rise">
          <Link to="/" className="lg:hidden flex items-center gap-2.5 mb-8 w-fit" aria-label="HeyJarvis Concierge home">
            <span className="w-9 h-9 rounded-[10px] bg-forest-800 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-forest-100" aria-hidden="true" />
            </span>
            <span className="font-display text-[19px] text-forest-900">HeyJarvis Concierge</span>
          </Link>

          <h1 className="text-[32px] leading-tight font-normal text-forest-900">Welcome back</h1>
          <p className="text-[15px] text-stone-600 mt-2">Sign in to your practice dashboard.</p>

          <form onSubmit={handleLogin} className="mt-6 space-y-4" noValidate>
            <div>
              <label htmlFor="login-email" className="block text-[13px] font-medium text-stone-700 mb-1.5">Email</label>
              <input
                id="login-email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 bg-white border border-stone-300 rounded-xl text-[15px] text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 transition"
                placeholder="name@practice.com"
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="login-password" className="block text-[13px] font-medium text-stone-700">Password</label>
                <Link to="/forgot-password" className="text-[12.5px] text-forest-700 hover:text-forest-900 link-quiet">Forgot password?</Link>
              </div>
              <div className="relative">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-4 pr-12 py-3 bg-white border border-stone-300 rounded-xl text-[15px] text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 transition"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  className="absolute inset-y-0 right-0 px-3.5 flex items-center text-stone-500 hover:text-forest-800"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" aria-hidden="true" /> : <Eye className="w-4 h-4" aria-hidden="true" />}
                </button>
              </div>
            </div>

            {error && (
              <p role="alert" className="text-[13.5px] text-red-800 bg-red-50 border border-red-200 rounded-xl px-3.5 py-2.5">{error}</p>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-forest-800 hover:bg-forest-900 text-white rounded-full font-medium text-[15px] transition-colors disabled:opacity-60 disabled:cursor-not-allowed shadow-sm"
            >
              {isLoading ? (
                <span className="animate-spin rounded-full h-5 w-5 border-2 border-white/30 border-t-white" aria-label="Signing in" />
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          {/* Quick Demo Credentials Panel for Production Testing */}
          <div className="mt-7 pt-5 border-t border-stone-200/80">
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-stone-500">
                Demo & Testing Logins
              </span>
              <span className="text-[10px] font-medium text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                1-Click Preset
              </span>
            </div>

            <div className="space-y-2">
              {DEMO_LOGINS.map((demo) => {
                const isSelected = email === demo.email;
                return (
                  <button
                    key={demo.email}
                    type="button"
                    onClick={() => fillDemoAccount(demo.email, demo.password)}
                    className={`w-full text-left p-2.5 rounded-xl border transition-all text-xs group ${
                      isSelected
                        ? 'border-forest-700 bg-forest-50/70 shadow-sm ring-1 ring-forest-700'
                        : 'border-stone-200 bg-white hover:border-stone-300 hover:bg-stone-50/70'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <span className="font-semibold text-stone-900 text-[12.5px]">{demo.role}</span>
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${demo.badgeColor}`}>
                        {demo.badge}
                      </span>
                    </div>
                    <p className="text-stone-500 text-[11px] font-mono mt-0.5 truncate">{demo.email}</p>
                    <div className="flex items-center justify-between mt-1.5 pt-1.5 border-t border-stone-100 text-[10.5px] text-stone-600">
                      <span className="truncate pr-1 text-stone-500">{demo.description}</span>
                      <span className={`font-semibold shrink-0 flex items-center gap-0.5 ${isSelected ? 'text-forest-800 font-bold' : 'text-stone-700 group-hover:text-forest-800'}`}>
                        {isSelected ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-600" />
                            <span>Selected</span>
                          </>
                        ) : (
                          <>
                            <span>Select</span>
                            <ArrowRight className="w-3 h-3" />
                          </>
                        )}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <p className="mt-6 text-[13px] text-stone-500 text-center">
            New to Concierge? <Link to="/request-access" className="link-quiet text-forest-800 font-medium">Request access for your practice</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
