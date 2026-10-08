import './styles.css';
import { WIDGET_CONFIG } from './config';
import { ChatClient } from './client';
import type { Message } from './types';

class HeyJarvisWidget {
  private container: HTMLElement | null = null;
  private chatWindow: HTMLElement | null = null;
  private messagesContainer: HTMLElement | null = null;
  private inputEl: HTMLInputElement | null = null;
  private toggleBtn: HTMLElement | null = null;
  private client: ChatClient | null = null;
  private isOpen = false;
  private sessionId = '';

  constructor() {
    this.injectStyles();
    this.createElements();
    this.bindEvents();
  }

  init(config: Record<string, string>): void {
    if (config.practiceSlug) {
      WIDGET_CONFIG.practiceSlug = config.practiceSlug;
    }
    if (config.apiUrl) {
      WIDGET_CONFIG.apiUrl = config.apiUrl;
    }
    if (config.primaryColor) {
      WIDGET_CONFIG.primaryColor = config.primaryColor;
      document.documentElement.style.setProperty('--hj-primary', config.primaryColor);
    }

    this.startSession();
  }

  private injectStyles(): void {
    if (document.getElementById('hj-widget-styles')) return;

    const styles = document.createElement('style');
    styles.id = 'hj-widget-styles';
    styles.textContent = `
      .hj-widget-container {
        --hj-primary: #2563eb;
        --hj-bg: #ffffff;
        --hj-text: #1f2937;
        --hj-muted: #6b7280;
        --hj-border: #e5e7eb;
        --hj-user-bg: #2563eb;
        --hj-user-text: #ffffff;
        --hj-ai-bg: #f3f4f6;
        --hj-ai-text: #1f2937;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 99999;
        font-size: 14px;
        line-height: 1.5;
      }

      .hj-toggle-btn {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: var(--hj-primary);
        color: white;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s;
      }

      .hj-toggle-btn:hover { transform: scale(1.05); }

      .hj-chat-window {
        position: absolute;
        bottom: 72px;
        right: 0;
        width: 380px;
        max-width: calc(100vw - 40px);
        height: 520px;
        max-height: calc(100vh - 120px);
        background: var(--hj-bg);
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.12);
        display: none;
        flex-direction: column;
        overflow: hidden;
      }

      .hj-chat-window.open { display: flex; }

      .hj-header {
        background: var(--hj-primary);
        color: white;
        padding: 16px 20px;
        flex-shrink: 0;
      }

      .hj-header h3 { margin: 0; font-size: 16px; font-weight: 600; }
      .hj-header p { margin: 4px 0 0; font-size: 12px; opacity: 0.9; }

      .hj-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .hj-message {
        max-width: 80%;
        padding: 10px 14px;
        border-radius: 16px;
        word-wrap: break-word;
        white-space: pre-wrap;
      }

      .hj-message.user {
        align-self: flex-end;
        background: var(--hj-user-bg);
        color: var(--hj-user-text);
        border-bottom-right-radius: 4px;
      }

      .hj-message.assistant {
        align-self: flex-start;
        background: var(--hj-ai-bg);
        color: var(--hj-ai-text);
        border-bottom-left-radius: 4px;
      }

      .hj-input-area {
        display: flex;
        padding: 12px 16px;
        border-top: 1px solid var(--hj-border);
        gap: 8px;
        flex-shrink: 0;
      }

      .hj-input-area input {
        flex: 1;
        border: 1px solid var(--hj-border);
        border-radius: 24px;
        padding: 10px 16px;
        font-size: 14px;
        outline: none;
        box-sizing: border-box;
      }

      .hj-input-area input:focus { border-color: var(--hj-primary); }

      .hj-input-area button {
        background: var(--hj-primary);
        color: white;
        border: none;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        cursor: pointer;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
      }

      .hj-input-area button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      @media (max-width: 480px) {
        .hj-widget-container {
          bottom: 12px;
          right: 12px;
          left: 12px;
        }
        .hj-chat-window {
          width: 100%;
          right: 0;
          bottom: 68px;
          max-width: none;
          max-height: calc(100vh - 100px);
        }
      }
    `;
    document.head.appendChild(styles);
  }

  private createElements(): void {
    this.container = document.createElement('div');
    this.container.className = 'hj-widget-container';

    this.chatWindow = document.createElement('div');
    this.chatWindow.className = 'hj-chat-window';

    this.chatWindow.innerHTML = `
      <div class="hj-header">
        <h3>${WIDGET_CONFIG.title}</h3>
        <p>${WIDGET_CONFIG.subtitle}</p>
      </div>
      <div class="hj-messages"></div>
      <div class="hj-input-area">
        <input type="text" placeholder="${WIDGET_CONFIG.placeholder}" />
        <button type="button">&#10148;</button>
      </div>
    `;

    this.messagesContainer = this.chatWindow.querySelector('.hj-messages')!;
    this.inputEl = this.chatWindow.querySelector('input')!;

    this.toggleBtn = document.createElement('button');
    this.toggleBtn.className = 'hj-toggle-btn';
    this.toggleBtn.innerHTML = '&#9993;';
    this.toggleBtn.setAttribute('aria-label', 'Open chat');

    this.container.appendChild(this.chatWindow);
    this.container.appendChild(this.toggleBtn);
    document.body.appendChild(this.container);
  }

  private bindEvents(): void {
    this.toggleBtn?.addEventListener('click', () => this.toggle());

    this.chatWindow?.querySelector('button')?.addEventListener('click', () => {
      if (this.inputEl?.value.trim()) {
        this.handleSend();
      }
    });

    this.inputEl?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (this.inputEl.value.trim()) {
          this.handleSend();
        }
      }
    });
  }

  private async startSession(): Promise<void> {
    try {
      const { session_id } = await createSession(WIDGET_CONFIG.practiceSlug);
      this.sessionId = session_id;
      this.addSystemMessage(WIDGET_CONFIG.greeting);
    } catch (error) {
      console.error('Failed to create session:', error);
      this.addSystemMessage('Sorry, we\'re having trouble connecting. Please try again later.');
    }
  }

  private toggle(): void {
    this.isOpen = !this.isOpen;
    this.chatWindow?.classList.toggle('open', this.isOpen);
    this.toggleBtn.innerHTML = this.isOpen ? '&#10005;' : '&#9993;';
    if (this.isOpen) {
      this.inputEl?.focus();
    }
  }

  private async handleSend(): Promise<void> {
    const message = this.inputEl?.value.trim();
    if (!message) return;

    if (!this.client) {
      this.client = new ChatClient(WIDGET_CONFIG.practiceSlug, this.sessionId, {
        onMessage: (msg) => this.appendMessage(msg),
        onStatus: () => {},
      });
    }

    this.inputEl.value = '';

    try {
      await this.client.send(message);
    } catch {
      this.addSystemMessage('Something went wrong. Please try again.');
    }
  }

  private appendMessage(message: Message): void {
    if (!this.messagesContainer) return;

    const el = document.createElement('div');
    el.className = `hj-message ${message.role}`;
    el.textContent = message.content;
    this.messagesContainer.appendChild(el);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }

  private addSystemMessage(content: string): void {
    this.appendMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content,
      timestamp: Date.now(),
    });
  }
}

// Expose globally
declare global {
  interface Window {
    HeyJarvisWidget: typeof HeyJarvisWidget;
  }
}
window.HeyJarvisWidget = HeyJarvisWidget;
