import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUpRight,
  CalendarCheck,
  Clock,
  Code2,
  Inbox,
  Lock,
  Mail,
  MessageSquare,
  Palette,
  Send,
  ShieldCheck,
  Smile,
  Sparkles,
  Users,
} from 'lucide-react';

const HEYJARVIS_URL = 'https://www.heyjarvis.ai';
const ACCESS_URL = 'https://www.heyjarvis.ai/#pilot';

/** Fades sections in as they scroll into view (CSS respects prefers-reduced-motion). */
function Reveal({ children, className = '', delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const show = () => { el.dataset.visible = 'true'; };
    // Content already on screen (or without observer support) is shown immediately.
    if (typeof IntersectionObserver === 'undefined' || el.getBoundingClientRect().top < window.innerHeight) {
      show();
      return;
    }
    el.dataset.visible = 'false';
    // Safety net: never leave content hidden if the observer does not fire.
    const fallback = window.setTimeout(show, 2500);
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          show();
          window.clearTimeout(fallback);
          io.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    io.observe(el);
    return () => {
      window.clearTimeout(fallback);
      io.disconnect();
    };
  }, []);
  return (
    <div
      ref={ref}
      data-visible="true"
      style={{ transitionDelay: `${delay}ms` }}
      className={`transition-all duration-700 ease-brand data-[visible=false]:opacity-0 data-[visible=false]:translate-y-3 ${className}`}
    >
      {children}
    </div>
  );
}

function Mark({ size = 'md' }: { size?: 'md' | 'sm' }) {
  const box = size === 'md' ? 'w-9 h-9 rounded-[10px]' : 'w-7 h-7 rounded-lg';
  return (
    <span className={`${box} bg-forest-800 inline-flex items-center justify-center flex-shrink-0`}>
      <Sparkles className={size === 'md' ? 'w-4 h-4 text-forest-100' : 'w-3.5 h-3.5 text-forest-100'} aria-hidden="true" />
    </span>
  );
}

/* ── Product vignettes (mockups of real Concierge screens) ───────────────────── */

