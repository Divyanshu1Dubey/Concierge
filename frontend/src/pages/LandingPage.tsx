import {
  Sparkles,
  Bot,
  ArrowRight,
  MessageSquare,
  CalendarCheck
} from 'lucide-react';
import { Link } from 'react-router-dom';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 selection:bg-teal-500 selection:text-slate-950">
      {/* Top Navbar */}
      <nav className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gradient-to-br from-teal-400 via-teal-500 to-cyan-500 rounded-xl shadow-md">
                <Sparkles className="w-5 h-5 text-slate-950 font-black" />
              </div>
              <div>
                <span className="text-lg font-black tracking-tight text-white block">HeyJarvis Concierge™</span>
                <span className="text-[10px] font-bold text-teal-400 uppercase tracking-widest block">
                  AI Dental Front Desk Platform
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Link
                to="/login"
                className="px-4 py-2 bg-teal-500 hover:bg-teal-400 text-slate-950 rounded-xl text-xs font-black shadow-md transition-all flex items-center gap-1.5"
              >
                Sign In to Practice <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-teal-500/10 border border-teal-500/30 text-teal-300 rounded-full text-xs font-extrabold mb-8 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
          The Multi-Tenant AI Dental Concierge Cloud
        </div>

        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-black text-white tracking-tight leading-tight max-w-4xl mx-auto mb-6">
          Never Miss a Dental Patient.
          <br />
          <span className="bg-gradient-to-r from-teal-400 via-cyan-400 to-blue-500 bg-clip-text text-transparent">
            Automate Your Front Desk 24/7.
          </span>
        </h1>

        <p className="text-base sm:text-lg text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed font-medium">
          Built specifically for dental practices and dental agencies. HeyJarvis Concierge welcomes website visitors,
          answers treatment questions, handles emergency triage, and coordinates appointments directly for your front-desk team.
        </p>

        {/* Primary Call-To-Action */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 max-w-md mx-auto">
          <Link
            to="/login"
            className="w-full sm:w-auto px-8 py-3.5 bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-slate-950 font-black rounded-xl text-sm shadow-xl transition-all flex items-center justify-center gap-2"
          >
            <Bot className="w-4 h-4" />
            Open Concierge Workspace
          </Link>
          <a
            href="/demo/"
            target="_blank"
            rel="noopener noreferrer"
            className="w-full sm:w-auto px-6 py-3.5 bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 font-bold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
          >
            View Live Patient Widget
          </a>
        </div>

        {/* Live Metrics Ticker Banner */}
        <div className="mt-14 max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-4 p-5 bg-slate-900/60 border border-slate-800 rounded-2xl">
          <div>
            <div className="text-2xl font-black text-white">24/7</div>
            <div className="text-[11px] text-slate-400 font-medium mt-0.5">Automated Concierge</div>
          </div>
          <div>
            <div className="text-2xl font-black text-teal-400">&lt; 3 sec</div>
            <div className="text-[11px] text-slate-400 font-medium mt-0.5">Patient Response Time</div>
          </div>
          <div>
            <div className="text-2xl font-black text-white">100%</div>
            <div className="text-[11px] text-slate-400 font-medium mt-0.5">Isolated Multi-Tenancy</div>
          </div>
          <div>
            <div className="text-2xl font-black text-cyan-400">HIPAA</div>
            <div className="text-[11px] text-slate-400 font-medium mt-0.5">Encrypted Architecture</div>
          </div>
        </div>
      </div>

      {/* Core Concierge Pillars */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 border-t border-slate-800/80">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-black text-white mb-3">Designed for the Dental Front Desk</h2>
          <p className="text-sm text-slate-400 max-w-xl mx-auto">
            Everything treatment coordinators and front-desk receptionists need to streamline patient communication.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          <div className="p-8 rounded-3xl bg-slate-900/80 border border-slate-800 hover:border-teal-500/40 transition-all space-y-4">
            <div className="p-3 bg-teal-500/10 border border-teal-500/30 w-fit rounded-2xl">
              <Bot className="w-6 h-6 text-teal-400" />
            </div>
            <h3 className="text-xl font-black text-white">24/7 AI Dental Concierge</h3>
            <p className="text-xs text-slate-400 leading-relaxed font-normal">
              Engages website visitors with a luxury dental concierge widget. Gathers symptoms, answers insurance questions, and triages emergencies.
            </p>
          </div>

          <div className="p-8 rounded-3xl bg-slate-900/80 border border-slate-800 hover:border-cyan-500/40 transition-all space-y-4">
            <div className="p-3 bg-cyan-500/10 border border-cyan-500/30 w-fit rounded-2xl">
              <CalendarCheck className="w-6 h-6 text-cyan-400" />
            </div>
            <h3 className="text-xl font-black text-white">Appointment Intake</h3>
            <p className="text-xs text-slate-400 leading-relaxed font-normal">
              Captures patient preferred dates and times, contact info, and procedure types into an actionable front-desk command queue.
            </p>
          </div>

          <div className="p-8 rounded-3xl bg-slate-900/80 border border-slate-800 hover:border-purple-500/40 transition-all space-y-4">
            <div className="p-3 bg-purple-500/10 border border-purple-500/30 w-fit rounded-2xl">
              <MessageSquare className="w-6 h-6 text-purple-400" />
            </div>
            <h3 className="text-xl font-black text-white">AI-Assisted Reply Composer</h3>
            <p className="text-xs text-slate-400 leading-relaxed font-normal">
              Empowers staff to generate warm, empathetic responses, propose openings, and send email replies in seconds with one click.
            </p>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-8 bg-slate-950 text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-teal-400" />
            <span className="font-bold text-slate-400">HeyJarvis Concierge™ • Multi-Tenant Dental SaaS Cloud</span>
          </div>
          <div>
            Built for Dental Practices &bull; Secure &amp; Isolated Cloud Architecture
          </div>
        </div>
      </footer>
    </div>
  );
}
