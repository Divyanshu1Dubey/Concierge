import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { leadsApi } from '@/services/api';
import { UserPlus, Search } from 'lucide-react';
import { useEffect, useState } from 'react';

export default function LeadsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['leads', debounced],
    queryFn: () => leadsApi.getAll(debounced ? { search: debounced } : undefined),
  });

  const leads: any[] = Array.isArray(data) ? data : (data?.results ?? []);

  const getStatusColor = (status: string) => {
    const s = (status || '').toUpperCase();
    const colors: Record<string, string> = {
      NEW: 'bg-blue-100 text-blue-700',
      CONTACTED: 'bg-yellow-100 text-yellow-700',
      QUALIFIED: 'bg-emerald-100 text-emerald-700',
      APPOINTMENT_REQUESTED: 'bg-purple-100 text-purple-700',
      PENDING: 'bg-yellow-100 text-yellow-700',
      BOOKED: 'bg-indigo-100 text-indigo-700',
      CONFIRMED: 'bg-green-100 text-green-700',
      CONVERTED: 'bg-green-100 text-green-700',
      LOST: 'bg-red-100 text-red-700',
    };
    return colors[s] || 'bg-gray-100 text-gray-700';
  };

  const getSourceLabel = (source: string) => {
    return (source || 'website_widget').replace(/_/g, ' ');
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Leads</h1>
        <p className="text-gray-500 mt-1">Track and manage leads captured from widget and concierge conversations.</p>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search leads..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200">
        {isLoading ? (
          <div className="p-12 text-center">
            <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-gray-500 mt-3">Loading leads...</p>
          </div>
        ) : isError ? (
          <div className="p-12 text-center text-sm text-red-600">Could not load leads.</div>
        ) : leads.length === 0 ? (
          <div className="p-12 text-center">
            <UserPlus className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No leads yet</p>
            <p className="text-sm text-gray-400 mt-1">Leads will appear when patients share contact info via the widget</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Patient Name</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Email / Contact</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Intent / Service</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Source</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {leads.map((lead: any) => (
                  <tr key={lead.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => navigate(`/dashboard/requests/${lead.id}`)}>
                    <td className="px-6 py-3 text-sm font-medium text-gray-900">
                      {lead.patient_name || lead.name || 'Anonymous Patient'}
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-600">
                      <div>{lead.patient_email || lead.email || '—'}</div>
                      {lead.patient_phone && <div className="text-xs text-gray-400">{lead.patient_phone}</div>}
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-600 capitalize">
                      {lead.intent || lead.service_name || lead.service || 'General Inquiry'}
                    </td>
                    <td className="px-6 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(lead.status)}`}>
                        {lead.status || 'NEW'}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-600 capitalize">{getSourceLabel(lead.source || 'Website Widget')}</td>
                    <td className="px-6 py-3 text-sm text-gray-500">
                      {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : 'Just now'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