function WidgetPreview() {
  return (
    <div className="relative" aria-hidden="true">
      <div className="surface-card shadow-lift overflow-hidden">
        {/* macOS-style window bar */}
        <div className="relative flex items-center h-10 px-4 border-b border-stone-200 bg-stone-100/80">
          <span className="flex gap-2">
            <span className="w-3 h-3 rounded-full bg-[#FF5F57] ring-1 ring-black/10" />
            <span className="w-3 h-3 rounded-full bg-[#FEBC2E] ring-1 ring-black/10" />
            <span className="w-3 h-3 rounded-full bg-[#28C840] ring-1 ring-black/10" />
          </span>
          <span className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1.5 w-[46%] max-w-[260px] justify-center text-[11.5px] text-stone-600 bg-white border border-stone-200 rounded-md px-3 py-1 shadow-sm">
            <Lock className="w-3 h-3 text-stone-400 flex-shrink-0" />
            <span className="truncate">yourpractice.com</span>
          </span>
        </div>

        <div className="grid sm:grid-cols-[minmax(0,1fr)_300px]">
          {/* The practice's own website behind the widget */}
          <div className="hidden sm:flex flex-col bg-cream p-5 gap-4 min-w-0">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-md bg-forest-100 flex items-center justify-center flex-shrink-0">
                <Smile className="w-3.5 h-3.5 text-forest-700" />
              </span>
              <span className="text-[12px] font-semibold text-forest-900 truncate">Riverside Dental</span>
            </div>
            <div className="mt-2">
              <p className="font-display text-[19px] xl:text-[22px] leading-[1.15] text-forest-900">Gentle care for the whole family.</p>
              <p className="mt-2 text-[11.5px] leading-relaxed text-stone-500">Cleanings, exams and emergency visits in a calm, modern office.</p>
            </div>
            <span className="w-fit text-[11px] font-medium px-3 py-1.5 rounded-full bg-forest-800 text-white whitespace-nowrap">Request a visit</span>
          </div>

          {/* Concierge chat widget */}
          <div className="sm:border-l border-stone-200 bg-white flex flex-col min-h-[400px]">
            <div className="flex items-center gap-2.5 px-4 py-3 bg-forest-800 text-white">
              <span className="w-8 h-8 rounded-full bg-forest-700 flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-4 h-4 text-forest-100" />
              </span>
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold truncate">Riverside Family Dental</span>
                <span className="flex items-center gap-1.5 text-[11px] text-forest-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Online · replies instantly
                </span>
              </span>
            </div>
            <div className="flex-1 p-4 space-y-3 text-[12.5px] leading-relaxed">
              <p className="bg-stone-100 text-stone-800 rounded-2xl rounded-tl-md px-3.5 py-2.5 max-w-[92%]">
                Hi! Welcome to Riverside Family Dental. How can I help you today?
              </p>
              <div className="flex flex-wrap gap-1.5">
                {['New Patient', 'Routine Cleaning', 'Dental Emergency'].map((q) => (
                  <span key={q} className="text-[11px] px-2.5 py-1 rounded-full border border-forest-200 text-forest-800 bg-forest-50">
                    {q}
                  </span>
                ))}
              </div>
              <p className="ml-auto bg-forest-700 text-white rounded-2xl rounded-tr-md px-3.5 py-2.5 max-w-[85%] w-fit">
                I need a cleaning and checkup
              </p>
              <p className="bg-stone-100 text-stone-800 rounded-2xl rounded-tl-md px-3.5 py-2.5 max-w-[92%]">
                I'd be glad to help coordinate your cleaning. What is your full name?
              </p>
            </div>
            <div className="px-3 pb-3">
              <div className="flex items-center gap-2 rounded-full border border-stone-200 bg-stone-50 pl-4 pr-1.5 py-1.5">
                <span className="flex-1 text-[12px] text-stone-400 truncate">Type your message…</span>
                <span className="w-7 h-7 rounded-full bg-forest-800 flex items-center justify-center flex-shrink-0">
                  <Send className="w-3.5 h-3.5 text-white" />
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Front-desk notification: anchored to the website pane's empty corner, never over the chat */}
      <div
        className="hidden md:block lg:hidden xl:block absolute -bottom-6 -left-6 w-56 surface-card shadow-lift p-3.5 animate-rise"
        style={{ animationDelay: '500ms' }}
      >
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-forest-700 whitespace-nowrap">New request</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 whitespace-nowrap">Pending review</span>
        </div>
        <p className="text-[13px] font-semibold text-stone-900">Cleaning &amp; checkup</p>
        <p className="text-[12px] text-stone-500 mt-0.5">Thursday · Morning</p>
      </div>
    </div>
  );
}

function AfterHoursVignette() {
  return (
    <div className="surface-card p-5 space-y-3 text-[12.5px] leading-relaxed" aria-hidden="true">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">Saturday · 9:40 pm</span>
        <span className="text-[10.5px] px-2 py-0.5 rounded-full bg-stone-100 text-stone-600">Office closed</span>
      </div>
      <p className="ml-auto bg-forest-700 text-white rounded-2xl rounded-tr-md px-3.5 py-2.5 max-w-[85%] w-fit">
        I have a dental emergency
      </p>
      <p className="bg-red-50 text-red-900 border border-red-100 rounded-2xl rounded-tl-md px-3.5 py-2.5 max-w-[95%]">
        If you are experiencing severe pain, uncontrolled bleeding, or trauma, please call our emergency line
        immediately. What is your best callback number and your name?
      </p>
      <p className="bg-stone-100 text-stone-700 rounded-2xl rounded-tl-md px-3.5 py-2.5 max-w-[95%]">
        Our office is currently closed. Leave your details and our front desk will follow up first thing next business morning.
      </p>
    </div>
  );
}

