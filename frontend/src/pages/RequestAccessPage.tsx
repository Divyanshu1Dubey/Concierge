import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, CheckCircle2 } from 'lucide-react';
import { publicApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';

const inputClass =
  'w-full px-4 py-3 bg-white border border-stone-300 rounded-xl text-[15px] text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 transition';

export default function RequestAccessPage() {
  const [form, setForm] = useState({ practice_name: '', contact_name: '', email: '', phone: '', website: '', message: '', company_fax: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setErrors({});
    setIsLoading(true);
    try {
      await publicApi.requestAccess(form);
      setDone(true);
    } catch (err: any) {
      const data = err?.response?.data;
      if (err?.response?.status === 400 && data && typeof data === 'object') setErrors(data);
      else if (err?.response?.status === 429) setError('Too many requests. Please try again later.');
      else setError(apiErrorMessage(err, 'We could not send your request. Please try again.'));
    } finally {
      setIsLoading(false);
    }
  };

  const field = (key: keyof typeof form, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div>
      <label htmlFor={`ra-${key}`} className="block text-[13px] font-medium text-stone-700 mb-1.5">{label}</label>
      <input id={`ra-${key}`} value={form[key]} onChange={set(key)} className={inputClass} {...props} />
      {errors[key] && <p className="mt-1 text-[12.5px] text-red-700">{errors[key]}</p>}
    </div>
  );

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center px-5 py-12">
      <div className="w-full max-w-[480px] animate-rise">
        <Link to="/" className="flex items-center gap-2.5 mb-10 w-fit" aria-label="HeyJarvis Concierge home">
          <span className="w-9 h-9 rounded-[10px] bg-forest-800 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-forest-100" aria-hidden="true" />
          </span>
          <span className="font-display text-[19px] text-forest-900">HeyJarvis Concierge</span>
        </Link>
        {done ? (
          <div role="status" className="space-y-4">
            <CheckCircle2 className="w-10 h-10 text-forest-700" aria-hidden="true" />
            <h1 className="text-[30px] leading-tight text-forest-900">Request received</h1>
            <p className="text-[15px] text-stone-600">
              Thank you. Our team reviews every practice personally and will contact you at the email you provided.
              Accounts are created only after that conversation.
            </p>
            <Link to="/login" className="inline-flex text-[14px] font-medium text-forest-800 link-quiet">Back to sign in</Link>
          </div>
        ) : (
          <>
            <h1 className="text-[32px] leading-tight text-forest-900">Request access</h1>
            <p className="text-[15px] text-stone-600 mt-2">
              Tell us about your dental practice. We will review your request and set up your practice and team accounts with you.
            </p>
            <form onSubmit={handleSubmit} className="mt-8 space-y-4" noValidate>
              {field('practice_name', 'Practice name', { required: true, autoComplete: 'organization', maxLength: 200 })}
              {field('contact_name', 'Your name', { required: true, autoComplete: 'name', maxLength: 200 })}
              {field('email', 'Work email', { required: true, type: 'email', autoComplete: 'email', maxLength: 254 })}
              <div className="grid sm:grid-cols-2 gap-4">
                {field('phone', 'Phone (optional)', { type: 'tel', autoComplete: 'tel', maxLength: 40 })}
                {field('website', 'Website (optional)', { autoComplete: 'url', maxLength: 300, placeholder: 'yourpractice.com' })}
              </div>
              <div>
                <label htmlFor="ra-message" className="block text-[13px] font-medium text-stone-700 mb-1.5">Anything we should know? (optional)</label>
                <textarea id="ra-message" rows={3} maxLength={2000} value={form.message} onChange={set('message')} className={inputClass} />
                <p className="mt-1 text-[12px] text-stone-500">Please do not include patient information.</p>
              </div>
              {/* Spam trap: hidden from people, often filled in by bots. */}
              <div aria-hidden="true" className="absolute -left-[9999px] w-px h-px overflow-hidden">
                <label htmlFor="ra-company_fax">Company fax</label>
                <input id="ra-company_fax" tabIndex={-1} autoComplete="off" value={form.company_fax} onChange={set('company_fax')} />
              </div>
              {error && <p role="alert" className="text-[13.5px] text-red-800 bg-red-50 border border-red-200 rounded-xl px-3.5 py-2.5">{error}</p>}
              <button type="submit" disabled={isLoading}
                className="w-full px-4 py-3 bg-forest-800 hover:bg-forest-900 text-white rounded-full font-medium text-[15px] transition-colors disabled:opacity-60">
                {isLoading ? 'Sending…' : 'Send request'}
              </button>
            </form>
            <p className="mt-8 text-[13px] text-stone-500">
              Already have an account? <Link to="/login" className="link-quiet text-forest-800">Sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}