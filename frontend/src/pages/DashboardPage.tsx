import { useQuery } from '@tanstack/react-query';
import { conversationsApi, requestsApi, practicesApi } from '@/services/api';
import {
  MessageSquare,
  Users,
  CalendarCheck,
  AlertCircle,
  Bot,
  ArrowRight,
  Building2,
  Sparkles,
  Inbox,
  Code2,
  Palette,
  Clock,
  Mail,
  ShieldCheck,
  FileText
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

export default function DashboardPage() {
  const user = useAuthStore((state) => state.user);

  // Time-of-day greeting
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const displayName = user?.first_name || (user?.email ? user.email.split('@')[0] : 'there');

  // Role checks
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

  // Fetch live requests, conversations, and metrics
  // Server-side aggregate counts (lists are paginated, so never count client-side).
  const { data: convStats } = useQuery({
    queryKey: ['conversations-stats'],
    queryFn: () => conversationsApi.stats(),
  });

  const { data: reqStats } = useQuery({
    queryKey: ['requests-stats'],
    queryFn: () => requestsApi.stats(),
  });

  const { data: reqData } = useQuery({
    queryKey: ['appointment-requests'],
    queryFn: () => requestsApi.list(),
  });
  const reqList: any[] = Array.isArray(reqData) ? reqData : (reqData?.results ?? []);

  const { data: metrics } = useQuery({
    queryKey: ['dashboard-metrics'],
    queryFn: () => practicesApi.metrics(),
  });

  const urgentCount = reqStats?.emergency ?? 0;
  const pendingCount = reqStats?.pending ?? 0;
  const activeConvCount = convStats?.active ?? 0;
  const totalConvCount = convStats?.total ?? 0;
  const leadsCount = metrics?.new_leads ?? reqStats?.total ?? 0;
  const emailDelivery: number | null = metrics?.email_delivery ?? null;

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-12">
      {/* Welcome Banner */}
      <div className="pt-2 pb-6 border-b border-gray-200 flex flex-col md:flex-row md:items-end justify-between gap-6 animate-rise">

        <div className="space-y-3">
          <div className="eyebrow">
            <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
            <span>{isAgencyAdmin ? 'Agency Cloud Platform' : metrics?.practice_name || user?.practice_name || 'Your Practice'}</span>
          </div>
          <h1 className="text-[34px] sm:text-[40px] leading-[1.1] font-normal text-gray-900">
            {greeting}, {displayName}.
          </h1>
          <p className="text-gray-600 text-[15px] max-w-xl leading-relaxed">
            {isAgencyAdmin
              ? 'An overview of patient activity across the dental practices you manage.'
              : 'Here is what needs your attention at the front desk today.'}
          </p>
        </div>

        <div className="flex flex-wrap gap-2.5">
          <Link
            to="/dashboard/requests"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-800 hover:bg-teal-900 text-white rounded-full text-sm font-semibold shadow-card transition"
          >
            <Inbox className="w-4 h-4" aria-hidden="true" />
            Open inbox
          </Link>
          <Link
            to="/dashboard/concierge"
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-white hover:bg-gray-100 text-gray-900 rounded-full text-sm font-semibold border border-gray-200 transition"
          >
            <Bot className="w-4 h-4" aria-hidden="true" />
            Preview concierge
          </Link>
          {isPracticeAdmin && (
            <Link
              to="/dashboard/installation"
              className="inline-flex items-center gap-2 px-4 py-2.5 text-gray-700 hover:text-gray-900 hover:bg-gray-200/60 rounded-full text-sm font-semibold transition"
            >
              <Code2 className="w-4 h-4" aria-hidden="true" />
              Website embed
            </Link>
          )}
        </div>
      </div>

      {/* Today's Key Focus Metrics */}
      <div>
        <h2 className="eyebrow text-gray-500 mb-4">
          Today's Activity &amp; Queue
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <Link
            to="/dashboard/requests"
            className="bg-white p-5 rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-teal-300 transition-all group"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Pending Requests
              </span>
              <CalendarCheck className="w-5 h-5 text-teal-600 transition-colors" />
            </div>
            <p className="text-[32px] font-display text-gray-900 mt-3 leading-none">{pendingCount}</p>
            <p className="text-xs text-gray-500 mt-1 flex items-center gap-1">
              <span>Awaiting review</span>
            </p>
          </Link>

          <Link
            to="/dashboard/requests"
            className="bg-white p-5 rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-red-300 transition-all group"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Needs Attention
              </span>
              <AlertCircle className={`w-5 h-5 ${urgentCount > 0 ? 'text-red-600' : 'text-gray-400'} transition-colors`} />
            </div>
            <p className={`text-[32px] font-display mt-3 leading-none ${urgentCount > 0 ? 'text-red-600' : 'text-gray-900'}`}>
              {urgentCount}
            </p>
            <p className="text-xs text-gray-500 mt-1">Urgent triage items</p>
          </Link>

          <Link
            to="/dashboard/conversations"
            className="bg-white p-5 rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-purple-300 transition-all group"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Conversations
              </span>
              <MessageSquare className="w-5 h-5 text-purple-600 transition-colors" />
            </div>
            <p className="text-[32px] font-display text-gray-900 mt-3 leading-none">{totalConvCount}</p>
            <p className="text-xs text-purple-600 font-medium mt-1">
              {activeConvCount} active visitors
            </p>
          </Link>

          <Link
            to="/dashboard/leads"
            className="bg-white p-5 rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-blue-300 transition-all group"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Captured Leads
              </span>
              <Users className="w-5 h-5 text-blue-600 transition-colors" />
            </div>
            <p className="text-[32px] font-display text-gray-900 mt-3 leading-none">{leadsCount}</p>
            <p className="text-xs text-blue-600 font-medium mt-1">Ready for outreach</p>
          </Link>

          {isPracticeAdmin && (
          <Link
            to="/dashboard/email-settings"
            className="bg-white p-5 rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-cyan-300 transition-all group"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Email Delivery
              </span>
              <Mail className="w-5 h-5 text-cyan-600 transition-colors" />
            </div>
            <p className="text-[32px] font-display text-gray-900 mt-3 leading-none">{emailDelivery === null ? '—' : `${emailDelivery}%`}</p>
            <p className="text-xs text-cyan-600 font-medium mt-1">
              {emailDelivery === null ? 'No emails sent yet' : `${metrics?.emails_sent ?? 0} sent · ${metrics?.emails_failed ?? 0} failed`}
            </p>
          </Link>
          )}
        </div>
      </div>

      {/* Quick Actions Grid */}
      <div>
        <h2 className="eyebrow text-gray-500 mb-4">
          Front Desk Workflows
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link
            to="/dashboard/requests"
            className="p-5 bg-white rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-gray-300 transition flex items-start gap-3.5"
          >
            <div className="w-10 h-10 rounded-xl bg-teal-50 border border-teal-200 flex items-center justify-center flex-shrink-0 text-teal-700">
              <Inbox className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-gray-900">Appointment Requests</h3>
              <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                Review appointment inquiries, triage symptoms, and reply to patients.
              </p>
            </div>
          </Link>

          <Link
            to="/dashboard/conversations"
            className="p-5 bg-white rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-gray-300 transition flex items-start gap-3.5"
          >
            <div className="w-10 h-10 rounded-xl bg-purple-50 border border-purple-200 flex items-center justify-center flex-shrink-0 text-purple-700">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-gray-900">Patient Conversations</h3>
              <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                Inspect AI concierge chats, takeover conversations, and send direct replies.
              </p>
            </div>
          </Link>

          <Link
            to="/dashboard/leads"
            className="p-5 bg-white rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-gray-300 transition flex items-start gap-3.5"
          >
            <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-200 flex items-center justify-center flex-shrink-0 text-blue-700">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-gray-900">Captured Leads</h3>
              <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                High-intent website visitors ready for appointment scheduling outreach.
              </p>
            </div>
          </Link>

          <Link
            to="/dashboard/concierge"
            className="p-5 bg-white rounded-card border border-gray-200 shadow-card hover:shadow-lift hover:border-gray-300 transition flex items-start gap-3.5"
          >
            <div className="w-10 h-10 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center flex-shrink-0 text-emerald-700">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-gray-900">Live AI Concierge</h3>
              <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                24/7 web concierge preview, practice clinical guidelines, and FAQs.
              </p>
            </div>
          </Link>
        </div>
      </div>

      {/* Integrations & Practice Admin Hub */}
      {isPracticeAdmin && (
        <div className="bg-white p-6 rounded-card border border-gray-200 space-y-4 shadow-card">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Code2 className="w-5 h-5 text-teal-700" />
                <h3 className="text-base font-semibold text-gray-900">Integrations &amp; Practice Admin Hub</h3>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Website plugin, script embed, operating hours, SMTP delivery, and staff management.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-2">
            <Link
              to="/dashboard/installation"
              className="p-3.5 bg-gray-50 hover:bg-white border border-gray-200 hover:border-teal-300 hover:shadow-card rounded-xl transition group text-left block"
            >
              <Code2 className="w-5 h-5 text-teal-700 mb-2 transition-colors" />
              <div className="text-[13px] font-semibold text-gray-900">WordPress &amp; Embed</div>
              <div className="text-[10px] text-gray-500 mt-0.5">Plugin ZIP &amp; JS tag</div>
            </Link>

            {isAgencyAdmin && (
              <Link
                to="/dashboard/practices"
                className="p-3.5 bg-gray-50 hover:bg-white border border-gray-200 hover:border-blue-300 hover:shadow-card rounded-xl transition group text-left block"
              >
                <Building2 className="w-5 h-5 text-blue-600 mb-2 transition-colors" />
                <div className="text-[13px] font-semibold text-gray-900">Dental Clinics</div>
                <div className="text-[10px] text-gray-500 mt-0.5">All Practices</div>
              </Link>
            )}

            <Link
              to="/dashboard/widget-settings"
              className="p-3.5 bg-gray-50 hover:bg-white border border-gray-200 hover:border-teal-300 hover:shadow-card rounded-xl transition group text-left block"
            >
              <Palette className="w-5 h-5 text-cyan-700 mb-2 transition-colors" />
              <div className="text-[13px] font-semibold text-gray-900">Widget Customizer</div>
              <div className="text-[10px] text-gray-500 mt-0.5">Colors &amp; greeting</div>
            </Link>

            <Link
              to="/dashboard/business-rules"
              className="p-3.5 bg-gray-50 hover:bg-white border border-gray-200 hover:border-teal-300 hover:shadow-card rounded-xl transition group text-left block"
            >
              <Clock className="w-5 h-5 text-purple-600 mb-2 transition-colors" />
              <div className="text-[13px] font-semibold text-gray-900">Hours &amp; Services</div>
              <div className="text-[10px] text-gray-500 mt-0.5">Schedule rules</div>
            </Link>

            <Link
              to="/dashboard/email-settings"
              className="p-3.5 bg-gray-50 hover:bg-white border border-gray-200 hover:border-teal-300 hover:shadow-card rounded-xl transition group text-left block"
            >
              <Mail className="w-5 h-5 text-blue-600 mb-2 transition-colors" />
              <div className="text-[13px] font-semibold text-gray-900">Email &amp; SMTP</div>
              <div className="text-[10px] text-gray-500 mt-0.5">Inbox delivery</div>
            </Link>

            <Link
              to="/dashboard/templates"
              className="p-3.5 bg-gray-50 hover:bg-white border border-gray-200 hover:border-teal-300 hover:shadow-card rounded-xl transition group text-left block"
            >
              <FileText className="w-5 h-5 text-indigo-400 mb-2 transition-colors" />
              <div className="text-[13px] font-semibold text-gray-900">Email Templates</div>
              <div className="text-[10px] text-gray-500 mt-0.5">Quick responses</div>
            </Link>

            <Link
              to="/dashboard/team"
              className="p-3.5 bg-gray-50 hover:bg-white border border-gray-200 hover:border-teal-300 hover:shadow-card rounded-xl transition group text-left block"
            >
              <Users className="w-5 h-5 text-amber-600 mb-2 transition-colors" />
              <div className="text-[13px] font-semibold text-gray-900">Dentists &amp; Staff</div>
              <div className="text-[10px] text-gray-500 mt-0.5">Users &amp; roles</div>
            </Link>

            <Link
              to="/dashboard/security"
              className="p-3.5 bg-gray-50 hover:bg-white border border-gray-200 hover:border-teal-300 hover:shadow-card rounded-xl transition group text-left block"
            >
              <ShieldCheck className="w-5 h-5 text-emerald-600 mb-2 transition-colors" />
              <div className="text-[13px] font-semibold text-gray-900">HIPAA &amp; Audit</div>
              <div className="text-[10px] text-gray-500 mt-0.5">Security logs</div>
            </Link>
          </div>
        </div>
      )}

      {/* Recent Activity List */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-gray-900">Recent Patient Inquiries</h3>
            <p className="text-xs text-gray-500 mt-0.5">Latest requests captured by HeyJarvis AI Concierge</p>
          </div>
          <Link
            to="/dashboard/requests"
            className="text-xs font-semibold text-teal-600 hover:text-teal-700 flex items-center gap-1"
          >
            View all <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {reqList.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-sm">
            No inquiries recorded yet. Patient requests submitted via the concierge widget will appear here.
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {reqList.slice(0, 5).map((req: any) => (
              <div
                key={req.id}
                className="p-4 hover:bg-gray-50/80 transition-colors flex items-center justify-between gap-4"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700 font-bold text-xs">
                    {(req.patient_name || req.patient_email || 'P').charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-gray-900">
                        {req.patient_name || 'Guest Patient'}
                      </span>
                      {req.urgency === 'URGENT' && (
                        <span className="px-2 py-0.2 rounded-full text-[10px] font-bold bg-red-100 text-red-700">
                          URGENT
                        </span>
                      )}
                      <span className="px-2 py-0.2 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-600 capitalize">
                        {req.intent || 'Appointment'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5 truncate max-w-md">
                      {req.patient_email} • Prefers: {req.preferred_date || 'Flexible'} ({req.preferred_time || 'Anytime'})
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      req.status === 'confirmed'
                        ? 'bg-emerald-100 text-emerald-700'
                        : req.status === 'contacted'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-amber-100 text-amber-700'
                    }`}
                  >
                    {req.status?.toUpperCase() || 'PENDING'}
                  </span>
                  <Link
                    to={`/dashboard/requests/${req.id}`}
                    className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400 hover:text-gray-600 transition"
                  >
                    <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
