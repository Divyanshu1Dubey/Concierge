import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  User,
  LogOut,
  Layers,
  Menu,
  ExternalLink,
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import ProfileModal from './ProfileModal';

interface HeaderProps {
  onMenuToggle: () => void;
}

// Page context shown in the header (matches the sidebar labels).
const SECTION_TITLES: Record<string, string> = {
  '': 'Overview',
  practices: 'Dental practices',
  requests: 'Appointment requests',
  conversations: 'Patient conversations',
  leads: 'Captured leads',
  patients: 'Patients',
  email: 'Email log',
  messages: 'Email log',
  concierge: 'AI concierge',
  installation: 'Plugin & embed',
  'widget-settings': 'Widget customizer',
  'business-rules': 'Hours & services',
  'email-settings': 'Email delivery',
  templates: 'Email templates',
  team: 'Team',
  security: 'Security & audit log',
  settings: 'Practice settings',
};

export default function Header({ onMenuToggle }: HeaderProps) {
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const { pathname } = useLocation();
  const section = pathname.replace(/^\/dashboard\/?/, '').split('/')[0] || '';
  const sectionTitle = SECTION_TITLES[section] ?? 'Overview';
  const { user, logout, activePracticeId, activePracticeName, setActivePractice } = useAuthStore();

  return (
    <header className="h-16 bg-gray-50/85 backdrop-blur border-b border-gray-200/80 flex items-center justify-between gap-3 px-4 lg:px-8 sticky top-0 z-30">
      {/* Left: mobile menu + page context */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onMenuToggle}
          className="lg:hidden p-2 -ml-2 rounded-lg hover:bg-gray-200/60 text-gray-700"
          aria-label="Open navigation"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-gray-500 leading-none mb-1 hidden sm:block">
            HeyJarvis Concierge
          </p>
          <h2 className="text-[15px] font-semibold text-gray-900 truncate leading-tight">{sectionTitle}</h2>
        </div>
      </div>

      {/* Middle: Practice Info (Desktop) */}
      <div className="hidden lg:flex items-center gap-3 text-xs">
        {user?.is_agency_admin || user?.role === 'AGENCY_ADMIN' ? (
          activePracticeId ? (
            <div className="flex items-center gap-2 pl-3 pr-1.5 py-1 bg-white border border-purple-200 rounded-full text-purple-900">
              <Layers className="w-3.5 h-3.5 text-purple-600" />
              <span className="text-gray-500">Workspace</span>
              <span className="font-semibold text-purple-900">{activePracticeName || 'Selected practice'}</span>
              <button
                onClick={() => {
                  setActivePractice(null, null);
                  window.location.reload();
                }}
                className="ml-1 text-[11px] px-2.5 py-1 rounded-full bg-purple-100 hover:bg-purple-200 text-purple-900 font-semibold transition"
                title="Switch back to Agency Overview of all practices"
              >
                All practices
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-full">
              <Layers className="w-3.5 h-3.5 text-purple-600" />
              <span className="font-semibold text-gray-900">Agency workspace</span>
              <span className="text-gray-300">/</span>
              <span className="text-gray-600">All practices</span>
            </div>
          )
        ) : (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-full max-w-[22rem]">
            <span className="w-1.5 h-1.5 rounded-full bg-teal-500 flex-shrink-0" aria-hidden="true" />
            <span className="font-semibold text-gray-900 truncate">
              {user?.practice_name || 'Your Practice'}
            </span>
          </div>
        )}
      </div>

      {/* Right: Quick Embed & Widget Actions + User Profile */}
      <div className="flex items-center gap-2.5">
        {(user?.is_agency_admin || ['ADMIN', 'OWNER', 'PRACTICE_ADMIN', 'AGENCY_ADMIN'].includes(user?.role || '')) && (
          <Link
            to="/dashboard/installation"
            className="hidden xl:flex items-center gap-1.5 px-3.5 py-2 text-gray-700 hover:text-gray-900 hover:bg-gray-200/60 rounded-full text-xs font-semibold transition"
            title="Get live widget snippet and plugin"
          >
            <span>Plugin &amp; embed</span>
          </Link>
        )}

        {user?.practice_slug && (
        <a
          href={`/concierge/${user.practice_slug}`}
          target="_blank"
          rel="noopener noreferrer"
          className="hidden md:flex items-center gap-1.5 px-3.5 py-2 bg-teal-700 hover:bg-teal-800 text-white rounded-full text-xs font-semibold transition shadow-card"
          title="Open live patient concierge page"
        >
          <span>Patient concierge</span>
          <ExternalLink className="w-3.5 h-3.5 opacity-80" aria-hidden="true" />
        </a>
        )}

        {/* User Pill */}
        <button
          onClick={() => setIsProfileOpen(true)}
          className="flex items-center gap-2.5 pl-3 border-l border-gray-200 text-left transition group"
          title="Click to edit profile / change name"
          aria-label="Edit your profile"
        >
          <div className="w-8 h-8 bg-teal-100 text-teal-800 group-hover:bg-teal-700 group-hover:text-white rounded-full flex items-center justify-center font-semibold text-xs transition">
            {(user?.first_name || user?.email || '?').charAt(0).toUpperCase() || <User className="w-4 h-4" />}
          </div>
          <div className="hidden sm:block text-left">
            <p className="text-xs font-semibold text-gray-900 group-hover:text-teal-700 transition leading-tight truncate max-w-[130px]">
              {user?.full_name || user?.first_name || user?.email?.split('@')[0] || 'Front Desk'}
            </p>
            <p className="text-[11px] text-gray-500 capitalize truncate max-w-[130px]">
              {user?.role ? user.role.replace('_', ' ').toLowerCase() : 'practice staff'}
            </p>
          </div>
        </button>

        <button
          onClick={logout}
          className="p-2 rounded-full hover:bg-gray-200/60 text-gray-500 hover:text-gray-900 transition-colors"
          title="Sign out of HeyJarvis"
          aria-label="Sign out"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>

      <ProfileModal isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} />
    </header>
  );
}
