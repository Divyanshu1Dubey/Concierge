import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { requestsApi } from '@/services/api';
import {
  CalendarCheck, Search, AlertTriangle, ArrowRight,
  Filter
} from 'lucide-react';

export default function RequestsPage() {
  const [activeTab, setActiveTab] = useState('all');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const { data: stats } = useQuery({
    queryKey: ['requests-stats'],
    queryFn: () => requestsApi.stats(),
  });

  const { data: requestsData, isLoading } = useQuery({
    queryKey: ['appointment-requests', activeTab, statusFilter, search],
    queryFn: () => {
      const params: Record<string, string> = {};
      if (activeTab !== 'all') {
        if (activeTab === 'new') params.status = 'pending';
        else if (activeTab === 'emergency') params.urgency = 'URGENT';
        else params.intent = activeTab;
      }
      if (statusFilter) params.status = statusFilter;
      if (search) params.search = search;
      return requestsApi.list(params);
    },
  });

  const requests = (requestsData as any[]) || [];

  const tabs = [
    { id: 'all', label: 'All Requests', count: stats?.total ?? 0 },
    { id: 'new', label: 'New Requests', count: stats?.pending ?? 0 },
    { id: 'emergency', label: 'Emergency', count: stats?.emergency ?? 0, isUrgent: true },
    { id: 'appointment', label: 'Appointments', count: stats?.appointment ?? 0 },
    { id: 'question', label: 'Questions', count: stats?.question ?? 0 },
    { id: 'reschedule', label: 'Reschedule', count: stats?.reschedule ?? 0 },
    { id: 'cancel', label: 'Cancellations', count: stats?.cancel ?? 0 },
    { id: 'handoff', label: 'Staff Handoffs', count: stats?.handoff ?? 0 },
  ];

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'confirmed':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800">Confirmed</span>;
      case 'contacted':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">Contacted</span>;
      case 'cancelled':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800">Cancelled</span>;
      case 'completed':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-100 text-purple-800">Completed</span>;
      default:
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">Pending Review</span>;
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header & Subtitle */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Front Desk Command Center</h1>
        <p className="text-gray-500 mt-1">
          Review, triage, and respond to incoming patient requests with 1-click AI drafts.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 overflow-x-auto">
        <nav className="flex space-x-2 -mb-px">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-3 px-3.5 border-b-2 font-medium text-xs whitespace-nowrap flex items-center gap-1.5 transition ${
                  isActive
                    ? 'border-teal-600 text-teal-700 font-semibold'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.isUrgent && <AlertTriangle className="w-3.5 h-3.5 text-red-500" />}
                <span>{tab.label}</span>
                <span
                  className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${
                    tab.isUrgent && tab.count > 0
                      ? 'bg-red-500 text-white font-bold'
                      : isActive
                      ? 'bg-teal-100 text-teal-800 font-bold'
                      : 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Search & Status Filter Controls */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search patient, phone, service..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="w-4 h-4 text-gray-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-xs border border-gray-300 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-teal-500"
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="contacted">Contacted</option>
            <option value="confirmed">Confirmed</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>

      {/* Requests List */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-16 text-center">
            <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-gray-500 text-sm mt-3">Loading requests...</p>
          </div>
        ) : requests.length === 0 ? (
          <div className="p-16 text-center space-y-3">
            <CalendarCheck className="w-12 h-12 text-gray-300 mx-auto" />
            <h3 className="text-base font-semibold text-gray-800">No requests in this view</h3>
            <p className="text-xs text-gray-500 max-w-sm mx-auto">
              New inquiries submitted by patients via your Concierge widget or hosted link will appear here.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {requests.map((req: any) => {
              const isUrgent = req.urgency === 'URGENT' || req.intent === 'emergency';
              return (
                <div
                  key={req.id}
                  className={`p-5 hover:bg-gray-50 transition flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 ${
                    isUrgent ? 'bg-red-50/40' : ''
                  }`}
                >
                  <div className="space-y-1.5 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-gray-900 text-sm">
                        {req.patient_name || req.patient_email || 'Guest Patient'}
                      </span>
                      {isUrgent && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-600 text-white">
                          EMERGENCY
                        </span>
                      )}
                      {getStatusBadge(req.status)}
                      <span className="text-xs text-gray-400 font-mono">
                        {req.confirmation_code}
                      </span>
                    </div>

                    <div className="text-xs text-gray-600 flex items-center gap-4 flex-wrap">
                      <span><strong>Service:</strong> {req.service_title || req.service_name || req.intent}</span>
                      <span><strong>Requested:</strong> {req.preferred_date || 'Flexible'} ({req.preferred_time || 'Any'})</span>
                      {req.patient_phone && <span><strong>Phone:</strong> {req.patient_phone}</span>}
                    </div>

                    {req.ai_summary && (
                      <p className="text-xs text-teal-800 bg-teal-50/80 px-2.5 py-1 rounded inline-block">
                        💡 {req.ai_summary}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
                    <span className="text-[11px] text-gray-400 whitespace-nowrap">
                      {new Date(req.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                    </span>
                    <Link
                      to={`/dashboard/requests/${req.id}`}
                      className="px-3.5 py-2 bg-gradient-to-r from-teal-600 to-cyan-600 hover:from-teal-700 hover:to-cyan-700 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition"
                    >
                      <span>Open & Reply</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
