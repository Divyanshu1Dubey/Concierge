/**
 * HeyJarvis Widget - Message List Component
 * Renders the conversation messages
 */

export class MessageList {
  constructor(container) {
    this.container = container;
    this.messages = [];
  }

  render(messages) {
    this.messages = messages || [];
    this.container.innerHTML = '';

    if (this.messages.length === 0) {
      this.renderWelcome();
      return;
    }

    this.messages.forEach((msg) => {
      this.container.appendChild(this.createMessageElement(msg));
    });

    this.scrollToBottom();
  }

  renderWelcome() {
    const welcome = document.createElement('div');
    welcome.className = 'hj-widget-message-list-welcome';
    welcome.innerHTML = `
      <div class="hj-widget-welcome-icon">🦷</div>
      <p>Start a conversation with our AI assistant</p>
    `;
    this.container.appendChild(welcome);
  }

  createMessageElement(msg) {
    const isUser = msg.sender === 'user';
    const wrapper = document.createElement('div');
    wrapper.className = `hj-widget-message-wrapper hj-widget-message-wrapper-${isUser ? 'user' : 'assistant'}`;

    const bubble = document.createElement('div');
    bubble.className = `hj-widget-message-bubble hj-widget-message-bubble-${isUser ? 'user' : 'assistant'}`;

    const content = document.createElement('div');
    content.className = 'hj-widget-message-content';
    content.textContent = msg.content;

    const time = document.createElement('div');
    time.className = 'hj-widget-message-time';
    time.textContent = this.formatTime(msg.timestamp);

    bubble.appendChild(content);
    bubble.appendChild(time);
    wrapper.appendChild(bubble);

    return wrapper;
  }

  addMessage(msg, animate = true) {
    this.messages.push(msg);
    const element = this.createMessageElement(msg);
    if (animate) {
      element.style.opacity = '0';
      element.style.transform = 'translateY(10px)';
    }
    this.container.appendChild(element);

    if (animate) {
      requestAnimationFrame(() => {
        element.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        element.style.opacity = '1';
        element.style.transform = 'translateY(0)';
      });
    }

    this.scrollToBottom();
  }

  showTypingIndicator() {
    this.removeTypingIndicator();
    const indicator = document.createElement('div');
    indicator.className = 'hj-widget-message-wrapper hj-widget-message-wrapper-assistant';
    indicator.id = 'hj-widget-typing-indicator';

    const bubble = document.createElement('div');
    bubble.className = 'hj-widget-message-bubble hj-widget-message-bubble-assistant hj-widget-typing';

    const dots = document.createElement('div');
    dots.className = 'hj-widget-typing-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';

    bubble.appendChild(dots);
    indicator.appendChild(bubble);
    this.container.appendChild(indicator);
    this.scrollToBottom();
  }

  removeTypingIndicator() {
    const existing = this.container.querySelector('#hj-widget-typing-indicator');
    if (existing) {
      existing.remove();
    }
  }

  renderQuickReplies(replies, onSelect) {
    this.removeQuickReplies();
    const container = document.createElement('div');
    container.className = 'hj-widget-quick-replies';

    replies.forEach((reply) => {
      const chip = document.createElement('button');
      chip.className = 'hj-widget-quick-reply-chip';
      chip.textContent = reply.label;
      chip.type = 'button';
      chip.addEventListener('click', () => {
        this.removeQuickReplies();
        onSelect(reply.value);
      });
      container.appendChild(chip);
    });

    this.container.appendChild(container);
    this.scrollToBottom();
  }

  removeQuickReplies() {
    const existing = this.container.querySelector('.hj-widget-quick-replies');
    if (existing) {
      existing.remove();
    }
  }

  scrollToBottom() {
    requestAnimationFrame(() => {
      this.container.scrollTop = this.container.scrollHeight;
    });
  }

  formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
}
