import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { practicesApi } from '@/services/api';
import {
  Palette, Bot, Save, MessageSquare, Send, Sparkles, Check
} from 'lucide-react';

export default function WidgetSettingsPage() {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);

  // Form State
  const [title, setTitle] = useState('HeyJarvis Concierge');
  const [greeting, setGreeting] = useState('Hi! How can our front desk assist you today?');
  const [launcherText, setLauncherText] = useState('Chat with Front Desk');
  const [primaryColor, setPrimaryColor] = useState('#0d9488');
  const [position, setPosition] = useState<'right' | 'left'>('right');
  const [borderRadius, setBorderRadius] = useState<'rounded' | 'pill' | 'square'>('rounded');
  const [autoOpen, setAutoOpen] = useState(false);
  const [autoOpenDelay, setAutoOpenDelay] = useState(5);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [offlineMessage, setOfflineMessage] = useState("We're currently offline. Please leave your details and we'll contact you promptly.");
  const [afterHoursMessage, setAfterHoursMessage] = useState('Our office is closed right now. We will review your request first thing in the morning!');
  const [successMessage, setSuccessMessage] = useState('Thank you! Our front desk has received your request and will reach out shortly.');

  // Fetch settings from API
  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: () => practicesApi.settings(),
  });

  useEffect(() => {
    if (settingsData?.settings) {
      const s = settingsData.settings;
      if (s.title) setTitle(s.title);
      if (s.greeting) setGreeting(s.greeting);
      if (s.primary_color) setPrimaryColor(s.primary_color);
      if (s.position) setPosition(s.position as any);
      if (s.launcher_text) setLauncherText(s.launcher_text);
      if (s.auto_open !== undefined) setAutoOpen(Boolean(s.auto_open));
      if (s.auto_open_delay !== undefined) setAutoOpenDelay(Number(s.auto_open_delay));
      if (s.sound_enabled !== undefined) setSoundEnabled(Boolean(s.sound_enabled));
      if (s.offline_message) setOfflineMessage(s.offline_message);
      if (s.after_hours_message) setAfterHoursMessage(s.after_hours_message);
      if (s.success_message) setSuccessMessage(s.success_message);
    }
  }, [settingsData]);

  const saveMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => practicesApi.updateSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
  });

  const handleSave = () => {
    saveMutation.mutate({
      title,
      greeting,
      primary_color: primaryColor,
      position,
      launcher_text: launcherText,
      auto_open: autoOpen,
      auto_open_delay: autoOpenDelay,
      sound_enabled: soundEnabled,
      offline_message: offlineMessage,
      after_hours_message: afterHoursMessage,
      success_message: successMessage,
      border_radius: borderRadius,
    });
  };

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
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Launcher Button Text</label>
                <input
                  type="text"
                  value={launcherText}
                  onChange={(e) => setLauncherText(e.target.value)}
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

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1">Corner Radius</label>
                <select
                  value={borderRadius}
                  onChange={(e) => setBorderRadius(e.target.value as any)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white"
                >
                  <option value="rounded">Rounded Corners (Modern)</option>
                  <option value="pill">Pill Shape</option>
                  <option value="square">Square Corners</option>
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
              <label className="text-xs font-semibold text-gray-700 block mb-1">Welcome / Greeting Message</label>
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

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Submission Success Message</label>
              <textarea
                rows={2}
                value={successMessage}
                onChange={(e) => setSuccessMessage(e.target.value)}
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

              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <span className="text-sm font-semibold text-gray-800">Chime Sound Effects</span>
                  <p className="text-xs text-gray-400">Play subtle notification sound on new inbound messages</p>
                </div>
                <input
                  type="checkbox"
                  checked={soundEnabled}
                  onChange={(e) => setSoundEnabled(e.target.checked)}
                  className="w-4 h-4 text-teal-600 rounded"
                />
              </label>
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
                  raleighdentistry.com
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
                      <p className="text-[10px] text-white/80">Online • Front Desk Active</p>
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
                      {greeting}
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
                <span>{launcherText}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