function InboxVignette() {
  const rows = [
    { name: 'Maya R.', note: 'New patient exam, prefers afternoons', tag: 'New patient', tone: 'bg-forest-50 text-forest-800' },
    { name: 'Daniel K.', note: 'Chipped tooth after a fall', tag: 'Emergency', tone: 'bg-red-50 text-red-700' },
    { name: 'Priya S.', note: 'Moving my Tuesday appointment', tag: 'Reschedule', tone: 'bg-blue-50 text-blue-700' },
  ];
  return (
    <div className="surface-card overflow-hidden" aria-hidden="true">
      <div className="px-4 py-3 border-b border-stone-200 flex items-center justify-between">
        <span className="text-[12px] font-semibold text-stone-900">Appointment requests</span>
        <span className="text-[11px] text-stone-500">3 pending</span>
      </div>
      <ul className="divide-y divide-stone-100">
        {rows.map((r) => (
          <li key={r.name} className="px-4 py-3 flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-stone-100 text-stone-700 text-[12px] font-semibold flex items-center justify-center">
              {r.name.charAt(0)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-medium text-stone-900">{r.name}</span>
              <span className="block text-[12px] text-stone-500 truncate">{r.note}</span>
            </span>
            <span className={`text-[10.5px] px-2 py-0.5 rounded-full ${r.tone}`}>{r.tag}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RulesVignette() {
  return (
    <div className="surface-card p-5 space-y-4" aria-hidden="true">
      <div>
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">Office hours</span>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[12.5px]">
          {[
            ['Mon – Thu', '8:00 – 17:00'],
            ['Friday', '8:00 – 14:00'],
            ['Saturday', 'Closed'],
            ['Sunday', 'Closed'],
          ].map(([d, h]) => (
            <div key={d} className="flex justify-between rounded-lg bg-stone-50 border border-stone-200 px-3 py-2">
              <span className="text-stone-600">{d}</span>
              <span className="text-stone-900 font-medium">{h}</span>
            </div>
          ))}
        </div>
      </div>
      <div>
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">Assistant guidance</span>
        <p className="mt-2 text-[12.5px] leading-relaxed text-stone-700 rounded-lg bg-stone-50 border border-stone-200 px-3 py-2.5">
          Mention that we offer CareCredit financing. Never confirm an appointment time without the front desk.
        </p>
      </div>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────────────── */

const PROBLEMS = [
  {
    title: 'Inquiries arrive after the office closes',
    body: 'Patients research care in the evening and on weekends. Without a reply, many simply move on to the next practice.',
  },
  {
    title: 'The same questions, every day',
    body: 'Hours, services, insurance and new-patient steps take up front-desk time that belongs to the patients in the chair.',
  },
  {
    title: 'Requests scatter across channels',
    body: 'Web forms, voicemail and email each hold part of the picture, and appointment requests slip through the gaps.',
  },
  {
    title: 'Follow-ups are hard to track',
    body: 'Without one shared queue it is difficult to see who has been contacted, who is waiting, and what was promised.',
  },
];

const STEPS = [
  { title: 'A patient visits your website', body: 'Concierge sits quietly on every page of your practice site.' },
  { title: 'They open the concierge', body: 'A branded chat greets them with your practice name and hours.' },
  { title: 'It answers from your rules', body: 'Replies follow the hours, policies and guidance your team configures.' },
  { title: 'They leave a request', body: 'Name, contact details and preferred timing are collected step by step.' },
  { title: 'It lands in your dashboard', body: 'Each request appears in a shared inbox, with an email alert to your team.' },
  { title: 'Your team follows up', body: 'Staff reply, propose a time and update the status in one place.' },
];

const FEATURE_GROUPS = [
  {
    eyebrow: 'For patients',
    title: 'A calm, helpful first conversation.',
    body: 'A website widget and a hosted concierge page give patients a clear way to ask questions and request a visit at any hour, with emergencies routed straight to your callback number.',
    points: [
      { icon: MessageSquare, label: 'Website chat widget and hosted concierge page' },
      { icon: Clock, label: 'After-hours messaging from your configured office hours' },
      { icon: ShieldCheck, label: 'Emergency requests fast-tracked to your team' },
    ],
    vignette: <AfterHoursVignette />,
  },
  {
    eyebrow: 'For the front desk',
    title: 'One inbox for every request.',
    body: 'Appointment requests and conversations live in a single, searchable workspace. Your team can reply by email, propose a visit time, add internal notes and track status without switching tools.',
    points: [
      { icon: Inbox, label: 'Shared request inbox with status and priority' },
      { icon: CalendarCheck, label: 'Propose visit times directly in replies' },
      { icon: Mail, label: 'Staff replies delivered from your practice email' },
    ],
    vignette: <InboxVignette />,
  },
  {
    eyebrow: 'For practice admins',
    title: 'Configured around your practice.',
    body: 'Set office hours, emergency contacts and assistant guidance, choose your widget colors and greeting, and decide who on the team receives which alerts.',
    points: [
      { icon: Clock, label: 'Business rules and practice-specific assistant guidance' },
      { icon: Palette, label: 'Widget branding, greeting and placement' },
      { icon: Users, label: 'Team roles, email templates and an audit log' },
    ],
    vignette: <RulesVignette />,
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-cream text-stone-800">
      {/* Navigation */}
      <header className="sticky top-0 z-40 bg-cream/85 backdrop-blur border-b border-stone-200/70">
        <nav className="max-w-content mx-auto px-5 sm:px-8 h-16 flex items-center justify-between" aria-label="Primary">
          <Link to="/" className="flex items-center gap-2.5" aria-label="HeyJarvis Concierge home">
            <Mark />
            <span className="leading-tight">
              <span className="font-display text-[19px] text-forest-900 block tracking-tight">HeyJarvis</span>
              <span className="text-[11px] font-medium text-forest-700 block">Concierge</span>
            </span>
          </Link>
          <div className="flex items-center gap-1 sm:gap-2">
            <a href="#how" className="hidden md:inline-flex px-3 py-2 text-[13.5px] text-stone-600 hover:text-forest-900 transition-colors">How it works</a>
            <a href="#features" className="hidden md:inline-flex px-3 py-2 text-[13.5px] text-stone-600 hover:text-forest-900 transition-colors">Features</a>
            <a href="#install" className="hidden md:inline-flex px-3 py-2 text-[13.5px] text-stone-600 hover:text-forest-900 transition-colors">Installation</a>
            <Link to="/login" className="px-3 py-2 text-[13.5px] font-medium text-forest-900 hover:text-forest-700 transition-colors">
              Sign in
            </Link>
            <a
              href={ACCESS_URL}
              className="hidden sm:inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-forest-800 hover:bg-forest-900 text-white text-[13.5px] font-medium transition-colors"
            >
              Request access
            </a>
          </div>
        </nav>
      </header>

      <main>
        {/* Hero */}
        <section className="max-w-content mx-auto px-5 sm:px-8 pt-16 sm:pt-24 pb-24 grid lg:grid-cols-[1.05fr_1fr] gap-14 lg:gap-16 items-center">
          <div className="animate-rise">
            <span className="eyebrow">
              <span className="w-1.5 h-1.5 rounded-full bg-forest-500" aria-hidden="true" />
              For dental practices
            </span>
            <h1 className="display text-[44px] sm:text-[60px] leading-[1.03] mt-5">
              Every patient inquiry deserves an answer.
            </h1>
            <p className="mt-6 text-[17px] leading-relaxed text-stone-600 max-w-[34rem]">
              HeyJarvis Concierge helps dental practices respond to patient questions, capture appointment requests,
              and keep every conversation organized, even after the front desk closes.
            </p>
            <div className="mt-9 flex flex-col sm:flex-row gap-3">
              <a
                href={ACCESS_URL}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full bg-forest-800 hover:bg-forest-900 text-white text-[15px] font-medium transition-colors"
              >
                Request access <ArrowRight className="w-4 h-4" aria-hidden="true" />
              </a>
              <a
                href="#how"
                className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full border border-stone-300 hover:border-forest-400 bg-white/60 text-forest-900 text-[15px] font-medium transition-colors"
              >
                See how it works
              </a>
            </div>
            <p className="mt-6 text-[13px] text-stone-500">
              Already using Concierge? <Link to="/login" className="link-quiet text-forest-800">Sign in to your practice</Link>
            </p>
          </div>
          <div className="animate-rise" style={{ animationDelay: '150ms' }}>
            <WidgetPreview />
          </div>
        </section>

        {/* Problem */}
        <section className="border-t border-stone-200 bg-white/60">
          <div className="max-w-content mx-auto px-5 sm:px-8 py-24 grid lg:grid-cols-[0.9fr_1.1fr] gap-12 lg:gap-20">
            <Reveal>
              <span className="eyebrow">The front-desk reality</span>
              <h2 className="display text-[34px] sm:text-[44px] leading-[1.08] mt-4">
                Your team is busy. Patients still expect a reply.
              </h2>
              <p className="mt-5 text-[16px] leading-relaxed text-stone-600 max-w-md">
                Concierge gives every inquiry a prompt, consistent first response and puts the follow-up in front of the right person.
              </p>
            </Reveal>
            <div className="grid sm:grid-cols-2 gap-x-10 gap-y-10">
              {PROBLEMS.map((p, i) => (
                <Reveal key={p.title} delay={i * 80}>
                  <span className="font-display text-[15px] text-forest-600">0{i + 1}</span>
                  <h3 className="mt-2 text-[17px] font-semibold text-stone-900 leading-snug">{p.title}</h3>
                  <p className="mt-2 text-[14.5px] leading-relaxed text-stone-600">{p.body}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* Workflow */}
        <section id="how" className="scroll-mt-20 border-t border-stone-200">
          <div className="max-w-content mx-auto px-5 sm:px-8 py-24">
            <Reveal className="max-w-2xl">
              <span className="eyebrow">How it works</span>
              <h2 className="display text-[34px] sm:text-[44px] leading-[1.08] mt-4">
                From first question to follow-up, in one flow.
              </h2>
            </Reveal>
            <ol className="mt-14 grid sm:grid-cols-2 lg:grid-cols-3 border-t border-l border-stone-200">
              {STEPS.map((s, i) => (
                <li key={s.title} className="border-r border-b border-stone-200 p-7 bg-white/40 hover:bg-white transition-colors duration-300">
                  <Reveal delay={(i % 3) * 80}>
                    <span className="font-display text-[40px] leading-none text-forest-300">{String(i + 1).padStart(2, '0')}</span>
                    <h3 className="mt-5 text-[16.5px] font-semibold text-stone-900">{s.title}</h3>
                    <p className="mt-2 text-[14.5px] leading-relaxed text-stone-600">{s.body}</p>
                  </Reveal>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="scroll-mt-20 border-t border-stone-200 bg-white/60">
          <div className="max-w-content mx-auto px-5 sm:px-8 py-24 space-y-24">
            {FEATURE_GROUPS.map((g, i) => (
              <div key={g.eyebrow} className={`grid lg:grid-cols-2 gap-12 lg:gap-16 items-center ${i % 2 === 1 ? 'lg:[&>*:first-child]:order-2' : ''}`}>
                <Reveal>
                  <span className="eyebrow">{g.eyebrow}</span>
                  <h2 className="display text-[30px] sm:text-[38px] leading-[1.1] mt-4">{g.title}</h2>
                  <p className="mt-5 text-[16px] leading-relaxed text-stone-600 max-w-lg">{g.body}</p>
                  <ul className="mt-7 space-y-3.5">
                    {g.points.map(({ icon: Icon, label }) => (
                      <li key={label} className="flex items-start gap-3 text-[14.5px] text-stone-700">
                        <span className="mt-0.5 w-7 h-7 rounded-full bg-forest-50 border border-forest-100 flex items-center justify-center flex-shrink-0">
                          <Icon className="w-3.5 h-3.5 text-forest-700" aria-hidden="true" />
                        </span>
                        <span className="pt-1">{label}</span>
                      </li>
                    ))}
                  </ul>
                </Reveal>
                <Reveal delay={120} className="lg:px-6">
                  {g.vignette}
                </Reveal>
              </div>
            ))}
          </div>
        </section>

        {/* Installation */}
        <section id="install" className="scroll-mt-20 border-t border-stone-200">
          <div className="max-w-content mx-auto px-5 sm:px-8 py-24 grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            <Reveal>
              <span className="eyebrow">Installation</span>
              <h2 className="display text-[34px] sm:text-[44px] leading-[1.08] mt-4">Add it to the website you already have.</h2>
              <p className="mt-5 text-[16px] leading-relaxed text-stone-600 max-w-lg">
                Paste one script tag before the closing body tag, download the WordPress plugin prepared for your practice,
                or link patients to your hosted concierge page.
              </p>
              <div className="mt-7 flex flex-wrap gap-2 text-[12.5px] text-stone-600">
                {['WordPress plugin', 'Squarespace', 'Wix', 'Webflow', 'Any HTML site'].map((t) => (
                  <span key={t} className="px-3 py-1 rounded-full border border-stone-200 bg-white/70">{t}</span>
                ))}
              </div>
            </Reveal>
            <Reveal delay={120}>
              <div className="rounded-card bg-forest-950 text-forest-100 p-6 shadow-lift">
                <div className="flex items-center gap-2 text-[12px] text-forest-300 mb-4">
                  <Code2 className="w-4 h-4" aria-hidden="true" />
                  <span>Website embed</span>
                </div>
                <pre className="text-[12.5px] leading-relaxed whitespace-pre-wrap break-all font-mono">
                  <span className="text-forest-400">&lt;script</span> async{'\n'}
                  {'  '}src=<span className="text-sage-300">"https://your-concierge-host/widget.js"</span>{'\n'}
                  {'  '}data-heyjarvis-client=<span className="text-sage-300">"your-practice-key"</span>
                  <span className="text-forest-400">&gt;&lt;/script&gt;</span>
                </pre>
                <p className="mt-5 text-[12px] text-forest-300">Each practice gets its own key and embed code in the dashboard.</p>
              </div>
            </Reveal>
          </div>
        </section>

        {/* Final call to action */}
        <section className="border-t border-stone-200 bg-forest-900 text-white">
          <div className="max-w-content mx-auto px-5 sm:px-8 py-24 text-center">
            <Reveal>
              <h2 className="font-display text-[36px] sm:text-[52px] leading-[1.06] tracking-tight max-w-3xl mx-auto">
                Give every patient a prompt, thoughtful first reply.
              </h2>
              <p className="mt-5 text-[16px] text-forest-200 max-w-xl mx-auto">
                HeyJarvis Concierge is currently available to practices in our private beta.
              </p>
              <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
                <a
                  href={ACCESS_URL}
                  className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full bg-cream text-forest-900 hover:bg-white text-[15px] font-medium transition-colors"
                >
                  Request access <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </a>
                <a
                  href="/demo/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full border border-forest-600 hover:border-forest-300 text-white text-[15px] font-medium transition-colors"
                >
                  Try the patient widget <ArrowUpRight className="w-4 h-4" aria-hidden="true" />
                </a>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="bg-cream border-t border-stone-200">
        <div className="max-w-content mx-auto px-5 sm:px-8 py-12 grid sm:grid-cols-[1.4fr_1fr_1fr] gap-10">
          <div>
            <div className="flex items-center gap-2.5">
              <Mark size="sm" />
              <span className="font-display text-[18px] text-forest-900">HeyJarvis Concierge</span>
            </div>
            <p className="mt-4 text-[13.5px] leading-relaxed text-stone-600 max-w-xs">
              AI-powered patient communication for modern dental practices. A product of HeyJarvis.ai, made for care teams.
            </p>
          </div>
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">Product</h3>
            <ul className="mt-4 space-y-2.5 text-[13.5px]">
              <li><a href="#how" className="text-stone-700 hover:text-forest-800 transition-colors">How it works</a></li>
              <li><a href="#features" className="text-stone-700 hover:text-forest-800 transition-colors">Features</a></li>
              <li><Link to="/login" className="text-stone-700 hover:text-forest-800 transition-colors">Sign in</Link></li>
            </ul>
          </div>
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">HeyJarvis.ai</h3>
            <ul className="mt-4 space-y-2.5 text-[13.5px]">
              <li><a href={`${HEYJARVIS_URL}/about/`} className="text-stone-700 hover:text-forest-800 transition-colors">About</a></li>
              <li><a href={ACCESS_URL} className="text-stone-700 hover:text-forest-800 transition-colors">Private beta</a></li>
              <li><a href={HEYJARVIS_URL} className="text-stone-700 hover:text-forest-800 transition-colors">heyjarvis.ai</a></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-stone-200">
          <div className="max-w-content mx-auto px-5 sm:px-8 py-5 text-[12.5px] text-stone-500">
            © {new Date().getFullYear()} HeyJarvis. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
}
