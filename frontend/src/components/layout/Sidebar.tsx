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
  BookOpen,
  LucideIcon
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';

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
              { to: '/dashboard/settings', label: 'Platform Settings', icon: Settings },
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
        { to: '/dashboard/knowledge', label: 'Knowledge Base', icon: BookOpen },
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
              { to: '/dashboard/security', label: 'HIPAA & Audit Logs', icon: ShieldCheck },
              { to: '/dashboard/settings', label: 'Practice Settings', icon: Settings },
            ],
          },
        ]
      : []),
  ];

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-40 lg:hidden" onClick={onClose} />
      )}

      <aside
        className={`fixed top-0 left-0 z-50 h-screen bg-slate-950 text-slate-100 border-r border-slate-800/80 transition-all duration-300 lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        } w-64 flex flex-col`}
      >
        {/* Brand Header */}
        <div className="flex items-center gap-3 px-5 h-16 border-b border-slate-800/80 flex-shrink-0 bg-slate-950">
          <div className="p-2 bg-gradient-to-br from-teal-400 via-teal-500 to-cyan-500 rounded-xl shadow-md flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-slate-950 font-black" />
          </div>
          <div className="truncate">
            <div className="flex items-center gap-1.5">
              <span className="text-base font-black tracking-tight text-white block">HeyJarvis</span>
              <span className="text-[9px] font-black px-1.5 py-0.2 rounded bg-teal-500/20 text-teal-300 border border-teal-500/30">
                AI
              </span>
            </div>
            <span className="text-[10px] font-bold text-teal-400 uppercase tracking-widest block truncate">
              {isAgencyAdmin ? 'Agency Cloud' : 'Dental Concierge'}
            </span>
          </div>
        </div>

        {/* Current Tenant / Practice Banner */}
        <div className="px-4 py-3 bg-slate-900/70 border-b border-slate-800/70 flex items-center justify-between">
          <div className="truncate">
            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block">
              {isAgencyAdmin ? 'Platform Role' : 'Active Practice'}
            </span>
            <p className="text-xs font-bold text-white truncate">
              {isAgencyAdmin ? 'Agency Admin' : user?.practice_name || 'Raleigh Dentistry'}
            </p>
          </div>
          <span
            className={`text-[9px] font-extrabold px-1.5 py-0.5 rounded border ${
              isAgencyAdmin
                ? 'bg-purple-500/20 text-purple-300 border-purple-500/30'
                : isPracticeAdmin
                ? 'bg-blue-500/20 text-blue-300 border-blue-500/30'
                : 'bg-teal-500/20 text-teal-300 border-teal-500/30'
            }`}
          >
            {isAgencyAdmin ? 'AGENCY' : isPracticeAdmin ? 'ADMIN' : 'STAFF'}
          </span>
        </div>

        {/* Navigation Groups */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-6">
          {navSections.map((group) => (
            <div key={group.title} className="space-y-1">
              <h3 className="px-3 text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
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
                          `flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition-all ${
                            isActive
                              ? 'bg-teal-500 text-slate-950 font-bold shadow-md'
                              : 'text-slate-300 hover:bg-slate-900 hover:text-white'
                          }`
                        }
                      >
                        <div className="flex items-center gap-2.5">
                          <Icon className="w-4 h-4 flex-shrink-0" />
                          <span>{item.label}</span>
                        </div>
                        {item.badge && (
                          <span
                            className={`text-[10px] font-extrabold px-1.5 py-0.5 rounded border ${
                              item.badgeColor || 'bg-slate-800 text-teal-300 border-slate-700'
                            }`}
                          >
                            {item.badge}
                          </span>
                        )}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* User Footer Profile & Logout */}
        <div className="p-3 border-t border-slate-800/80 flex-shrink-0 bg-slate-900/80">
          <div className="flex items-center justify-between gap-2">
            <div className="truncate flex-1">
              <p className="text-xs font-bold text-white truncate">
                {user?.full_name || user?.first_name || user?.email || 'Logged User'}
              </p>
              <p className="text-[10px] text-slate-400 truncate">{user?.email}</p>
            </div>
            <button
              onClick={() => logout()}
              className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-rose-400 rounded-lg transition"
              title="Sign Out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
