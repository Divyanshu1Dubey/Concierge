import { useQuery } from '@tanstack/react-query';
import { practicesApi } from '@/services/api';
import {
  ShieldCheck, Download, History, Lock,
  FileSpreadsheet
} from 'lucide-react';

export default function SecurityPage() {
  // Fetch audit logs
  const { data: auditData, isLoading } = useQuery({
    queryKey: ['auditLogs'],
    queryFn: () => practicesApi.auditLogs(),
  });

  const logs: any[] = auditData?.audit_logs || [];

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Security, Audit Trail & Exports</h1>
        <p className="text-gray-500 mt-1">Tenant isolation status, tamper-evident audit history, and data exports.</p>
      </div>

      {/* Security Status Cards */}
      <div className="grid sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <Lock className="w-5 h-5 text-emerald-600" />
            <span className="font-bold text-sm text-gray-900">Tenant Isolation</span>
          </div>
          <p className="text-xs text-gray-500 mb-2">
            All database queries are scoped server-side by practice_id. Cross-tenant leakage is strictly prevented.
          </p>
          <span className="text-[10px] font-bold uppercase bg-emerald-100 text-emerald-800 px-2.5 py-0.5 rounded-full">
            ENFORCED SERVER-SIDE
          </span>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="w-5 h-5 text-teal-600" />
            <span className="font-bold text-sm text-gray-900">Credential Encryption</span>
          </div>
          <p className="text-xs text-gray-500 mb-2">
            Custom SMTP passwords are encrypted at rest using AES-256 and never returned to the frontend.
          </p>
          <span className="text-[10px] font-bold uppercase bg-teal-100 text-teal-800 px-2.5 py-0.5 rounded-full">
            AES-256 ENCRYPTED
          </span>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <Download className="w-5 h-5 text-blue-600" />
            <span className="font-bold text-sm text-gray-900">GDPR / HIPAA Export</span>
          </div>
          <p className="text-xs text-gray-500 mb-2">
            Download your practice data in standard CSV format for offsite compliance backups.
          </p>
          <div className="flex gap-2 mt-2">
            <a
              href="/api/practices/export/leads/"
              download="leads.csv"
              className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 px-2.5 py-1 rounded font-semibold flex items-center gap-1"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-blue-600" />
              Leads CSV
            </a>
            <a
              href="/api/practices/export/conversations/"
              download="conversations.csv"
              className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 px-2.5 py-1 rounded font-semibold flex items-center gap-1"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-teal-600" />
              Conversations CSV
            </a>
          </div>
        </div>
      </div>

      {/* Audit Logs Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
            <History className="w-5 h-5 text-gray-600" />
            Practice Audit Trail
          </h2>
          <span className="text-xs text-gray-400">Strictly redacts secrets, passwords, and tokens</span>
        </div>

        {isLoading ? (
          <div className="p-12 text-center text-gray-400 text-sm">Loading audit trail...</div>
        ) : logs.length === 0 ? (
          <div className="p-12 text-center text-gray-400 text-sm">
            No audit records yet. All sensitive actions will be cataloged here automatically.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Timestamp</th>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Actor</th>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Action</th>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Details</th>
                  <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">IP Address</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 font-mono text-xs">
                {logs.map((log: any) => (
                  <tr key={log.id} className="hover:bg-gray-50 transition font-sans">
                    <td className="px-6 py-3.5 text-gray-500 whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-3.5 font-semibold text-gray-800">
                      {log.user_email || 'System'}
                    </td>
                    <td className="px-6 py-3.5">
                      <span className="font-mono text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded font-bold">
                        {log.action}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-gray-600 max-w-md truncate">
                      {log.details ? JSON.stringify(log.details) : '—'}
                    </td>
                    <td className="px-6 py-3.5 text-gray-400 font-mono text-xs">
                      {log.ip_address || 'Internal'}
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
