/**
 * HeyJarvis Widget - Core Widget Class
 * Orchestrates all components and manages widget state
 */

export class HeyJarvisWidget {
  constructor(config) {
    this.config = { ...config };
    this.session = null;
    this.conversationId = null;
    this.messages = [];
    this.isProcessing = false;
    this.quickReplyState = 'initial';

    this.init();
  }

  init() {
    // Create widget container
    this.createContainer();

    // Initialize components
    this.chatWindow = new ChatWindow(
      this.host.querySelector('.hj-widget-chat-window-container'),
      this.config
    );

    this.messageList = new MessageList(
      this.hat);
    this.chatWindow.setMessageListComponent(this.messageList);

    this.messageInput = new MessageInput(
      this.host.querySelector('.hj-widget-chat-input-area'),
      this.config,
      (text) => this.handleUserMessage(text)
    );
    this.chatWindow.setMessageInputComponent(this.messageInput);

    this.chatBubble = new ChatBubble(
      this.host.querySelector('.hj-widget-chat-bubble-container'),
      this.config,
      () => this.chatWindow.toggle()
    );

    // Initialize API client and storage
    this.apiClient = new ApiClient(this.config);
    this.storage = new Storage(this.config);

    // Setup message handler
    this.messageInputEl = this.messageInput;

    // Restore session or create new
    this.restoreOrCreateSession();

    // Show bubble
    this.chatBubble.show();

    // Open on load if configured
    if (this.config.openOnLoad) {
      setTimeout(() => this.chatWindow.open(), 500);
    }
  }

  createContainer() {
    this.host = document.createElement('div');
    this.host.className = 'hj-widget-host';
    this.host.setAttribute('role', 'application');
    this.host.setAttribute('aria-label', 'HeyJarvis Chat');

    this.host.innerHTML = `
      <div class="hj-widget-chat-bubble-container"></div>
      <div class="hj-widget-chat-window-container"></div>
    `;

    document.body.appendChild(this.host);
  }

  async restoreOrCreateSession() {
    // Try to restore existing session
    const existingSession = this.storage.getSession();

    if (existingSession && existingSession.conversationId) {
      this.session = existingSession;
      this.conversationId = existingSession.conversationId;

      // Load existing messages
      try {
        const data = await this.apiClient.getMessages(
          this.conversationId,
          this.session.sessionId
        );
        this.messages = data.results || data || [];
        this.storage.storeMessages(this.messages);
        this.messageList.render(this.messages);
      } catch (e) {
        console.error('[HeyJarvis] Failed to load messages:', e);
        // Show cached messages if available
        const cached = this.storage.getStoredMessages();
        if (cached.length > 0) {
          this.messages = cached;
          this.messageList.render(this.messages);
        }
      }

      this.showWelcomeBack();
    } else {
      // Create new session
      try {
        const conversation = await this.apiClient.createConversation(null);
        this.conversationId = conversation.id;
        this.session = this.storage.createSession(this.conversationId);

        // Show welcome message
        this.showWelcomeMessage();
      } catch (e) {
        console.error('[HeyJarvis] Failed to create session:', e);
        // Still show welcome, will retry on first message
        this.showWelcomeMessage();
      }
    }
  }

  showWelcomeMessage() {
    const welcomeMsg = {
      id: 'welcome',
      sender: 'assistant',
      content: this.config.welcomeMessage || 'Hi! How can I help you today?',
      timestamp: new Date().toISOString(),
    };

    this.messages.push(welcomeMsg);
    this.messageList.addMessage(welcomeMsg);
    this.storage.storeMessages(this.messages);

    // Show initial quick replies
    this.showQuickReplies('initial');
  }

  showWelcomeBack() {
    if (this.messages.length > 0) {
      // Already has messages, nothing to show
      return;
    }

    // No messages yet, show welcome
    this.showWelcomeMessage();
  }

  showQuickReplies(state) {
    this.quickReplyState = state;
    const replies = state === 'initial'
      ? QUICK_REPLIES.initial
      : QUICK_REPLIES.appointment;

    this.messageList.renderQuickReplies(replies, (value) => {
      this.handleUserMessage(value);
    });
  }

  async handleUserMessage(text) {
    if (this.isProcessing) return;
    this.isProcessing = true;

    // Disable input while processing
    this.messageInput.setDisabled(true);
    this.messageList.removeQuickReplies();

    // If no conversation, try to create one
    if (!this.conversationId) {
      try {
        const conversation = await this.apiClient.createConversation(
          this.session ? this.session.sessionId : null
        );
        this.conversationId = conversation.id;
        if (this.session) {
          this.session.conversationId = this.conversationId;
          this.storage.setSession(this.session);
        }
      } catch (e) {
        this.showError('Unable to connect. Please try again.');
        this.messageInput.setDisabled(false);
        this.isProcessing = false;
        return;
      }
    }

    // Add user message
    const userMsg = {
      id: 'user_' + Date.now(),
      sender: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    this.messages.push(userMsg);
    this.messageList.addMessage(userMsg);
    this.storage.storeMessages(this.messages);

    // Check for appointment-related keywords to change quick replies
    this.updateQuickReplyState(text);

    // Show typing indicator
    this.messageList.showTypingIndicator();

    try {
      // Send to API
      const response = await this.apiClient.sendMessage(
        this.conversationId,
        text,
        this.session ? this.session.sessionId : null
      );

      // Remove typing indicator
      this.messageList.removeTypingIndicator();

      // Add assistant response
      const assistantMsg = {
        id: response.id || 'assistant_' + Date.now(),
        sender: 'assistant',
        content: response.content || response.message || response.text || 'Thanks for your message!',
        timestamp: response.timestamp || new Date().toISOString(),
      };

      this.messages.push(assistantMsg);
      this.messageList.addMessage(assistantMsg);
      this.storage.storeMessages(this.messages);

      // Show contextual quick replies
      this.showQuickReplies(this.quickReplyState);

    } catch (e) {
      console.error('[HeyJarvis] Message error:', e);
      this.messageList.removeTypingIndicator();

      // Add error message
      const errorMsg = {
        id: 'error_' + Date.now(),
        sender: 'assistant',
        content: 'Something went wrong. Please try again or call our office directly.',
        timestamp: new Date().toISOString(),
      };

      this.messages.push(errorMsg);
      this.messageList.addMessage(errorMsg);
    }

    this.messageInput.setDisabled(false);
    this.isProcessing = false;
  }

  updateQuickReplyState(text) {
    const lower = text.toLowerCase();
    const appointmentKeywords = ['appoint', 'book', 'schedule', 'visit', 'come in', 'see a doctor', 'checkup', 'check-up'];

    if (this.quickReplyState === 'initial' && appointmentKeywords.some(kw => lower.includes(kw))) {
      this.quickReplyState = 'appointment';
    }
  }

  showError(message) {
    const errorMsg = {
      id: 'error_' + Date.now(),
      sender: 'assistant',
      content: message,
      timestamp: new Date().toISOString(),
    };

    this.messages.push(errorMsg);
    this.messageList.addMessage(errorMsg);
  }
}
