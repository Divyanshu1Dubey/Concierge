import { useQuery } from '@tanstack/react-query';
import { patientsApi } from '@/services/api';
import { Users, Search } from 'lucide-react';
import { useEffect, useState } from 'react';

export default function PatientsPage() {
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['patients', debounced],
    queryFn: () => patientsApi.getAll(debounced ? { search: debounced } : undefined),
  });

  // Patients are derived from requests: collapse repeat requests from the same person.
  const requests: any[] = Array.isArray(data) ? data : (data?.results ?? []);
  const seen = new Map<string, any>();
  for (const r of requests) {
    const key = (r.patient_email || r.patient_phone || r.id || '').toString().toLowerCase();
    const existing = seen.get(key);
    if (existing) existing._requestCount += 1;
    else seen.set(key, { ...r, _requestCount: 1 });
  }
  const patients: any[] = Array.from(seen.values());

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Patients</h1>
          <p className="text-gray-500 mt-1">People who have contacted the practice through the concierge.</p>
        </div>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search patients..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200">
        {isLoading ? (
          <div className="p-12 text-center">
            <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-gray-500 mt-3">Loading patients...</p>
          </div>
        ) : isError ? (
          <div className="p-12 text-center text-sm text-red-600">Could not load patients.</div>
        ) : patients.length === 0 ? (
          <div className="p-12 text-center">
            <Users className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No patients yet</p>
            <p className="text-sm text-gray-400 mt-1">Patients will appear here as they interact</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Email</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Phone</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Added</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {patients.map((patient: any) => (
                  <tr key={patient.id} className="hover:bg-gray-50">
                    <td className="px-6 py-3 text-sm font-medium text-gray-900">{patient.patient_name || patient.name || 'Anonymous Patient'}</td>
                    <td className="px-6 py-3 text-sm text-gray-600">{patient.patient_email || patient.email || '—'}</td>
                    <td className="px-6 py-3 text-sm text-gray-600">{patient.patient_phone || patient.phone || '—'}</td>
                    <td className="px-6 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        patient.intent === 'new_patient'
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-emerald-100 text-emerald-700'
                      }`}>
                        {patient.intent === 'new_patient' ? 'New Patient' : 'Returning'}
                      </span>
                      {patient._requestCount > 1 && (
                        <span className="ml-2 text-xs text-gray-400">{patient._requestCount} requests</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-500">
                      {patient.created_at ? new Date(patient.created_at).toLocaleDateString() : 'Recent'}
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
