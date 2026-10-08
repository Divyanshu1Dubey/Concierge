/**
 * HeyJarvis Widget - Chat Window Component
 * The main chat window/modal
 */

export class ChatWindow {
  constructor(container, config) {
    this.container = container;
    this.config = config;
    this.isOpen = false;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="hj-widget-chat-window" role="dialog" aria-label="Chat window" aria-hidden="true">
        <div class="hj-widget-chat-header">
          <div class="hj-widget-chat-header-info">
            <div class="hj-widget-chat-avatar">
              <span class="hj-widget-chat-avatar-text">HJ</span>
            </div>
            <div class="hj-widget-chat-header-text">
              <div class="hj-widget-chat-title">${this.escapeHtml(this.config.title || 'HeyJarvis AI')}</div>
              <div class="hj-widget-chat-subtitle">${this.escapeHtml(this.config.subtitle || 'Chat with us')}</div>
            </div>
          </div>
          <button class="hj-widget-chat-close" type="button" aria-label="Close chat">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        <div class="hj-widget-chat-messages"></div>
        <div class="hj-widget-chat-input-area"></div>
      </div>
    `;

    this.window = this.container.querySelector('.hj-widget-chat-window');
    this.closeBtn = this.container.querySelector('.hj-widget-chat-close');
    this.messagesContainer = this.container.querySelector('.hj-widget-chat-messages');
    this.inputArea = this.container.querySelector('.hj-widget-chat-input-area');

    this.closeBtn.addEventListener('click', () => this.close());

    // Accessibility: close on Escape key
    this.escHandler = (e) => {
      if (e.key === 'Escape' && this.isOpen) {
        this.close();
      }
    };
  }

  setMessageListComponent(messageList) {
    this.messageList = messageList;
    this.messagesContainer.innerHTML = '';
    this.messagesContainer.appendChild(messageList.container);
  }

  setMessageInputComponent(messageInput) {
    this.messageInput = messageInput;
    this.inputArea.innerHTML = '';
    this.inputArea.appendChild(messageInput.container);
  }

  open() {
    this.isOpen = true;
    this.window.classList.add('hj-widget-chat-window-open');
    this.window.setAttribute('aria-hidden', 'false');
    document.addEventListener('keydown', this.escHandler);
    if (this.messageInput) {
      setTimeout(() => this.messageInput.focus(), 300);
    }
  }

  close() {
    this.isOpen = false;
    this.window.classList.remove('hj-widget-chat-window-open');
    this.window.setAttribute('aria-hidden', 'true');
    document.removeEventListener('keydown', this.escHandler);
  }

  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  setLoading(loading) {
    this.window.classList.toggle('hj-widget-chat-window-loading', loading);
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}
