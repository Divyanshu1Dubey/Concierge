import { Link } from 'react-router-dom';
import {
  User,
  LogOut,
  Bot,
  Layers,
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';

interface HeaderProps {
  onMenuToggle: () => void;
}

export default function Header({ onMenuToggle }: HeaderProps) {
  const { user, logout, activePracticeId, activePracticeName, setActivePractice } = useAuthStore();

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-4 lg:px-6 shadow-sm sticky top-0 z-30">
      {/* Left: Mobile Toggle & Product Mode Switcher */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuToggle}
          className="lg:hidden p-2 -ml-2 rounded-lg hover:bg-gray-100 text-gray-600"
          aria-label="Toggle Navigation"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        {/* Inbound Concierge Active Pill */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-teal-50 border border-teal-200/80 rounded-xl text-xs font-bold text-teal-900">
          <span className="w-2 h-2 rounded-full bg-teal-500 animate-pulse" />
          <Bot className="w-3.5 h-3.5 text-teal-600" />
          <span>Inbound AI Concierge</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded bg-teal-100/80 text-teal-800 uppercase font-extrabold">Active</span>
        </div>
      </div>

      {/* Middle: Practice Info (Desktop) */}
      <div className="hidden lg:flex items-center gap-3 text-xs">
        {user?.is_agency_admin || user?.role === 'AGENCY_ADMIN' ? (
          activePracticeId ? (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-50 border border-purple-200 rounded-xl text-purple-900 shadow-sm animate-in fade-in">
              <Layers className="w-3.5 h-3.5 text-purple-600" />
              <span>Workspace:</span>
              <span className="font-black text-purple-950">{activePracticeName || 'Selected Dentistry'}</span>
              <button
                onClick={() => {
                  setActivePractice(null, null);
                  window.location.reload();
                }}
                className="ml-1 text-[11px] px-2 py-0.5 rounded bg-purple-200/80 hover:bg-purple-300 text-purple-900 font-bold transition"
                title="Switch back to Agency Overview of all practices"
              >
                Reset to All Clinics
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl">
              <Layers className="w-3.5 h-3.5 text-purple-600" />
              <span className="font-extrabold text-slate-900">HeyJarvis Platform Agency</span>
              <span className="text-gray-400">&bull;</span>
              <span className="text-purple-700 font-bold bg-purple-100 px-1.5 py-0.5 rounded text-[10px]">ALL PRACTICES</span>
            </div>
          )
        ) : (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl">
            <Layers className="w-3.5 h-3.5 text-slate-600" />
            <span className="font-extrabold text-slate-900">
              {user?.practice_name || 'Your Practice'}
            </span>
            <span className="text-gray-400">&bull;</span>
            <span className="text-gray-600 font-medium">
              {user?.role ? user.role.replace('_', ' ') : 'Dental Staff'}
            </span>
          </div>
        )}
      </div>

      {/* Right: Quick Embed & Widget Actions + User Profile */}
      <div className="flex items-center gap-2.5">
        {(user?.is_agency_admin || ['ADMIN', 'OWNER', 'PRACTICE_ADMIN', 'AGENCY_ADMIN'].includes(user?.role || '')) && (
          <Link
            to="/dashboard/installation"
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition shadow-sm"
            title="Get live widget snippet and plugin"
          >
            <span>Plugin &amp; Embed</span>
          </Link>
        )}

        {user?.practice_slug && (
        <a
          href={`/concierge/${user.practice_slug}`}
          target="_blank"
          rel="noopener noreferrer"
          className="hidden md:flex items-center gap-1.5 px-3 py-1.5 bg-teal-50 hover:bg-teal-100 text-teal-800 border border-teal-200 rounded-xl text-xs font-bold transition"
          title="Open live patient concierge page"
        >
          <span>Patient Concierge</span>
        </a>
        )}

        {/* User Pill */}
        <div className="flex items-center gap-2 pl-2 border-l border-gray-200">
          <div className="w-8 h-8 bg-slate-900 text-teal-400 rounded-xl flex items-center justify-center font-bold text-xs shadow-sm">
            <User className="w-4 h-4" />
          </div>
          <div className="hidden sm:block text-left">
            <p className="text-xs font-bold text-gray-900 leading-tight">
              {user?.email?.split('@')[0] || 'Front Desk'}
            </p>
            <p className="text-[10px] text-gray-500 font-medium capitalize">
              {user?.role || 'Practice Staff'}
            </p>
          </div>
        </div>

        <button
          onClick={logout}
          className="p-2 rounded-xl hover:bg-gray-100 text-gray-500 hover:text-gray-900 transition-colors"
          title="Sign out of HeyJarvis"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
