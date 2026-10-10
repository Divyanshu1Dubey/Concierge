import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { practicesApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';
import {
  Palette, Bot, Save, MessageSquare, Send, Sparkles, Check
} from 'lucide-react';

export default function WidgetSettingsPage() {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);

  // Form State
  const [title, setTitle] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [greeting, setGreeting] = useState('');
  const [primaryColor, setPrimaryColor] = useState('#0d9488');
  const [position, setPosition] = useState<'right' | 'left'>('right');
  const [autoOpen, setAutoOpen] = useState(false);
  const [autoOpenDelay, setAutoOpenDelay] = useState(5);
  const [afterHoursMessage, setAfterHoursMessage] = useState('');

  const { data: settingsData, isLoading, isError } = useQuery({
    queryKey: ['settings'],
    queryFn: () => practicesApi.settings(),
  });
  const { data: rulesData } = useQuery({
    queryKey: ['booking-rules'],
    queryFn: () => practicesApi.bookingRules(),
  });

  useEffect(() => {
    if (!settingsData) return;
    setTitle(settingsData.widget_title ?? '');
    setSubtitle(settingsData.widget_subtitle ?? '');
    setGreeting(settingsData.ai_greeting_message ?? '');
    if (settingsData.widget_primary_color) setPrimaryColor(settingsData.widget_primary_color);
    setPosition(settingsData.widget_position === 'left' ? 'left' : 'right');
    setAutoOpen(Boolean(settingsData.widget_auto_open));
    setAutoOpenDelay(Number(settingsData.widget_auto_open_delay_sec ?? 5));
  }, [settingsData]);

  useEffect(() => {
    if (rulesData) setAfterHoursMessage(rulesData.after_hours_message ?? '');
  }, [rulesData]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      await practicesApi.updateSettings({
        widget_title: title,
        widget_subtitle: subtitle,
        ai_greeting_message: greeting,
        widget_primary_color: primaryColor,
        widget_position: position,
        widget_auto_open: autoOpen,
        widget_auto_open_delay_sec: autoOpenDelay,
      });
      await practicesApi.updateBookingRules({ after_hours_message: afterHoursMessage });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['booking-rules'] });
      toast.success('Widget settings saved');
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not save widget settings.')),
  });

  const handleSave = () => {
    if (!/^#[0-9a-fA-F]{6}$/.test(primaryColor)) {
      toast.error('Primary color must be a hex value like #0d9488');
      return;
    }
    saveMutation.mutate();
  };

  if (isLoading) {
    return <div className="p-8 text-sm text-gray-500">Loading widget settings…</div>;
  }
  if (isError) {
    return <div className="p-8 text-sm text-red-600">Could not load widget settings. Please refresh the page.</div>;
  }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Widget Appearance & Behavior</h1>
          <p className="text-gray-500 mt-1">Customize the floating concierge widget embedded on your patient website.</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="flex items-center gap-2 px-6 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-sm font-semibold transition shadow-sm disabled:opacity-50"
        >
          {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {saved ? 'Saved Successfully!' : saveMutation.isPending ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      <div className="grid lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Form Controls (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* Visual Customization Card */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <Palette className="w-5 h-5 text-teal-600" />
              Theme & Branding
            </h2>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Widget Title</label>
                <input
                  type="text"
                  value={title}
                  maxLength={100}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Subtitle</label>
                <input
                  type="text"
                  maxLength={150}
                  value={subtitle}
                  onChange={(e) => setSubtitle(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Primary Color</label>
                <div className="flex gap-2 items-center">
                  <input
                    type="color"
                    value={primaryColor}
                    onChange={(e) => setPrimaryColor(e.target.value)}
                    className="w-10 h-10 rounded-lg border border-gray-200 cursor-pointer p-0.5"
                  />
                  <input
                    type="text"
                    value={primaryColor}
                    maxLength={7}
                    onChange={(e) => setPrimaryColor(e.target.value)}
                    className="flex-1 font-mono text-xs px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Launcher Position</label>
                <select
                  value={position}
                  onChange={(e) => setPosition(e.target.value as any)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white"
                >
                  <option value="right">Bottom Right (Standard)</option>
                  <option value="left">Bottom Left</option>
                </select>
              </div>

            </div>
          </div>

          {/* Messages & Greetings Card */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-cyan-600" />
              Greeting & System Messages
            </h2>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Welcome / Greeting Message <span className="font-normal text-gray-400">({'{practice}'} is replaced with your practice name)</span></label>
              <textarea
                rows={2}
                value={greeting}
                onChange={(e) => setGreeting(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">After-Hours Message</label>
              <textarea
                rows={2}
                value={afterHoursMessage}
                onChange={(e) => setAfterHoursMessage(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
            </div>

          </div>

          {/* Behavior & Sound */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-amber-500" />
              Behavior & Interaction
            </h2>

            <div className="space-y-3">
              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <span className="text-sm font-semibold text-gray-800">Auto-Open on Page Load</span>
                  <p className="text-xs text-gray-400">Automatically open chat window for new visitors after a short delay</p>
                </div>
                <input
                  type="checkbox"
                  checked={autoOpen}
                  onChange={(e) => setAutoOpen(e.target.checked)}
                  className="w-4 h-4 text-teal-600 rounded"
                />
              </label>

              {autoOpen && (
                <div className="pl-4 border-l-2 border-teal-500">
                  <label className="text-xs font-semibold text-gray-700 block mb-1">Auto-Open Delay (Seconds)</label>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    value={autoOpenDelay}
                    onChange={(e) => setAutoOpenDelay(Number(e.target.value))}
                    className="w-32 px-3 py-1.5 border border-gray-200 rounded-lg text-sm"
                  />
                </div>
              )}

            </div>
          </div>
        </div>

        {/* Right Column: Interactive Live Preview (5 cols) */}
        <div className="lg:col-span-5 sticky top-6">
          <div className="bg-gray-100 rounded-2xl border border-gray-300 p-4 shadow-inner">
            <div className="flex items-center justify-between mb-3 px-2">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-500">Live Widget Preview</span>
              <span className="text-[10px] bg-teal-100 text-teal-800 px-2 py-0.5 rounded-full font-bold">INTERACTIVE</span>
            </div>

            {/* Mocked website browser container */}
            <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden flex flex-col h-[520px] relative">
              {/* Fake Browser Top Bar */}
              <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center gap-2">
                <div className="flex gap-1">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-400" />
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                </div>
                <div className="bg-white px-3 py-0.5 rounded text-[10px] text-gray-400 flex-1 truncate font-mono border border-gray-200 text-center">
                  your-practice-website.com
                </div>
              </div>

              {/* Fake Website Content */}
              <div className="p-4 bg-gray-50/50 flex-1 opacity-40 select-none">
                <div className="h-4 bg-gray-200 rounded w-1/3 mb-2" />
                <div className="h-3 bg-gray-200 rounded w-2/3 mb-4" />
                <div className="h-20 bg-gray-200 rounded w-full mb-3" />
                <div className="h-3 bg-gray-200 rounded w-1/2" />
              </div>

              {/* Simulated Floating Chat Window */}
              <div className="absolute inset-x-2 bottom-14 bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden max-h-[380px]">
                {/* Chat Header */}
                <div
                  className="px-4 py-3 text-white flex items-center justify-between shadow-sm"
                  style={{ backgroundColor: primaryColor }}
                >
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center">
                      <Bot className="w-4 h-4 text-white" />
                    </div>
                    <div>
                      <h4 className="text-xs font-bold leading-tight">{title}</h4>
                      <p className="text-[10px] text-white/80">{subtitle}</p>
                    </div>
                  </div>
                </div>

                {/* Chat Messages */}
                <div className="p-3 flex-1 overflow-y-auto space-y-2.5 text-xs bg-gray-50">
                  <div className="flex gap-2 items-start max-w-[85%]">
                    <div className="w-5 h-5 rounded-full bg-teal-600 text-white flex items-center justify-center text-[10px] flex-shrink-0">
                      AI
                    </div>
                    <div className="bg-white p-2.5 rounded-xl rounded-tl-none shadow-sm border border-gray-100 text-gray-800 text-[11px] leading-relaxed">
                      {greeting.replace('{practice}', settingsData?.practice_name || 'your practice')}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {['New Patient', 'Emergency', 'Cleaning', 'Question'].map((opt) => (
                      <span
                        key={opt}
                        className="px-2.5 py-1 bg-white border border-teal-600/30 text-teal-800 rounded-full text-[10px] font-semibold"
                      >
                        {opt}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Input Bar */}
                <div className="p-2 bg-white border-t border-gray-200 flex gap-1.5">
                  <input
                    type="text"
                    disabled
                    placeholder="Type your reply here..."
                    className="flex-1 text-[11px] bg-gray-50 border border-gray-200 rounded-lg px-2.5 py-1.5"
                  />
                  <button
                    disabled
                    className="p-1.5 rounded-lg text-white"
                    style={{ backgroundColor: primaryColor }}
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Launcher Floating Pill */}
              <div
                className={`absolute bottom-3 ${position === 'left' ? 'left-3' : 'right-3'} flex items-center gap-2 px-3.5 py-2 rounded-full text-white shadow-lg text-xs font-bold cursor-default select-none`}
                style={{ backgroundColor: primaryColor }}
              >
                <Bot className="w-4 h-4" />
                <span>Chat with us</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
