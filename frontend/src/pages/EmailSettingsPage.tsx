import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { practicesApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';
import {
  Mail, Server, ShieldCheck, Send, Save, Check, AlertCircle, CheckCircle2
} from 'lucide-react';

export default function EmailSettingsPage() {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const [testResult, setTestResult] = useState<{ success?: boolean; message?: string } | null>(null);

  // Form State
  const [providerType, setProviderType] = useState<'MANAGED' | 'SMTP'>('MANAGED');
  const [fromName, setFromName] = useState('');
  const [fromEmail, setFromEmail] = useState('');
  const [replyTo, setReplyTo] = useState('');

  // SMTP Settings
  const [smtpHost, setSmtpHost] = useState('');
  const [smtpPort, setSmtpPort] = useState(587);
  const [smtpUsername, setSmtpUsername] = useState('');
  const [smtpPassword, setSmtpPassword] = useState('');
  const [useTls, setUseTls] = useState(true);
  const [useSsl, setUseSsl] = useState(false);

  // Routing Destinations
  const [leadNotificationEmail, setLeadNotificationEmail] = useState('');
  const [emergencyNotificationEmail, setEmergencyNotificationEmail] = useState('');
  const [appointmentNotificationEmail, setAppointmentNotificationEmail] = useState('');
  const [handoffNotificationEmail, setHandoffNotificationEmail] = useState('');

  const { data: configData, isLoading, isError } = useQuery({
    queryKey: ['emailConfig'],
    queryFn: () => practicesApi.emailConfig(),
  });
  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: () => practicesApi.settings(),
  });

  useEffect(() => {
    const c = configData;
    if (!c) return;
    setProviderType((c.provider_type || 'managed').toUpperCase() === 'SMTP' ? 'SMTP' : 'MANAGED');
    setFromName(c.from_name ?? '');
    setFromEmail(c.from_email ?? '');
    setReplyTo(c.reply_to ?? '');
    setSmtpHost(c.smtp_host ?? '');
    if (c.smtp_port) setSmtpPort(Number(c.smtp_port));
    setSmtpUsername(c.smtp_username ?? '');
    setUseTls(c.smtp_use_tls !== false);
    setUseSsl(Boolean(c.smtp_use_ssl));
  }, [configData]);

  useEffect(() => {
    const n = settingsData?.notification_emails || {};
    setLeadNotificationEmail(n.general ?? '');
    setEmergencyNotificationEmail(n.emergency ?? '');
    setAppointmentNotificationEmail(n.appointment ?? '');
    setHandoffNotificationEmail(n.handoff ?? '');
  }, [settingsData]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        provider_type: providerType.toLowerCase(),
        from_name: fromName,
        from_email: fromEmail,
        reply_to: replyTo,
        smtp_host: smtpHost,
        smtp_port: smtpPort,
        smtp_username: smtpUsername,
        smtp_use_tls: useTls,
        smtp_use_ssl: useSsl,
      };
      // Only send a password when the admin typed a new one; it is encrypted at rest server-side.
      if (smtpPassword) payload.smtp_password = smtpPassword;
      await practicesApi.updateEmailConfig(payload);
      await practicesApi.updateSettings({
        notification_emails: {
          general: leadNotificationEmail,
          emergency: emergencyNotificationEmail,
          appointment: appointmentNotificationEmail,
          handoff: handoffNotificationEmail,
        },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emailConfig'] });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setSmtpPassword('');
      toast.success('Email settings saved');
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not save email settings.')),
  });

  // The test endpoint reports failures in the body ({success: false}); never treat 200 as success.
  const testMutation = useMutation({
    mutationFn: () => practicesApi.testEmail(),
    onSuccess: (res: any) => {
      setTestResult({ success: Boolean(res?.success), message: res?.message || (res?.success ? 'Connection successful.' : 'Connection failed.') });
      queryClient.invalidateQueries({ queryKey: ['emailConfig'] });
    },
    onError: (err: any) => {
      setTestResult({ success: false, message: apiErrorMessage(err, 'Test connection failed.') });
    },
  });

  const handleSave = () => {
    if (providerType === 'SMTP' && (!smtpHost || !smtpPort)) {
      toast.error('SMTP host and port are required for custom SMTP.');
      return;
    }
    saveMutation.mutate();
  };

  if (isLoading) return <div className="p-8 text-sm text-gray-500">Loading email settings…</div>;
  if (isError) return <div className="p-8 text-sm text-red-600">Could not load email settings. Please refresh the page.</div>;

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Email & Notification Settings</h1>
          <p className="text-gray-500 mt-1">Configure SMTP delivery, managed sender routing, and staff alert emails.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => testMutation.mutate()}
            disabled={testMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 rounded-xl text-sm font-semibold transition"
          >
            <Send className="w-4 h-4 text-teal-600" />
            {testMutation.isPending ? 'Testing...' : 'Test Connection'}
          </button>
          <button
            onClick={handleSave}
            disabled={saveMutation.isPending}
            className="flex items-center gap-2 px-6 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-sm font-semibold transition shadow-sm"
          >
            {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
            {saved ? 'Saved!' : saveMutation.isPending ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>

      {/* Test Result Alert */}
      {testResult && (
        <div className={`p-4 rounded-xl border flex items-center gap-3 text-sm ${
          testResult.success ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-800'
        }`}>
          {testResult.success ? <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" /> : <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0" />}
          <span>{testResult.message}</span>
        </div>
      )}

      {/* Provider Selector Card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
          <Mail className="w-5 h-5 text-teal-600" />
          Email Delivery Engine
        </h2>

        <div className="grid sm:grid-cols-2 gap-4">
          <label className={`p-4 rounded-xl border-2 cursor-pointer flex items-start gap-3 transition ${
            providerType === 'MANAGED' ? 'border-teal-600 bg-teal-50/30' : 'border-gray-200 hover:bg-gray-50'
          }`}>
            <input
              type="radio"
              name="provider"
              value="MANAGED"
              checked={providerType === 'MANAGED'}
              onChange={() => setProviderType('MANAGED')}
              className="mt-1 text-teal-600"
            />
            <div>
              <span className="font-bold text-sm text-gray-900 block">HeyJarvis Managed Email</span>
              <p className="text-xs text-gray-500 mt-1">
                Zero configuration required. Notifications sent reliably via our high-reputation transactional delivery cluster.
              </p>
              <span className="inline-block mt-2 text-[10px] font-bold uppercase bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full">
                ACTIVE & READY
              </span>
            </div>
          </label>

          <label className={`p-4 rounded-xl border-2 cursor-pointer flex items-start gap-3 transition ${
            providerType === 'SMTP' ? 'border-teal-600 bg-teal-50/30' : 'border-gray-200 hover:bg-gray-50'
          }`}>
            <input
              type="radio"
              name="provider"
              value="SMTP"
              checked={providerType === 'SMTP'}
              onChange={() => setProviderType('SMTP')}
              className="mt-1 text-teal-600"
            />
            <div>
              <span className="font-bold text-sm text-gray-900 block">Custom Practice SMTP</span>
              <p className="text-xs text-gray-500 mt-1">
                Send emails directly from your own practice email server (e.g. Google Workspace, Office 365, SendGrid).
              </p>
              <span className="inline-block mt-2 text-[10px] font-bold uppercase bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">
                CUSTOM DOMAIN
              </span>
            </div>
          </label>
        </div>
      </div>

      {/* Custom SMTP Configuration (Visible if SMTP selected) */}
      {providerType === 'SMTP' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <Server className="w-5 h-5 text-indigo-600" />
              SMTP Server Details
            </h2>
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              Credentials encrypted at rest (AES-256)
            </div>
          </div>

          <div className="grid sm:grid-cols-3 gap-4">
            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-gray-700 block mb-1">SMTP Host</label>
              <input
                type="text"
                placeholder="smtp.gmail.com or smtp.office365.com"
                value={smtpHost}
                onChange={(e) => setSmtpHost(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">SMTP Port</label>
              <input
                type="number"
                value={smtpPort}
                onChange={(e) => setSmtpPort(Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              />
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Username / Email</label>
              <input
                type="text"
                value={smtpUsername}
                onChange={(e) => setSmtpUsername(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Password / App Password</label>
              <input
                type="password"
                placeholder={configData?.has_password ? 'Saved — leave blank to keep' : '••••••••••••'}
                autoComplete="new-password"
                value={smtpPassword}
                onChange={(e) => setSmtpPassword(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              />
            </div>
          </div>

          <div className="flex gap-6 pt-2">
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={useTls}
                onChange={(e) => setUseTls(e.target.checked)}
                className="w-4 h-4 text-teal-600 rounded"
              />
              Use TLS (Port 587)
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={useSsl}
                onChange={(e) => setUseSsl(e.target.checked)}
                className="w-4 h-4 text-teal-600 rounded"
              />
              Use SSL (Port 465)
            </label>
          </div>
        </div>
      )}

      {/* Sender Header Details */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-gray-900">Outbound Email Headers</h2>

        <div className="grid sm:grid-cols-3 gap-4">
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">From Name</label>
            <input
              type="text"
              value={fromName}
              onChange={(e) => setFromName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">From Email Address</label>
            <input
              type="email"
              value={fromEmail}
              onChange={(e) => setFromEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">Reply-To Address</label>
            <input
              type="email"
              value={replyTo}
              onChange={(e) => setReplyTo(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
        </div>
      </div>

      {/* Staff Notification Routing Destinations */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-gray-900">Notification Routing Destinations</h2>
        <p className="text-xs text-gray-500">Route alerts to different staff members or inboxes based on request intent.</p>

        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">New Patient Leads</label>
            <input
              type="email"
              value={leadNotificationEmail}
              onChange={(e) => setLeadNotificationEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-red-700 block mb-1">Emergency Triage Alerts</label>
            <input
              type="email"
              value={emergencyNotificationEmail}
              onChange={(e) => setEmergencyNotificationEmail(e.target.value)}
              className="w-full px-3 py-2 border border-red-200 bg-red-50/30 rounded-lg text-sm focus:ring-red-500"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">Appointment Requests</label>
            <input
              type="email"
              value={appointmentNotificationEmail}
              onChange={(e) => setAppointmentNotificationEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">Staff Handoff Requests</label>
            <input
              type="email"
              value={handoffNotificationEmail}
              onChange={(e) => setHandoffNotificationEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
