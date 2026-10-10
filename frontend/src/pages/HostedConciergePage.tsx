import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Bot, Send, Shield, AlertTriangle } from 'lucide-react';
import { chatApi } from '@/services/api';

interface Message {
  role: 'assistant' | 'user';
  content: string;
  timestamp: Date;
}

export default function HostedConciergePage() {
  const { slug } = useParams<{ slug: string }>();
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [quickOptions, setQuickOptions] = useState<{ label: string; value: string }[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!slug) return;
    chatApi.hostedConfig(slug)
      .then((data) => {
        setConfig(data);
        const greeting = data.greeting || data.welcome_message || `Hello! Welcome to ${data.practice_name || 'our practice'}. How can we help you today?`;
        setMessages([
          {
            role: 'assistant',
            content: greeting,
            timestamp: new Date(),
          },
        ]);
        setQuickOptions(Array.isArray(data.quick_replies) ? data.quick_replies : []);
        setLoading(false);
      })
      .catch(() => {
        setError('Practice concierge not found or unavailable.');
        setLoading(false);
      });
  }, [slug]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text || isSending) return;

    const userMsg: Message = { role: 'user', content: text, timestamp: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsSending(true);

    const clientKey = config?.client_key || undefined;

    chatApi.send(text, conversationId || undefined, clientKey)
      .then((data: any) => {
        if (data.conversation_id) {
          setConversationId(data.conversation_id);
        }

        setQuickOptions(
          Array.isArray(data.quick_replies)
            ? data.quick_replies.map((r: any) => (typeof r === 'string' ? { label: r, value: r } : r))
            : []
        );

        const reply: Message = {
          role: 'assistant',
          content: data.message || "Thank you! Our front desk has received your request and will reach out shortly.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, reply]);
      })
      .catch(() => {
        const fallback: Message = {
          role: 'assistant',
          content: `Sorry, your message could not be sent. Please try again${config?.phone ? ` or call us at ${config.phone}` : ''}.`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, fallback]);
      })
      .finally(() => setIsSending(false));
  };

  const primaryColor = config?.primary_color || config?.color || '#0d9488';
  const practiceName = config?.practice_name || 'HeyJarvis Concierge';
  const assistantName = config?.title || config?.assistant_name || 'Dental Concierge';

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-teal-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500 font-medium">Connecting to Concierge...</p>
        </div>
      </div>
    );
  }

  if (error || !config) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl p-8 max-w-md w-full shadow-md text-center">
          <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-3" />
          <h2 className="text-lg font-bold text-gray-900">Concierge Unavailable</h2>
          <p className="text-sm text-gray-500 mt-2">{error || 'Unable to load practice configuration.'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col items-center justify-center p-0 sm:p-4">
      <div className="w-full sm:max-w-xl bg-white sm:rounded-2xl shadow-xl flex flex-col h-screen sm:h-[720px] overflow-hidden border border-gray-200">
        {/* Practice Branding Header */}
        <div
          className="px-6 py-4 text-white flex items-center justify-between shadow-md"
          style={{ backgroundColor: primaryColor }}
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center backdrop-blur-sm">
              <Bot className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-bold text-base leading-tight">{practiceName}</h1>
              <p className="text-xs text-white/80">{assistantName} • 24/7 Virtual Assistant</p>
            </div>
          </div>
          <span className="text-[11px] bg-white/20 px-2.5 py-1 rounded-full font-medium">
            Online
          </span>
        </div>

        {/* Emergency Warning Banner */}
        <div className="bg-amber-50 px-4 py-2 border-b border-amber-200/60 text-[11px] text-amber-900 flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />
          <span>For medical or dental emergencies requiring immediate attention, please call 911.</span>
        </div>

        {/* Chat Timeline */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 bg-slate-50/50">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex gap-3 max-w-[85%] ${
                msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''
              }`}
            >
              {msg.role === 'assistant' && (
                <div
                  className="w-8 h-8 rounded-full text-white flex items-center justify-center flex-shrink-0 text-xs font-bold shadow-sm"
                  style={{ backgroundColor: primaryColor }}
                >
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`p-3.5 rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'text-white rounded-tr-none shadow-sm'
                    : 'bg-white text-gray-800 rounded-tl-none border border-gray-200/80 shadow-sm'
                }`}
                style={msg.role === 'user' ? { backgroundColor: primaryColor } : undefined}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>
                <div
                  className={`text-[10px] mt-1 text-right ${
                    msg.role === 'user' ? 'text-white/70' : 'text-gray-400'
                  }`}
                >
                  {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            </div>
          ))}

          {isSending && (
            <div className="flex gap-2 items-center text-xs text-gray-400 pl-11">
              <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" />
              <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce delay-100" />
              <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce delay-200" />
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Suggestion Pills */}
        {quickOptions.length > 0 && !isSending && (
          <div className="px-4 py-2 bg-white border-t border-gray-100 flex flex-wrap gap-2">
            {quickOptions.map((opt) => (
              <button
                key={opt.label}
                onClick={() => handleSend(opt.value)}
                className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-full text-xs font-medium transition"
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}

        {/* Input Bar */}
        <div className="p-3 bg-white border-t border-gray-200 flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Type your message..."
            disabled={isSending}
            className="flex-1 px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || isSending}
            className="p-2.5 rounded-xl text-white font-semibold transition disabled:opacity-50 shadow-sm"
            style={{ backgroundColor: primaryColor }}
          >
            <Send className="w-5 h-5" />
          </button>
        </div>

        {/* Privacy Footer */}
        <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 text-[10px] text-gray-400 text-center">
          Powered by HeyJarvis Concierge • HIPAA-Aware Communication
        </div>
      </div>
    </div>
  );
}
