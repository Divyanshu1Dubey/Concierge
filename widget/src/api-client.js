/**
 * HeyJarvis Widget - API Client
 * Handles all communication with the HeyJarvis backend API
 */

export class ApiClient {
  constructor(config) {
    this.apiUrl = config.apiUrl.replace(/\/$/, '');
    this.practiceId = config.practiceId;
  }

  async createConversation(sessionId) {
    const response = await fetch(`${this.apiUrl}/conversations/`, {
      method: 'POST',
      headers: this.getHeaders(sessionId),
      body: JSON.stringify({
        practice_id: this.practiceId,
        source: 'widget',
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to create conversation: ${response.statusText}`);
    }

    return response.json();
  }

  async sendMessage(conversationId, message, sessionId) {
    const response = await fetch(
      `${this.apiUrl}/conversations/${conversationId}/messages/`,
      {
        method: 'POST',
        headers: this.getHeaders(sessionId),
        body: JSON.stringify({
          content: message,
          sender: 'user',
        }),
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to send message: ${response.statusText}`);
    }

    return response.json();
  }

  async getMessages(conversationId, sessionId) {
    const response = await fetch(
      `${this.apiUrl}/conversations/${conversationId}/messages/`,
      {
        method: 'GET',
        headers: this.getHeaders(sessionId),
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch messages: ${response.statusText}`);
    }

    return response.json();
  }

  getHeaders(sessionId) {
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };

    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
    }

    if (this.practiceId) {
      headers['X-Practice-ID'] = this.practiceId;
    }

    return headers;
  }
}
