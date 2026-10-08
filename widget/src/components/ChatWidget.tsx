import { useState, useEffect, useRef, useCallback } from 'react';
import type { Message, WidgetConfig } from './config';
import { sendMessage, createSession } from './api';

interface ChatWidgetProps {
  config: WidgetConfig;
}

export function ChatWidget({ config }: ChatWidgetProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    createSession(config.practiceSlug)
      .then((data) => {
        setSessionId(data.session_id);
        setMessages([{
          id: crypto.randomUUID(),
          role: 'assistant',
          content: config.greeting,
          timestamp: Date.now(),
        }]);
      })
      .catch(() => {
        setMessages([{
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'Sorry, we\'re having trouble connecting. Please try again later.',
          timestamp: Date.now(),
        }]);
      });
  }, [config]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading || !sessionId) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await sendMessage(config.practiceSlug, sessionId, text);
      setSessionId(response.sessionId);
      for (const msg of response.messages) {
        setMessages((prev) => {
          if (prev.some((m) => m.id === msg.id)) return prev;
          return [...prev, msg];
        });
      }
    } catch {
      setMessages((prev) => [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Something went wrong. Please try again.',
        timestamp: Date.now(),
      }]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, sessionId, config.practiceSlug]);

  return (
    <div className="hj-widget-root" style={{ position: 'fixed', bottom: 20, right: 20, zIndex: 99999 }}>
      {isOpen ? (
        <div className="hj-chat-window" style={{
          width: 380, maxWidth: 'calc(100vw - 40px)', height: 520,
          maxHeight: 'calc(100vh - 120px)',
          background: '#fff', borderRadius: 16,
          boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}>
          <div style={{ background: config.primaryColor, color: 'white', padding: '16px 20px', flexShrink: 0 }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{config.title}</h3>
            <p style={{ margin: '4px 0 0', fontSize: 12, opacity: 0.9 }}>{config.subtitle}</p>
          </div>

          <div style={{
            flex: 1, overflowY: 'auto', padding: 16,
            display: 'flex', flexDirection: 'column', gap: 12,
          }}>
            {messages.map((msg) => (
              <div key={msg.id} style={{
                maxWidth: '80%', padding: '10px 14px',
                borderRadius: 16, wordWrap: 'break-word', whiteSpace: 'pre-wrap',
                alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                background: msg.role === 'user' ? config.primaryColor : '#f3f4f6',
                color: msg.role === 'user' ? '#fff' : '#1f2937',
                borderBottomRightRadius: msg.role === 'user' ? 4 : 16,
                borderBottomLeftRadius: msg.role === 'assistant' ? 4 : 16,
              }}>
                {msg.content}
              </div>
            ))}
            {isLoading && (
              <div style={{
                alignSelf: 'flex-start', background: '#f3f4f6',
                padding: '10px 14px', borderRadius: 16,
                borderBottomLeftRadius: 4, color: '#6b7280',
                fontSize: 13,
              }}>
                typing...
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div style={{ display: 'flex', padding: '12px 16px', borderTop: '1px solid #e5e7eb', gap: 8, flexShrink: 0 }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
              placeholder={config.placeholder}
              disabled={isLoading}
              style={{
                flex: 1, border: '1px solid #e5e7eb', borderRadius: 24,
                padding: '10px 16px', fontSize: 14, outline: 'none',
              }}
            />
            <button
              onClick={send}
              disabled={isLoading || !input.trim()}
              style={{
                background: config.primaryColor, color: 'white',
                border: 'none', borderRadius: '50%', width: 40, height: 40,
                cursor: 'pointer', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 16, opacity: isLoading || !input.trim() ? 0.5 : 1,
              }}
            >
              &#10148;
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setIsOpen(true)}
          style={{
            width: 60, height: 60, borderRadius: '50%',
            background: config.primaryColor, color: 'white',
            border: 'none', cursor: 'pointer',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 24, transition: 'transform 0.2s',
          }}
          onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.05)'}
          onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
        >
          &#9993;
        </button>
      )}
    </div>
  );
}
