import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { practicesApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';
import { useAuthStore } from '@/stores/authStore';
import { Save, Bell, Palette, Globe } from 'lucide-react';

const PRACTICE_FIELDS = ['name', 'phone', 'email', 'timezone', 'address', 'city', 'state', 'zip_code', 'website'] as const;
type PracticeForm = Record<(typeof PRACTICE_FIELDS)[number], string>;

const NOTIFY_TOGGLES: { key: string; label: string; hint?: string }[] = [
  { key: 'notify_on_new_request', label: 'Email alerts for new patient requests', hint: 'Master switch for all request alerts below' },
  { key: 'notify_on_emergency', label: 'Emergency requests' },
  { key: 'notify_on_appointment', label: 'Appointment / new patient / cleaning requests' },
  { key: 'notify_on_question', label: 'General questions' },
  { key: 'notify_on_reschedule', label: 'Reschedule requests' },
  { key: 'notify_on_cancel', label: 'Cancellation requests' },
  { key: 'notify_on_handoff', label: 'Human handoff requests' },
];

const emptyForm = (): PracticeForm =>
  Object.fromEntries(PRACTICE_FIELDS.map((f) => [f, ''])) as PracticeForm;

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { user, setUser, activePracticeId, setActivePractice } = useAuthStore();
  const [form, setForm] = useState<PracticeForm>(emptyForm());
  const [notify, setNotify] = useState<Record<string, boolean>>({});

  const tenantQuery = useQuery({ queryKey: ['tenant'], queryFn: practicesApi.getTenant });
  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: practicesApi.settings });

  useEffect(() => {
    const p = tenantQuery.data;
    if (!p) return;
    setForm(Object.fromEntries(PRACTICE_FIELDS.map((f) => [f, p[f] ?? ''])) as PracticeForm);
  }, [tenantQuery.data]);

  useEffect(() => {
    const s = settingsQuery.data;
    if (!s) return;
    setNotify(Object.fromEntries(NOTIFY_TOGGLES.map(({ key }) => [key, s[key] !== false])));
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const tenant = await practicesApi.updateTenant({ ...form });
      await practicesApi.updateSettings({ ...notify });
      return tenant;
    },
    onSuccess: (tenant: any) => {
      // Reflect a renamed practice immediately in the Header & Sidebar.
      if (tenant?.name) {
        if (activePracticeId && String(tenant.id) === activePracticeId) {
          setActivePractice(activePracticeId, tenant.name);
        } else if (user && (!user.practice || String(user.practice) === String(tenant.id))) {
          setUser({ ...user, practice_name: tenant.name });
        }
      }
      queryClient.invalidateQueries({ queryKey: ['tenant'] });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
      toast.success('Settings saved');
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not save settings.')),
  });

  const handleSave = () => {
    if (!form.name.trim()) return toast.error('Practice name is required.');
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) return toast.error('Enter a valid practice email.');
    if (form.state && form.state.length > 2) return toast.error('Use the 2-letter state code.');
    saveMutation.mutate();
  };

  if (tenantQuery.isLoading || settingsQuery.isLoading) {
    return <div className="p-8 text-sm text-gray-500">Loading settings…</div>;
  }
  if (tenantQuery.isError || settingsQuery.isError) {
    return <div className="p-8 text-sm text-red-600">Could not load practice settings. Please refresh the page.</div>;
  }

  const field = (key: keyof PracticeForm, label: string, opts: { type?: string; span?: boolean; maxLength?: number } = {}) => (
    <div className={opts.span ? 'col-span-2' : ''}>
      <label className="text-sm text-gray-500 block mb-1">{label}</label>
      <input
        type={opts.type || 'text'}
        value={form[key]}
        maxLength={opts.maxLength}
        onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
      />
    </div>
  );

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 mt-1">Manage your practice configuration.</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Globe className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900">Practice Information</h2>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {field('name', 'Practice Name', { maxLength: 255 })}
          {field('phone', 'Phone', { maxLength: 20 })}
          {field('email', 'Email', { type: 'email' })}
          {field('timezone', 'Timezone (e.g. America/New_York)', { maxLength: 50 })}
          {field('website', 'Website', { type: 'url', span: true })}
          {field('address', 'Street Address', { span: true })}
          {field('city', 'City', { maxLength: 100 })}
          <div className="grid grid-cols-2 gap-4">
            {field('state', 'State', { maxLength: 2 })}
            {field('zip_code', 'ZIP', { maxLength: 10 })}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-2">
          <Palette className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900">Widget Customization</h2>
        </div>
        <p className="text-sm text-gray-500">
          Title, colors, greeting and behaviour are managed on the{' '}
          <Link to="/dashboard/widget-settings" className="text-teal-700 underline">Widget Settings</Link> page.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Bell className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900">Staff Notifications</h2>
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Alerts are emailed to the routing addresses configured under{' '}
          <Link to="/dashboard/email-settings" className="text-teal-700 underline">Email Settings</Link> (or the practice email).
        </p>
        <div className="space-y-3">
          {NOTIFY_TOGGLES.map(({ key, label, hint }) => (
            <label key={key} className={`flex items-center justify-between ${key !== 'notify_on_new_request' && !notify.notify_on_new_request ? 'opacity-50' : ''}`}>
              <span className="text-sm text-gray-700">
                {label}
                {hint && <span className="block text-xs text-gray-400">{hint}</span>}
              </span>
              <input
                type="checkbox"
                checked={Boolean(notify[key])}
                disabled={key !== 'notify_on_new_request' && !notify.notify_on_new_request}
                onChange={(e) => setNotify((prev) => ({ ...prev, [key]: e.target.checked }))}
                className="w-4 h-4 text-teal-600 rounded"
              />
            </label>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="flex items-center gap-2 px-6 py-2.5 bg-teal-600 text-white rounded-lg text-sm font-medium hover:bg-teal-700 disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {saveMutation.isPending ? 'Saving…' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}
