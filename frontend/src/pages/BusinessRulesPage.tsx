import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { practicesApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';
import {
  Calendar, Clock, AlertTriangle, Headphones, Save, Check, ShieldCheck
} from 'lucide-react';

export default function BusinessRulesPage() {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);

  // Business Hours state
  const [hours, setHours] = useState<Record<string, { open: string; close: string; closed: boolean }>>({
    monday: { open: '08:00', close: '17:00', closed: false },
    tuesday: { open: '08:00', close: '17:00', closed: false },
    wednesday: { open: '08:00', close: '17:00', closed: false },
    thursday: { open: '08:00', close: '17:00', closed: false },
    friday: { open: '08:00', close: '14:00', closed: false },
    saturday: { open: '09:00', close: '13:00', closed: true },
    sunday: { open: '09:00', close: '13:00', closed: true },
  });

  // Emergency & Triage rules
  const [emergencyPhone, setEmergencyPhone] = useState('');
  const [emergencyMessage, setEmergencyMessage] = useState('');

  // Human handoff rules
  const [handoffEnabled, setHandoffEnabled] = useState(true);
  const [handoffMessage, setHandoffMessage] = useState('');

  // Appointment & Custom AI rules
  const [cancellationNoticeHours, setCancellationNoticeHours] = useState(24);
  const [customInstructions, setCustomInstructions] = useState('');
  const [newPatientDuration, setNewPatientDuration] = useState(90);
  const [confirmationHours, setConfirmationHours] = useState(48);
  const [noShowFee, setNoShowFee] = useState('65.00');
  const [financing, setFinancing] = useState('');

  const { data: rulesData, isLoading, isError } = useQuery({
    queryKey: ['booking-rules'],
    queryFn: () => practicesApi.bookingRules(),
  });

  useEffect(() => {
    if (!rulesData) return;
    const r = rulesData;
    if (r.business_hours && Object.keys(r.business_hours).length) {
      setHours((prev) => ({ ...prev, ...r.business_hours }));
    }
    setEmergencyPhone(r.emergency_phone ?? '');
    setEmergencyMessage(r.emergency_message ?? '');
    setHandoffEnabled(r.handoff_enabled !== false);
    setHandoffMessage(r.handoff_message ?? '');
    setCancellationNoticeHours(Number(r.cancellation_notice_hours ?? 24));
    setCustomInstructions(r.custom_instructions ?? '');
    setNewPatientDuration(Number(r.new_patient_duration ?? 90));
    setConfirmationHours(Number(r.confirmation_hours ?? 48));
    setNoShowFee(String(r.no_show_fee ?? '0'));
    setFinancing(Array.isArray(r.financing_options) ? r.financing_options.join(', ') : '');
  }, [rulesData]);

  const saveMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => practicesApi.updateBookingRules(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['booking-rules'] });
      toast.success('Business rules saved');
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not save business rules.')),
  });

  const handleSave = () => {
    saveMutation.mutate({
      business_hours: hours,
      emergency_phone: emergencyPhone,
      emergency_message: emergencyMessage,
      handoff_enabled: handoffEnabled,
      handoff_message: handoffMessage,
      cancellation_notice_hours: cancellationNoticeHours,
      custom_instructions: customInstructions,
      new_patient_duration: newPatientDuration,
      confirmation_hours: confirmationHours,
      no_show_fee: noShowFee || '0',
      financing_options: financing.split(',').map((f) => f.trim()).filter(Boolean),
    });
  };

  if (isLoading) return <div className="p-8 text-sm text-gray-500">Loading business rules…</div>;
  if (isError) return <div className="p-8 text-sm text-red-600">Could not load business rules. Please refresh the page.</div>;

  const updateDay = (day: string, field: 'open' | 'close' | 'closed', val: any) => {
    setHours((prev) => ({
      ...prev,
      [day]: { ...prev[day], [field]: val },
    }));
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Business Rules & AI Instructions</h1>
          <p className="text-gray-500 mt-1">Configure operating hours, emergency triage, and AI guardrails.</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="flex items-center gap-2 px-6 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-sm font-semibold transition shadow-sm disabled:opacity-50"
        >
          {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {saved ? 'Saved!' : saveMutation.isPending ? 'Saving...' : 'Save Rules'}
        </button>
      </div>

      {/* Operating Hours Card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
          <Clock className="w-5 h-5 text-teal-600" />
          Weekly Operating Hours
        </h2>
        <p className="text-xs text-gray-500">
          The Concierge will inform patients if the clinic is currently closed and collect requests for morning review.
        </p>

        <div className="divide-y divide-gray-100 border border-gray-100 rounded-xl overflow-hidden">
          {Object.entries(hours).map(([day, config]) => (
            <div key={day} className="px-4 py-3 flex items-center justify-between bg-white hover:bg-gray-50">
              <span className="font-semibold text-sm capitalize text-gray-800 w-28">{day}</span>

              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-xs text-gray-600">
                  <input
                    type="checkbox"
                    checked={config.closed}
                    onChange={(e) => updateDay(day, 'closed', e.target.checked)}
                    className="w-4 h-4 text-teal-600 rounded"
                  />
                  Closed
                </label>

                {!config.closed && (
                  <div className="flex items-center gap-2">
                    <input
                      type="time"
                      value={config.open}
                      onChange={(e) => updateDay(day, 'open', e.target.value)}
                      className="px-2 py-1 text-xs border border-gray-200 rounded-lg"
                    />
                    <span className="text-gray-400 text-xs">to</span>
                    <input
                      type="time"
                      value={config.close}
                      onChange={(e) => updateDay(day, 'close', e.target.value)}
                      className="px-2 py-1 text-xs border border-gray-200 rounded-lg"
                    />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Emergency Triage Card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-red-600" />
          Emergency Triage & Safety Guardrails
        </h2>
        <p className="text-xs text-gray-500">
          When an emergency is detected, the AI will prioritize triage, collect minimal required info, and trigger staff alerts.
        </p>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">Emergency After-Hours Hotline</label>
            <input
              type="text"
              value={emergencyPhone}
              onChange={(e) => setEmergencyPhone(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">Emergency Disclaimer & Protocol</label>
            <textarea
              rows={3}
              value={emergencyMessage}
              onChange={(e) => setEmergencyMessage(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>

          <p className="text-xs text-gray-500">
            Emergency requests are always fast-tracked: the concierge only asks for a callback number before alerting your team.
          </p>

          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <span>Safety Rule Enforced: The AI will NEVER invent medical diagnoses or prescribe medications.</span>
          </div>
        </div>
      </div>

      {/* Human Handoff Card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
          <Headphones className="w-5 h-5 text-cyan-600" />
          Human Staff Handoff
        </h2>

        <div className="space-y-3">
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-sm font-semibold text-gray-800">Enable Human Handoff Option</span>
              <p className="text-xs text-gray-400">Allows visitors to ask for a human front desk coordinator at any time</p>
            </div>
            <input
              type="checkbox"
              checked={handoffEnabled}
              onChange={(e) => setHandoffEnabled(e.target.checked)}
              className="w-4 h-4 text-teal-600 rounded"
            />
          </label>

          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">Handoff Confirmation Message</label>
            <textarea
              rows={2}
              value={handoffMessage}
              onChange={(e) => setHandoffMessage(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
        </div>
      </div>

      {/* Scheduling policies (front-desk reference) */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
          <Clock className="w-5 h-5 text-teal-600" />
          Scheduling policies
        </h2>
        <p className="text-xs text-gray-500">
          Your team's booking rules. Financing options are shared with the assistant; other policies are not
          told to patients unless you add them to the instructions below. Staff always confirm real appointment times.
        </p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="br-np-duration" className="text-xs font-semibold text-gray-700 block mb-1">New-patient visit length (minutes)</label>
            <input id="br-np-duration" type="number" min="15" max="240" value={newPatientDuration}
              onChange={(e) => setNewPatientDuration(Number(e.target.value))} className="w-32 px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
          </div>
          <div>
            <label htmlFor="br-confirm" className="text-xs font-semibold text-gray-700 block mb-1">Confirm appointments within (hours)</label>
            <input id="br-confirm" type="number" min="1" max="168" value={confirmationHours}
              onChange={(e) => setConfirmationHours(Number(e.target.value))} className="w-32 px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
          </div>
          <div>
            <label htmlFor="br-fee" className="text-xs font-semibold text-gray-700 block mb-1">No-show fee ($)</label>
            <input id="br-fee" type="number" min="0" step="0.01" value={noShowFee}
              onChange={(e) => setNoShowFee(e.target.value)} className="w-32 px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
          </div>
          <div>
            <label htmlFor="br-financing" className="text-xs font-semibold text-gray-700 block mb-1">Financing options (comma-separated)</label>
            <input id="br-financing" type="text" value={financing} placeholder="e.g. Cherry, CareCredit"
              onChange={(e) => setFinancing(e.target.value)} className="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
          </div>
        </div>
      </div>

      {/* Custom AI Instructions & Scheduling Policy */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
          <Calendar className="w-5 h-5 text-indigo-600" />
          Practice Context & Custom AI Instructions
        </h2>

        <div>
          <label className="text-xs font-semibold text-gray-700 block mb-1">Cancellation / Reschedule Notice (Hours)</label>
          <input
            type="number"
            min="1"
            max="72"
            value={cancellationNoticeHours}
            onChange={(e) => setCancellationNoticeHours(Number(e.target.value))}
            className="w-32 px-3 py-1.5 border border-gray-200 rounded-lg text-sm"
          />
        </div>

        <div>
          <label className="text-xs font-semibold text-gray-700 block mb-1">Custom Practice AI System Instructions</label>
          <textarea
            rows={4}
            value={customInstructions}
            onChange={(e) => setCustomInstructions(e.target.value)}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-sans focus:outline-none focus:ring-2 focus:ring-teal-500"
            placeholder="Add specific details about accepted insurance, parking instructions, financing, or doctor bios..."
          />
        </div>
      </div>
    </div>
  );
}
