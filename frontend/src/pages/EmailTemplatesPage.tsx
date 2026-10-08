import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { practicesApi } from '@/services/api';
import {
  FileText, Save, Check, Eye, Code
} from 'lucide-react';

const AVAILABLE_VARIABLES = [
  '{{patient_name}}',
  '{{phone}}',
  '{{email}}',
  '{{service}}',
  '{{intent}}',
  '{{preferred_date}}',
  '{{preferred_time}}',
  '{{insurance}}',
  '{{financing}}',
  '{{message}}',
  '{{conversation_summary}}',
  '{{page_url}}',
  '{{conversation_id}}',
];

export default function EmailTemplatesPage() {
  const queryClient = useQueryClient();
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [previewMode, setPreviewMode] = useState(false);
  const [saved, setSaved] = useState(false);

  // Fetch templates from API
  const { data: templatesData, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => practicesApi.templates(),
  });

  const templates: any[] = templatesData?.templates || [];

  // When templates load, pick first
  const activeTemplate = templates.find((t) => t.id === selectedTemplateId) || templates[0];

  const handleSelect = (tmpl: any) => {
    setSelectedTemplateId(tmpl.id);
    setSubject(tmpl.subject);
    setBody(tmpl.body);
  };

  // If first render and activeTemplate exists
  useState(() => {
    if (activeTemplate && !subject) {
      setSubject(activeTemplate.subject);
      setBody(activeTemplate.body);
    }
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!activeTemplate) return Promise.resolve();
      return practicesApi.updateTemplate(activeTemplate.id, { subject, body });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
  });

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
      .replace(/{{insurance}}/g, 'Delta Dental PPO')
      .replace(/{{financing}}/g, 'Not requested')
      .replace(/{{message}}/g, 'Looking for an appointment sometime next week')
      .replace(/{{conversation_summary}}/g, 'Patient is requesting a routine cleaning. Prefers Thursday afternoon.')
      .replace(/{{page_url}}/g, 'https://raleighdentistry.com/services/cleaning')
      .replace(/{{conversation_id}}/g, 'conv_9182a4');
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
            onClick={() => saveMutation.mutate()}
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
          ) : (
            <div className="divide-y divide-gray-100">
              {templates.map((t: any) => {
                const isSelected = activeTemplate?.id === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => handleSelect(t)}
                    className={`w-full text-left p-4 hover:bg-gray-50 transition flex items-start gap-3 ${
                      isSelected ? 'bg-teal-50/60 border-l-4 border-teal-600' : ''
                    }`}
                  >
                    <FileText className={`w-4 h-4 mt-0.5 flex-shrink-0 ${isSelected ? 'text-teal-600' : 'text-gray-400'}`} />
                    <div>
                      <span className="text-sm font-bold text-gray-900 block">{t.name}</span>
                      <span className="text-xs text-gray-400 uppercase tracking-wider font-semibold">
                        Intent: {t.intent}
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
                    {getInterpolatedPreview(subject || activeTemplate.subject)}
                  </div>
                ) : (
                  <input
                    type="text"
                    value={subject || activeTemplate.subject}
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
                    {getInterpolatedPreview(body || activeTemplate.body)}
                  </div>
                ) : (
                  <textarea
                    rows={10}
                    value={body || activeTemplate.body}
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
