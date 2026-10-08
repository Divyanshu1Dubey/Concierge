/**
 * HeyJarvis Widget - Session Storage
 * Manages localStorage for session persistence and message caching
 */

export class Storage {
  constructor(config) {
    this.sessionKey = config.sessionKey || 'heyjarvis_session';
    this.storeMessages = config.storeMessages !== false;
  }

  getSession() {
    try {
      const data = localStorage.getItem(this.sessionKey);
      return data ? JSON.parse(data) : null;
    } catch (e) {
      console.error('[HeyJarvis] Failed to read session:', e);
      return null;
    }
  }

  setSession(session) {
    try {
      localStorage.setItem(this.sessionKey, JSON.stringify(session));
    } catch (e) {
      console.error('[HeyJarvis] Failed to save session:', e);
    }
  }

  generateSessionId() {
    return 'hj_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 9);
  }

  createSession(conversationId) {
    const session = {
      sessionId: this.generateSessionId(),
      conversationId: conversationId,
      createdAt: new Date().toISOString(),
    };
    this.setSession(session);
    return session;
  }

  getConversationId() {
    const session = this.getSession();
    return session ? session.conversationId : null;
  }

  getSessionId() {
    const session = this.getSession();
    return session ? session.sessionId : null;
  }

  clearSession() {
    try {
      localStorage.removeItem(this.sessionKey);
    } catch (e) {
      console.error('[HeyJarvis] Failed to clear session:', e);
    }
  }

  getStoredMessages() {
    try {
      const key = `${this.sessionKey}_messages`;
      const data = localStorage.getItem(key);
      return data ? JSON.parse(data) : [];
    } catch (e) {
      return [];
    }
  }

  storeMessages(messages) {
    if (!this.storeMessages) return;
    try {
      const key = `${this.sessionKey}_messages`;
      localStorage.setItem(key, JSON.stringify(messages));
    } catch (e) {
      console.error('[HeyJarvis] Failed to store messages:', e);
    }
  }
}
