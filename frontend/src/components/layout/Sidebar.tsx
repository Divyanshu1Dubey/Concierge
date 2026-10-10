import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Home,
  Bot,
  MessageSquare,
  CalendarCheck,
  Users,
  Building2,
  Settings,
  ShieldCheck,
  Sparkles,
  LogOut,
  Palette,
  Code2,
  Clock,
  Mail,
  FileText,
  UserPlus,
  UserCog,
  LucideIcon
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import ProfileModal from './ProfileModal';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  badge?: string;
  badgeColor?: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

export default function Sidebar({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  // Compute role
  const rawRole = (user?.role || '').toUpperCase();
  const normalizedRole = (user?.normalized_role || '').toUpperCase();

  const isAgencyAdmin = Boolean(
    user?.is_agency_admin ||
    rawRole === 'AGENCY_ADMIN' ||
    normalizedRole === 'AGENCY_ADMIN' ||
    (user as any)?.is_superuser
  );

  const isPracticeAdmin = Boolean(
    isAgencyAdmin ||
    user?.is_practice_admin ||
    ['ADMIN', 'OWNER', 'PRACTICE_ADMIN'].includes(rawRole) ||
    ['ADMIN', 'OWNER', 'PRACTICE_ADMIN'].includes(normalizedRole)
  );

  // Navigation structure based on role
  const navSections: NavSection[] = [
    {
      title: 'MAIN',
      items: [
        { to: '/dashboard', label: 'Home', icon: Home, end: true },
      ],
    },
    ...(isAgencyAdmin
      ? [
          {
            title: 'AGENCY PLATFORM',
            items: [
              { to: '/dashboard/practices', label: 'Dental Practices', icon: Building2, badge: 'All Clinics' },
            ],
          },
        ]
      : []),
    {
      title: 'INBOUND FRONT DESK',
      items: [
        { to: '/dashboard/requests', label: 'Appointment Requests', icon: CalendarCheck, badge: 'Inbox', badgeColor: 'bg-teal-500/20 text-teal-300 border-teal-500/30' },
        { to: '/dashboard/conversations', label: 'Patient Conversations', icon: MessageSquare },
        { to: '/dashboard/leads', label: 'Captured Leads', icon: UserPlus },
        { to: '/dashboard/patients', label: 'Patients Directory', icon: Users },
        { to: '/dashboard/email', label: 'Email Log', icon: Mail },
      ],
    },
    {
      title: 'AI CONCIERGE',
      items: [
        { to: '/dashboard/concierge', label: 'Live AI Concierge', icon: Bot, badge: '24/7 AI', badgeColor: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' },
      ],
    },
    ...(isPracticeAdmin
      ? [
          {
            title: 'INTEGRATIONS & WIDGET',
            items: [
              { to: '/dashboard/installation', label: 'Plugin & Embed Code', icon: Code2, badge: 'WordPress', badgeColor: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
              { to: '/dashboard/widget-settings', label: 'Widget Customizer', icon: Palette },
            ],
          },
          {
            title: 'CLINIC & DENTIST ADMIN',
            items: [
              { to: '/dashboard/business-rules', label: 'Hours & Services', icon: Clock },
              { to: '/dashboard/email-settings', label: 'Email & SMTP Delivery', icon: Mail },
              { to: '/dashboard/templates', label: 'Email Templates', icon: FileText },
              { to: '/dashboard/team', label: 'Dentists & Staff', icon: Users },
              { to: '/dashboard/security', label: 'Security & Audit Logs', icon: ShieldCheck },
              { to: '/dashboard/settings', label: 'Practice Settings', icon: Settings },
            ],
          },
        ]
      : []),
  ];

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 bg-slate-950/40 backdrop-blur-[2px] z-40 lg:hidden" onClick={onClose} aria-hidden="true" />
      )}

      <aside
        aria-label="Main navigation"
        className={`fixed top-0 left-0 z-50 h-screen bg-gray-100 text-gray-800 border-r border-gray-200 transition-transform duration-300 ease-brand lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        } w-64 flex flex-col`}
      >
        {/* Brand Header */}
        <div className="flex items-center gap-3 px-5 h-16 border-b border-gray-200 flex-shrink-0">
          <div className="w-9 h-9 bg-teal-800 rounded-[10px] flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-4 h-4 text-teal-100" aria-hidden="true" />
          </div>
          <div className="truncate leading-tight">
            <span className="font-display text-[19px] text-gray-900 block tracking-tight">HeyJarvis</span>
            <span className="text-[11px] font-medium text-teal-700 block truncate">
              {isAgencyAdmin ? 'Concierge · Agency' : 'Concierge'}
            </span>
          </div>
        </div>

        {/* Current Tenant / Practice Banner */}
        <div className="mx-3 mt-3 px-3 py-2.5 bg-white border border-gray-200 rounded-xl flex items-center justify-between gap-2">
          <div className="truncate">
            <span className="text-[10px] uppercase font-medium tracking-[0.12em] text-gray-500 block">
              {isAgencyAdmin ? 'Platform role' : 'Practice'}
            </span>
            <p className="text-[13px] font-semibold text-gray-900 truncate">
              {isAgencyAdmin ? 'Agency Admin' : user?.practice_name || 'Your Practice'}
            </p>
          </div>
          <span
            className={`text-[10px] font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${
              isAgencyAdmin
                ? 'bg-purple-100 text-purple-800'
                : isPracticeAdmin
                ? 'bg-blue-100 text-blue-800'
                : 'bg-teal-100 text-teal-800'
            }`}
          >
            {isAgencyAdmin ? 'Agency' : isPracticeAdmin ? 'Admin' : 'Staff'}
          </span>
        </div>

        {/* Navigation Groups */}
        <nav className="flex-1 overflow-y-auto py-5 px-3 space-y-5">
          {navSections.map((group) => (
            <div key={group.title} className="space-y-1">
              <h3 className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-500">
                {group.title}
              </h3>
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        onClick={onClose}
                        className={({ isActive }) =>
                          `relative flex items-center justify-between px-3 py-2 rounded-lg text-[13px] transition-colors duration-200 ${
                            isActive
                              ? 'bg-white text-teal-900 font-semibold shadow-card before:absolute before:left-0 before:top-2 before:bottom-2 before:w-[3px] before:rounded-full before:bg-teal-700'
                              : 'text-gray-700 font-medium hover:bg-gray-200/60 hover:text-gray-900'
                          }`
                        }
                      >
                        <div className="flex items-center gap-2.5">
                          <Icon className="w-4 h-4 flex-shrink-0 opacity-80" aria-hidden="true" />
                          <span>{item.label}</span>
                        </div>
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* User Footer Profile & Logout */}
        <div className="p-3 border-t border-gray-200 flex-shrink-0">
          <div className="flex items-center justify-between gap-2">
            <button
              onClick={() => setIsProfileOpen(true)}
              className="truncate flex-1 text-left group p-1.5 -m-1 rounded-lg hover:bg-gray-200/60 transition"
              title="Click to change your name & edit profile"
            >
              <div className="flex items-center gap-1.5">
                <p className="text-[13px] font-semibold text-gray-900 group-hover:text-teal-800 transition truncate">
                  {user?.full_name || user?.first_name || user?.email || 'Logged User'}
                </p>
                <UserCog className="w-3 h-3 text-gray-400 group-hover:text-teal-700 transition flex-shrink-0" aria-hidden="true" />
              </div>
              <p className="text-[11px] text-gray-500 truncate">{user?.email}</p>
            </button>
            <button
              onClick={() => logout()}
              className="p-2 hover:bg-gray-200/60 text-gray-500 hover:text-red-700 rounded-lg transition"
              title="Sign Out"
              aria-label="Sign out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      <ProfileModal isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} />
    </>
  );
}
