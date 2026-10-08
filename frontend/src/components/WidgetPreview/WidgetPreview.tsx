import { useState, useRef, useEffect, useCallback } from 'react';
import { chatApi } from '@/services/api';
import {
  Bot,
  Send,
  Sparkles,
  Copy,
  RefreshCw
} from 'lucide-react';
import toast from 'react-hot-toast';

export default function WidgetPreview() {
  const [isOpen, setIsOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<'preview' | 'embed' | 'customize'>('preview');
  const [message, setMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [primaryColor, setPrimaryColor] = useState('#0d9488');
  const [position, setPosition] = useState<'bottom-right' | 'bottom-left'>('bottom-right');
  const [messages, setMessages] = useState<
    { role: 'user' | 'bot'; content: string; time: string; chips?: string[]; isCard?: boolean }[]
  >([
    {
      role: 'bot',
      content:
        'Hello and welcome to Raleigh Comprehensive Dentistry! 👋 I am your 24/7 AI Concierge. How can our clinic take care of your smile today?',
      time: 'Just now',
      chips: ['📅 Book Cleaning & Exam', '⚡ Tooth Pain / Emergency', '💬 Insurance Question', '🕒 Office Hours'],
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const sendMessage = useCallback(
    async (textToSend?: string) => {
      const txt = (textToSend || message).trim();
      if (!txt) return;

      setMessage('');
      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      setMessages((prev) => [...prev, { role: 'user', content: txt, time: timeStr }]);
      setIsTyping(true);

      try {
        const response = await chatApi.send(txt, conversationId);
        if (response?.conversation_id) {
          setConversationId(response.conversation_id);
        }

        const replyContent =
          (typeof response?.message === 'string' ? response.message : response?.message?.content) ||
          response?.response ||
          "Thank you for your message! Our front desk has received your request and will follow up with you shortly.";

        // Determine if reply suggests options
        let followUpChips: string[] | undefined = undefined;
        if (txt.toLowerCase().includes('book') || txt.toLowerCase().includes('clean')) {
          followUpChips = ['Tuesday at 10:00 AM', 'Thursday at 2:30 PM', 'Flexible Next Week'];
        }

        setTimeout(() => {
          setIsTyping(false);
          setMessages((prev) => [
            ...prev,
            {
              role: 'bot',
              content: replyContent,
              time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              chips: followUpChips,
            },
          ]);
        }, 600);
      } catch {
        setTimeout(() => {
          setIsTyping(false);
          setMessages((prev) => [
            ...prev,
            {
              role: 'bot',
              content:
                "We would be delighted to assist you with that! What is the best phone number or email address for our front desk to confirm your preferred time?",
              time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              chips: ['919-555-0144', 'Contact via Email', 'Speak with Doctor'],
            },
          ]);
        }, 600);
      }
    },
    [message, conversationId]
  );

  const resetChat = () => {
    setConversationId(undefined);
    setMessages([
      {
        role: 'bot',
        content:
          'Hello and welcome to Raleigh Comprehensive Dentistry! 👋 I am your 24/7 AI Concierge. How can our clinic take care of your smile today?',
        time: 'Just now',
        chips: ['📅 Book Cleaning & Exam', '⚡ Tooth Pain / Emergency', '💬 Insurance Question', '🕒 Office Hours'],
      },
    ]);
    toast.success('Widget conversation refreshed');
  };

  const widgetOrigin = typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
    ? window.location.origin
    : 'http://localhost:8000';

  const embedCode = `<!-- HeyJarvis Universal Dental AI Concierge Widget -->
<script
  src="${widgetOrigin}/widget.js"
  data-heyjarvis-client="raleigh-dentistry-pro"
  data-theme="light"
  data-color="${primaryColor}"
  data-position="${position}"
  async
></script>`;

  const copyEmbed = () => {
    navigator.clipboard.writeText(embedCode);
    toast.success('Embed script copied to clipboard!');
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-teal-100 text-teal-800 flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-teal-600" /> Live Interactive Preview
            </span>
            <span className="text-xs text-gray-500 font-medium">Standalone Web Widget</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">Dental Website Concierge</h1>
          <p className="text-sm text-gray-500">
            Preview, test, and customize the luxury AI concierge widget that your patients interact with on your website.
          </p>
        </div>

        {/* Tab switchers */}
        <div className="flex items-center gap-2 bg-gray-100 p-1 rounded-xl">
          <button
            onClick={() => setActiveTab('preview')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
              activeTab === 'preview' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Live Preview
          </button>
          <button
            onClick={() => setActiveTab('customize')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
              activeTab === 'customize' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Customize
          </button>
          <button
            onClick={() => setActiveTab('embed')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
              activeTab === 'embed' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Embed Script
          </button>
        </div>
      </div>

      {activeTab === 'customize' && (
        <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">
              Primary Theme Accent
            </label>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={primaryColor}
                onChange={(e) => setPrimaryColor(e.target.value)}
                className="w-10 h-10 rounded-xl cursor-pointer border border-gray-300"
              />
              <span className="font-mono text-xs text-gray-600">{primaryColor}</span>
            </div>
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">
              Widget Position
            </label>
            <select
              value={position}
              onChange={(e) => setPosition(e.target.value as any)}
              className="w-full px-3 py-2 border border-gray-300 rounded-xl text-xs font-medium focus:ring-2 focus:ring-teal-500"
            >
              <option value="bottom-right">Bottom Right (Recommended)</option>
              <option value="bottom-left">Bottom Left</option>
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={resetChat}
              className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-xl text-xs font-semibold text-gray-700 hover:bg-gray-50 transition"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Reset Conversation
            </button>
          </div>
        </div>
      )}

      {activeTab === 'embed' && (
        <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-gray-900">HTML Embed Code</h3>
              <p className="text-xs text-gray-500">Paste before the closing &lt;/body&gt; tag on your clinic website.</p>
            </div>
            <button
              onClick={copyEmbed}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-xl text-xs font-bold shadow-sm transition"
            >
              <Copy className="w-3.5 h-3.5" /> Copy Code
            </button>
          </div>
          <pre className="bg-slate-950 text-teal-300 p-4 rounded-xl text-xs font-mono overflow-x-auto leading-relaxed border border-slate-800">
            {embedCode}
          </pre>
        </div>
      )}

      {/* Simulated Dental Clinic Website Background with Live Floating Widget */}
      <div className="relative bg-slate-100 rounded-3xl border border-gray-300/80 h-[680px] overflow-hidden shadow-inner flex flex-col">
        {/* Fake Clinic Website Header */}
        <div className="h-14 bg-white border-b border-gray-200 px-6 flex items-center justify-between shadow-sm z-10">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-teal-600 text-white flex items-center justify-center font-black text-sm">
              R
            </div>
            <div>
              <span className="text-sm font-black text-gray-900 tracking-tight block">
                Raleigh Comprehensive Dentistry
              </span>
              <span className="text-[10px] text-gray-500 font-semibold block">Dr. Neal Patel, DDS</span>
            </div>
          </div>
          <div className="hidden sm:flex items-center gap-6 text-xs font-semibold text-gray-600">
            <span>About Us</span>
            <span>Services</span>
            <span>Dental Implants</span>
            <span>Cosmetic</span>
            <span className="px-3 py-1.5 bg-teal-600 text-white rounded-lg">Call: (919) 555-0100</span>
          </div>
        </div>

        {/* Fake Website Hero Background */}
        <div className="p-8 md:p-12 space-y-6 max-w-2xl opacity-40 select-none pointer-events-none">
          <span className="px-3 py-1 bg-teal-100 text-teal-800 rounded-full text-xs font-bold uppercase tracking-wider">
            Excellence in Gentle Dental Care
          </span>
          <h2 className="text-3xl md:text-5xl font-extrabold text-gray-900 leading-tight">
            Healthy, Radiant Smiles Start Here in Raleigh.
          </h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            Welcome to our modern, comfortable dental clinic. From preventive hygiene checkups to full mouth
            cosmetic transformations, we treat you like family.
          </p>
          <div className="flex gap-3 pt-2">
            <div className="w-36 h-10 bg-teal-600 rounded-xl" />
            <div className="w-32 h-10 bg-gray-300 rounded-xl" />
          </div>
        </div>

        {/* ─── Modern Luxury Dental Concierge Widget ─── */}
        <div
          className={`absolute bottom-6 z-30 transition-all ${
            position === 'bottom-left' ? 'left-6' : 'right-6'
          }`}
        >
          {/* Launcher Button (when closed) */}
          {!isOpen && (
            <button
              onClick={() => setIsOpen(true)}
              style={{ background: primaryColor }}
              className="w-16 h-16 rounded-full text-white shadow-2xl flex items-center justify-center hover:scale-105 active:scale-95 transition-transform duration-200 group relative border-2 border-white"
              title="Open HeyJarvis Concierge"
            >
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-emerald-400 border-2 border-white rounded-full animate-pulse" />
              <Bot className="w-8 h-8 text-white group-hover:rotate-6 transition-transform" />
            </button>
          )}

          {/* Interactive Chat Window */}
          {isOpen && (
            <div className="w-[380px] sm:w-[410px] h-[580px] max-h-[85vh] bg-white rounded-3xl shadow-2xl border border-gray-200/90 flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
              {/* Header */}
              <div
                style={{
                  background: `linear-gradient(135deg, #0f172a 0%, ${primaryColor} 140%)`,
                }}
                className="px-5 py-4 text-white flex items-center justify-between flex-shrink-0 shadow-md"
              >
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div className="w-11 h-11 rounded-2xl bg-white/10 border border-white/20 backdrop-blur-md flex items-center justify-center text-teal-300 shadow-sm">
                      <Bot className="w-6 h-6" />
                    </div>
                    <span className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 bg-emerald-400 border-2 border-slate-900 rounded-full" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold tracking-tight text-white leading-tight">
                      Raleigh Dental Concierge
                    </h3>
                    <p className="text-[11px] text-teal-200 font-medium flex items-center gap-1.5 mt-0.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      Dr. Neal Patel • Instant Reply
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={resetChat}
                    className="p-1.5 rounded-xl hover:bg-white/10 text-white/80 hover:text-white transition"
                    title="Restart chat"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setIsOpen(false)}
                    className="p-1.5 rounded-xl hover:bg-white/10 text-white/80 hover:text-white transition text-sm font-bold"
                    title="Minimize"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {/* Message Feed */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3.5 bg-slate-50/70">
                {/* Intro badge */}
                <div className="text-center py-1">
                  <span className="px-3 py-1 bg-white border border-gray-200 text-gray-500 rounded-full text-[10px] font-semibold shadow-xs">
                    🔒 HIPAA-Encrypted Front Desk AI
                  </span>
                </div>

                {messages.map((msg, i) => {
                  const isUser = msg.role === 'user';
                  return (
                    <div key={i} className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} space-y-1.5`}>
                      <div
                        className={`max-w-[85%] px-4 py-3 rounded-2xl text-[13.5px] leading-relaxed shadow-xs ${
                          isUser
                            ? 'text-white rounded-br-xs'
                            : 'bg-white border border-gray-200 text-gray-800 rounded-bl-xs'
                        }`}
                        style={isUser ? { background: primaryColor } : {}}
                      >
                        <p className="whitespace-pre-wrap">{msg.content}</p>
                        <span
                          className={`text-[10px] block text-right mt-1.5 ${
                            isUser ? 'text-teal-200' : 'text-gray-400'
                          }`}
                        >
                          {msg.time}
                        </span>
                      </div>

                      {/* Interactive Suggestion Chips */}
                      {msg.chips && msg.chips.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1 max-w-[90%]">
                          {msg.chips.map((chip, cIdx) => (
                            <button
                              key={cIdx}
                              onClick={() => sendMessage(chip)}
                              className="px-3 py-1 bg-white hover:bg-teal-50 text-teal-800 border border-teal-200 rounded-full text-xs font-semibold shadow-xs hover:border-teal-400 transition-all text-left"
                            >
                              {chip}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Typing indicator */}
                {isTyping && (
                  <div className="flex items-center gap-1.5 bg-white border border-gray-200 px-4 py-2.5 rounded-2xl w-fit shadow-xs">
                    <span className="w-2 h-2 rounded-full bg-teal-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 rounded-full bg-teal-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 rounded-full bg-teal-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Input Footer */}
              <div className="p-3 bg-white border-t border-gray-200">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    sendMessage();
                  }}
                  className="relative flex items-center"
                >
                  <input
                    type="text"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Type your reply or question..."
                    className="w-full pl-4 pr-12 py-3 bg-gray-50 border border-gray-200 rounded-2xl text-xs font-medium focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white transition-colors"
                  />
                  <button
                    type="submit"
                    disabled={!message.trim()}
                    style={{ background: primaryColor }}
                    className="absolute right-2 p-2 rounded-xl text-white hover:opacity-90 transition disabled:opacity-30 disabled:cursor-not-allowed shadow-xs"
                    title="Send"
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                </form>
                <div className="flex items-center justify-between text-[10px] text-gray-400 mt-2 px-1">
                  <span>Powered by HeyJarvis AI</span>
                  <span className="flex items-center gap-1 text-emerald-600 font-semibold">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Clinic Online
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
