import { Message } from './types';
import { sendMessage, createSession } from './api';

type MessageHandler = (message: Message) => void;
type StatusHandler = (status: 'connecting' | 'connected' | 'error') => void;

export class ChatClient {
  private sessionId: string;
  private practiceSlug: string;
  private onMessage: MessageHandler;
  private onStatus: StatusHandler;
  private abortController: AbortController | null = null;

  constructor(
    practiceSlug: string,
    sessionId: string,
    handlers: { onMessage: MessageHandler; onStatus: StatusHandler }
  ) {
    this.practiceSlug = practiceSlug;
    this.sessionId = sessionId;
    this.onMessage = handlers.onMessage;
    this.onStatus = handlers.onStatus;
  }

  async send(message: string): Promise<void> {
    if (this.abortController) {
      this.abortController.abort();
    }

    this.abortController = new AbortController();

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: message,
      timestamp: Date.now(),
    };

    this.onMessage(userMessage);
    this.onStatus('connecting');

    try {
      const response = await sendMessage(this.practiceSlug, this.sessionId, message);
      this.sessionId = response.sessionId;

      for (const msg of response.messages) {
        this.onMessage(msg);
      }

      this.onStatus('connected');
    } catch (error) {
      console.error('Chat error:', error);
      this.onStatus('error');
    }
  }

  destroy(): void {
    if (this.abortController) {
      this.abortController.abort();
    }
  }
}
