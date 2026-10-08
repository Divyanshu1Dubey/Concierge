import { useState, useEffect, useRef, useCallback } from 'react';
import { Bot, Send, User, Settings2 } from 'lucide-react';
import { chatApi } from '@/services/api';

type MessageRole = 'user' | 'assistant';

interface ChatMessage {
  role: MessageRole;
  content: string;
  timestamp: Date;
}

const SCENARIOS = [
  { label: 'New patient booking', message: "Hi, I'm a new patient looking to book my first appointment. What do I need to know?" },
  { label: 'Emergency visit', message: 'I have a severe toothache and need to see a dentist ASAP. Do you have any emergency slots?' },
  { label: 'Reschedule request', message: 'I have an appointment next Tuesday but I need to reschedule. Is that possible?' },
];

export default function ConciergePage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [quickOptions, setQuickOptions] = useState<string[]>(['New Patient', 'Emergency', 'Cleaning', 'Question']);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: "Hello! I'm the HeyJarvis Concierge. How can our front desk assist you today?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isPending, setIsPending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback((textToSend?: string) => {
    const trimmed = (textToSend || input).trim();
    if (!trimmed || isPending) return;

    const userMessage: ChatMessage = { role: 'user', content: trimmed, timestamp: new Date() };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsPending(true);

    chatApi.send(trimmed, conversationId || undefined)
      .then((data: any) => {
        if (data.conversation_id) {
          setConversationId(data.conversation_id);
        }
        if (data.quick_options && Array.isArray(data.quick_options) && data.quick_options.length > 0) {
          setQuickOptions(data.quick_options);
        } else if (data.quick_replies && Array.isArray(data.quick_replies) && data.quick_replies.length > 0) {
          setQuickOptions(data.quick_replies.map((r: any) => r.label || r));
        } else {
          setQuickOptions([]);
        }
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: data.message || "Thank you! Our front desk has received your details.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
      })
      .catch(() => {
        const errorMessage: ChatMessage = {
          role: 'assistant',
          content: "I'm having trouble connecting right now. Please leave your details and our front desk will help.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMessage]);
      })
      .finally(() => setIsPending(false));
  }, [input, isPending, conversationId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Concierge</h1>
          <p className="text-gray-500 text-sm mt-0.5">Preview how the AI concierge interacts with patients</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-50 text-green-700 rounded-full text-xs font-medium">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            Active
          </span>
          <button className="p-2 rounded-lg hover:bg-gray-100 text-gray-600">
            <Settings2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Chat container - FIXED HEIGHT */}
      <div className="flex-1 bg-white rounded-xl border border-gray-200 shadow-sm flex overflow-hidden min-h-0">
        {/* Chat messages */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${message.role === 'user' ? 'bg-blue-100' : 'bg-purple-100'}`}>
                  {message.role === 'user' ? (
                    <User className="w-4 h-4 text-blue-600" />
                  ) : (
                    <Bot className="w-4 h-4 text-purple-600" />
                  )}
                </div>
                <div className={`max-w-[70%] px-4 py-3 rounded-2xl ${message.role === 'user' ? 'bg-blue-600 text-white rounded-br-md' : 'bg-gray-50 text-gray-800 border border-gray-200 rounded-bl-md'}`}>
                  <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
                  <p className={`text-xs mt-1 ${message.role === 'user' ? 'text-blue-200' : 'text-gray-400'}`}>
                    {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            ))}

            {isPending && (
              <div className="flex gap-3">
                <div className="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-purple-600" />
                </div>
                <div className="bg-gray-50 border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3">
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Options Pills */}
          {quickOptions.length > 0 && !isPending && (
            <div className="flex-shrink-0 px-4 py-2 border-t border-gray-100 flex flex-wrap gap-2 bg-gray-50/50">
              {quickOptions.map((opt) => (
                <button
                  key={opt}
                  onClick={() => handleSend(opt)}
                  className="px-3 py-1 bg-white hover:bg-teal-50 border border-teal-600/30 text-teal-800 rounded-full text-xs font-semibold shadow-xs transition"
                >
                  {opt}
                </button>
              ))}
            </div>
          )}

          {/* Input area - FIXED HEIGHT, always at bottom */}
          <div className="flex-shrink-0 p-4 border-t border-gray-100">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a message as a patient would..."
                className="flex-1 px-4 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent placeholder:text-gray-400"
              />
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || isPending}
                className="px-4 py-2.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors disabled:opacity-50 flex-shrink-0"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Scenario sidebar */}
        <div className="hidden lg:block w-72 border-l border-gray-200 p-4 flex-shrink-0">
          <h3 className="text-sm font-medium text-gray-900 mb-3">Try a scenario</h3>
          <div className="space-y-2">
            {SCENARIOS.map((scenario, index) => (
              <button
                key={index}
                onClick={() => { setInput(scenario.message); inputRef.current?.focus(); }}
                className="w-full text-left px-3 py-2.5 bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors group"
              >
                <p className="text-xs font-medium text-gray-700 group-hover:text-teal-700">{scenario.label}</p>
                <p className="text-xs text-gray-500 mt-1 line-clamp-2">{scenario.message.slice(0, 80)}...</p>
              </button>
            ))}
          </div>

          <div className="mt-6 pt-4 border-t border-gray-100">
            <h3 className="text-sm font-medium text-gray-900 mb-2">Tips</h3>
            <p className="text-xs text-gray-500 leading-relaxed">
              This simulates how patients interact with the AI concierge via text messaging.
              The AI uses the practice's booking rules and cadence settings to guide conversations.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
