import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { practicesApi } from '@/services/api';
import { apiErrorMessage, asList } from '@/utils/api';
import {
  FileText, Save, Check, Eye, Code
} from 'lucide-react';

// Only variables the backend substitutes when drafting replies (appointments AIDraftView).
const AVAILABLE_VARIABLES = [
  '{{patient_name}}',
  '{{email}}',
  '{{phone}}',
  '{{service}}',
  '{{intent}}',
  '{{preferred_date}}',
  '{{preferred_time}}',
  '{{message}}',
  '{{practice}}',
];

// Mirrors EmailTemplate.TEMPLATE_TYPES on the backend.
const TEMPLATE_TYPES: { type: string; label: string }[] = [
  { type: 'new_patient', label: 'New Patient Request' },
  { type: 'emergency', label: 'Emergency Request' },
  { type: 'cleaning', label: 'Cleaning & Checkup' },
  { type: 'reschedule', label: 'Reschedule Request' },
  { type: 'cancel', label: 'Cancellation Request' },
  { type: 'question', label: 'General Question' },
  { type: 'handoff', label: 'Human Handoff Request' },
];

export default function EmailTemplatesPage() {
  const queryClient = useQueryClient();
  const [selectedType, setSelectedType] = useState<string>(TEMPLATE_TYPES[0].type);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [previewMode, setPreviewMode] = useState(false);
  const [saved, setSaved] = useState(false);

  // Fetch templates from API
  const { data: templatesData, isLoading, isError } = useQuery({
    queryKey: ['templates'],
    queryFn: () => practicesApi.templates(),
  });

  const saved_templates: any[] = asList(templatesData);
  const templates = TEMPLATE_TYPES.map(({ type, label }) => {
    const existing = saved_templates.find((t) => t.template_type === type);
    return existing
      ? { ...existing, name: label, exists: true }
      : { id: null, template_type: type, name: label, subject: '', body: '', exists: false };
  });
  const activeTemplate = templates.find((t) => t.template_type === selectedType) || templates[0];

  useEffect(() => {
    setSubject(activeTemplate?.subject ?? '');
    setBody(activeTemplate?.body ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedType, templatesData]);

  const handleSelect = (tmpl: any) => setSelectedType(tmpl.template_type);

  const saveMutation = useMutation({
    mutationFn: () => {
      const data = { subject: subject.trim(), body };
      return activeTemplate.exists
        ? practicesApi.updateTemplate(activeTemplate.id, data)
        : practicesApi.createTemplate({ ...data, template_type: activeTemplate.template_type });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      toast.success('Template saved');
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not save template.')),
  });

  const handleSave = () => {
    if (!subject.trim() || !body.trim()) {
      toast.error('Subject and body are required.');
      return;
    }
    saveMutation.mutate();
  };

  const insertVariable = (variable: string) => {
    setBody((prev) => prev + ' ' + variable);
  };

  const getInterpolatedPreview = (text: string) => {
    return text
      .replace(/{{patient_name}}/g, 'Sarah Jenkins')
      .replace(/{{phone}}/g, '(919) 555-0142')
      .replace(/{{email}}/g, 'sarah.j@example.com')
      .replace(/{{service}}/g, 'Comprehensive Cleaning')
      .replace(/{{intent}}/g, 'Cleaning')
      .replace(/{{preferred_date}}/g, 'Thursday')
      .replace(/{{preferred_time}}/g, 'Afternoon (around 3:00 PM)')
      .replace(/{{message}}/g, 'Looking for an appointment sometime next week')
      .replace(/{{practice}}/g, 'Your Practice');
  };

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Email Templates</h1>
          <p className="text-gray-500 mt-1">Configure automated notifications and outbound front desk templates.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setPreviewMode(!previewMode)}
            className="flex items-center gap-1.5 px-4 py-2 border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 rounded-xl text-sm font-semibold transition"
          >
            {previewMode ? <Code className="w-4 h-4 text-teal-600" /> : <Eye className="w-4 h-4 text-teal-600" />}
            {previewMode ? 'Edit Template' : 'Preview with Sample Data'}
          </button>
          <button
            onClick={handleSave}
            disabled={saveMutation.isPending || !activeTemplate}
            className="flex items-center gap-2 px-6 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-sm font-semibold transition shadow-sm disabled:opacity-50"
          >
            {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
            {saved ? 'Saved!' : saveMutation.isPending ? 'Saving...' : 'Save Template'}
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Template List (4 cols) */}
        <div className="lg:col-span-4 bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 font-bold text-xs uppercase tracking-wider text-gray-500">
            Available Templates
          </div>
          {isLoading ? (
            <div className="p-8 text-center text-sm text-gray-400">Loading templates...</div>
          ) : isError ? (
            <div className="p-8 text-center text-sm text-red-600">Could not load templates.</div>
          ) : (
            <div className="divide-y divide-gray-100">
              {templates.map((t: any) => {
                const isSelected = activeTemplate?.template_type === t.template_type;
                return (
                  <button
                    key={t.template_type}
                    onClick={() => handleSelect(t)}
                    className={`w-full text-left p-4 hover:bg-gray-50 transition flex items-start gap-3 ${
                      isSelected ? 'bg-teal-50/60 border-l-4 border-teal-600' : ''
                    }`}
                  >
                    <FileText className={`w-4 h-4 mt-0.5 flex-shrink-0 ${isSelected ? 'text-teal-600' : 'text-gray-400'}`} />
                    <div>
                      <span className="text-sm font-bold text-gray-900 block">{t.name}</span>
                      <span className="text-xs text-gray-400 uppercase tracking-wider font-semibold">
                        {t.exists ? (t.is_active ? 'Active' : 'Inactive') : 'Not set up yet'}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Editor & Preview (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          {activeTemplate ? (
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                <h2 className="text-base font-bold text-gray-900">
                  Editing: <span className="text-teal-700">{activeTemplate.name}</span>
                </h2>
                <span className="text-xs bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full font-mono">
                  Type: {activeTemplate.template_type}
                </span>
              </div>

              {/* Subject */}
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Email Subject Line</label>
                {previewMode ? (
                  <div className="p-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm font-semibold text-gray-900">
                    {getInterpolatedPreview(subject)}
                  </div>
                ) : (
                  <input
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                )}
              </div>

              {/* Available Variables Chips */}
              {!previewMode && (
                <div>
                  <label className="text-xs font-semibold text-gray-500 block mb-1.5">
                    Click to Insert Dynamic Variable:
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {AVAILABLE_VARIABLES.map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => insertVariable(v)}
                        className="px-2 py-1 bg-gray-100 hover:bg-teal-50 hover:text-teal-700 border border-gray-200 rounded text-[11px] font-mono text-gray-700 transition"
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Body */}
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Email Body Content</label>
                {previewMode ? (
                  <div className="p-4 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-800 whitespace-pre-wrap leading-relaxed font-sans min-h-[220px]">
                    {getInterpolatedPreview(body)}
                  </div>
                ) : (
                  <textarea
                    rows={10}
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                )}
              </div>

              {previewMode && (
                <div className="p-3 bg-teal-50 border border-teal-200 rounded-lg text-xs text-teal-800 flex items-center justify-between">
                  <span>💡 This preview shows dynamic variables replaced with real-world sample patient data.</span>
                  <button
                    onClick={() => setPreviewMode(false)}
                    className="font-bold underline ml-2"
                  >
                    Back to Edit
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="p-12 text-center text-gray-400 bg-white rounded-xl border border-gray-200">
              Select a template on the left to edit.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
