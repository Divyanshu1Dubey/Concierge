import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { CalendarCheck, CalendarClock, CheckCircle2, MapPin, Phone, AlertCircle } from 'lucide-react';
import { publicApi } from '@/services/api';

interface Offer {
  state: 'pending' | 'confirmed' | 'reschedule_requested' | 'superseded' | 'expired' | 'closed' | 'invalid';
  practice: { name: string; initial: string; logo_url: string; color: string; button_text_color: string; phone: string; email: string; address: string; website: string };
  patient_first_name: string;
  date_display: string;
  time: string;
  timezone: string;
  service: string;
  reference: string;
  message?: string;
}

/** Patient page reached from the confirmation email. Nothing changes until the patient presses a button. */
export default function AppointmentResponsePage() {
  const { token = '' } = useParams();
  const [params] = useSearchParams();
  const [offer, setOffer] = useState<Offer | null>(null);
  const [loadError, setLoadError] = useState('');
  const [mode, setMode] = useState<'choose' | 'reschedule'>(params.get('action') === 'reschedule' ? 'reschedule' : 'choose');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    document.title = 'Your appointment';
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex, nofollow';
    document.head.appendChild(meta);
    publicApi.getAppointmentOffer(token)
      .then((data) => setOffer(data))
      .catch((err) => {
        if (err?.response?.status === 404) setLoadError('This link is not valid. Please contact the practice.');
        else if (err?.response?.status === 429) setLoadError('Too many attempts. Please wait a minute and try again.');
        else setLoadError('We could not load your appointment. Check your connection and try again.');
      });
    return () => { document.head.removeChild(meta); };
  }, [token]);

  const act = async (action: 'confirm' | 'reschedule') => {
    setBusy(true);
    setActionError('');
    try {
      const data = await publicApi.respondToAppointmentOffer(token, action, action === 'reschedule' ? note : undefined);
      setOffer(data);
    } catch (err: any) {
      const data = err?.response?.data;
      if (err?.response?.status === 409 && data?.state) setOffer(data);
      else if (err?.response?.status === 429) setActionError('Too many attempts. Please wait a minute and try again.');
      else setActionError(data?.message || 'Something went wrong and nothing was changed. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  if (loadError) {
    return (
      <Shell>
        <div className="text-center py-6" role="alert">
          <AlertCircle className="w-10 h-10 text-stone-400 mx-auto" aria-hidden="true" />
          <p className="mt-4 text-[16px] text-stone-700">{loadError}</p>
        </div>
      </Shell>
    );
  }
  if (!offer) {
    return <Shell><p className="text-center text-stone-500 py-10" role="status">Loading your appointment…</p></Shell>;
  }

  const p = offer.practice;
  const accent = { backgroundColor: p.color, color: p.button_text_color };

  return (
    <Shell>
      <header className="flex items-center gap-3 pb-5 border-b border-stone-200">
        {p.logo_url ? (
          <img src={p.logo_url} alt={p.name} className="h-10 max-w-[160px] object-contain" />
        ) : (
          <span className="w-10 h-10 rounded-[10px] flex items-center justify-center font-display text-[18px]" style={accent} aria-hidden="true">{p.initial}</span>
        )}
        <span className="font-semibold text-[16px] text-stone-900">{p.name}</span>
      </header>

      <div className="pt-6">
        <Outcome offer={offer} />

        <div className="mt-5 rounded-2xl border border-stone-200 bg-stone-50 p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">
            {offer.state === 'confirmed' ? 'Your appointment' : 'Proposed appointment'}
          </p>
          <p className="mt-1.5 text-[19px] font-semibold text-stone-900">{offer.date_display}</p>
          <p className="text-[17px] font-semibold" style={{ color: p.color }}>
            {offer.time}{offer.timezone && <span className="ml-1 text-[13px] font-normal text-stone-500">{offer.timezone}</span>}
          </p>
          {offer.service && <p className="mt-3 text-[14px] text-stone-700"><span className="font-semibold text-stone-900">Visit:</span> {offer.service}</p>}
          {p.address && <p className="mt-1.5 text-[14px] text-stone-700 flex gap-1.5"><MapPin className="w-4 h-4 mt-0.5 flex-shrink-0 text-stone-400" aria-hidden="true" />{p.address}</p>}
        </div>

        {offer.state === 'pending' && mode === 'choose' && (
          <div className="mt-6 grid sm:grid-cols-2 gap-3">
            <button type="button" disabled={busy} onClick={() => act('confirm')}
              className="w-full px-5 py-3.5 rounded-full font-semibold text-[15px] disabled:opacity-60" style={accent}>
              {busy ? 'Confirming…' : 'Confirm appointment'}
            </button>
            <button type="button" disabled={busy} onClick={() => setMode('reschedule')}
              className="w-full px-5 py-3.5 rounded-full font-semibold text-[15px] border border-stone-300 bg-white text-stone-900 hover:border-stone-400 disabled:opacity-60">
              Request a different time
            </button>
          </div>
        )}

        {(offer.state === 'pending' || offer.state === 'confirmed') && mode === 'reschedule' && (
          <div className="mt-6 space-y-3">
            <label htmlFor="resched-note" className="block text-[14px] font-medium text-stone-800">Which days or times work better for you? (optional)</label>
            <textarea id="resched-note" rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Weekday afternoons after 2 pm"
              className="w-full px-4 py-3 bg-white border border-stone-300 rounded-xl text-[15px] focus:outline-none focus:ring-2 focus:ring-stone-400/40" />
            <p className="text-[12px] text-stone-500">Please don't include medical details. The front desk will contact you.</p>
            <div className="grid sm:grid-cols-2 gap-3">
              <button type="button" disabled={busy} onClick={() => act('reschedule')}
                className="w-full px-5 py-3.5 rounded-full font-semibold text-[15px] disabled:opacity-60" style={accent}>
                {busy ? 'Sending…' : 'Send request'}
              </button>
              <button type="button" disabled={busy} onClick={() => setMode('choose')}
                className="w-full px-5 py-3.5 rounded-full font-semibold text-[15px] border border-stone-300 bg-white text-stone-900">
                Back
              </button>
            </div>
          </div>
        )}

        {offer.state === 'confirmed' && mode === 'choose' && (
          <button type="button" onClick={() => setMode('reschedule')} className="mt-5 text-[14px] font-medium underline underline-offset-4 text-stone-700">
            Need a different time?
          </button>
        )}

        {actionError && <p role="alert" className="mt-4 text-[14px] text-red-800 bg-red-50 border border-red-200 rounded-xl px-4 py-3">{actionError}</p>}

        <footer className="mt-8 pt-5 border-t border-stone-200 text-[13px] text-stone-600 space-y-1">
          {p.phone && <p className="flex items-center gap-1.5"><Phone className="w-4 h-4 text-stone-400" aria-hidden="true" />Questions? Call <a href={`tel:${p.phone}`} className="font-medium" style={{ color: p.color }}>{p.phone}</a></p>}
          {offer.reference && <p className="text-stone-400">Reference {offer.reference}</p>}
        </footer>
      </div>
    </Shell>
  );
}

function Outcome({ offer }: { offer: Offer }) {
  const name = offer.patient_first_name ? `${offer.patient_first_name}, ` : '';
  switch (offer.state) {
    case 'confirmed':
      return (
        <div role="status" className="flex gap-3">
          <CheckCircle2 className="w-7 h-7 text-emerald-600 flex-shrink-0" aria-hidden="true" />
          <div>
            <h1 className="font-display text-[26px] leading-tight text-stone-900">You're confirmed</h1>
            <p className="mt-1 text-[15px] text-stone-600">Thank you. {offer.practice.name} can see that you confirmed this time.</p>
          </div>
        </div>
      );
    case 'reschedule_requested':
      return (
        <div role="status" className="flex gap-3">
          <CalendarClock className="w-7 h-7 text-blue-600 flex-shrink-0" aria-hidden="true" />
          <div>
            <h1 className="font-display text-[26px] leading-tight text-stone-900">Request sent</h1>
            <p className="mt-1 text-[15px] text-stone-600">The front desk will contact you to arrange a new time. The time below is not confirmed.</p>
          </div>
        </div>
      );
    case 'pending':
      return (
        <div className="flex gap-3">
          <CalendarCheck className="w-7 h-7 text-stone-500 flex-shrink-0" aria-hidden="true" />
          <div>
            <h1 className="font-display text-[26px] leading-tight text-stone-900">{name}does this time work for you?</h1>
            <p className="mt-1 text-[15px] text-stone-600">Confirm below, or ask for a different time.</p>
          </div>
        </div>
      );
    default:
      return (
        <div role="alert" className="flex gap-3">
          <AlertCircle className="w-7 h-7 text-stone-400 flex-shrink-0" aria-hidden="true" />
          <div>
            <h1 className="font-display text-[24px] leading-tight text-stone-900">This link can't be used</h1>
            <p className="mt-1 text-[15px] text-stone-600">
              {offer.message ||
                (offer.state === 'superseded' ? 'This time was replaced by a newer one. Please use the most recent email from the practice.'
                  : offer.state === 'expired' ? 'This appointment time has passed or the link has expired. Please contact the practice.'
                  : 'This request is no longer active. Please contact the practice directly.')}
            </p>
          </div>
        </div>
      );
  }
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-cream px-4 py-8 sm:py-14">
      <main className="mx-auto w-full max-w-[520px] bg-white rounded-2xl border border-stone-200 shadow-card p-6 sm:p-8">{children}</main>
      <p className="mt-5 text-center text-[11px] text-stone-400">Secured by HeyJarvis Concierge</p>
    </div>
  );
}