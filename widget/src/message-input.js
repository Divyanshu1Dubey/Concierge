/**
 * HeyJarvis Widget - Message Input Component
 * Handles user message input and submission
 */

export class MessageInput {
  constructor(container, config, onSubmit) {
    this.container = container;
    this.config = config;
    this.onSubmit = onSubmit;
    this.disabled = false;

    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="hj-widget-input-wrapper">
        <textarea
          class="hj-widget-input"
          placeholder="${this.escapeHtml(this.config.placeholder || 'Type your message...')}"
          rows="1"
          aria-label="Message"
        ></textarea>
        <button class="hj-widget-send-btn" type="button" aria-label="Send message" disabled>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        </button>
      </div>
      <div class="hj-widget-input-footer">
        <span>Powered by HeyJarvis AI</span>
      </div>
    `;

    this.input = this.container.querySelector('.hj-widget-input');
    this.sendBtn = this.container.querySelector('.hj-widget-send-btn');

    this.bindEvents();
  }

  bindEvents() {
    this.sendBtn.addEventListener('click', () => this.handleSend());

    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }
    });

    this.input.addEventListener('input', () => {
      this.updateSendButton();
      this.autoResize();
    });
  }

  handleSend() {
    const text = this.input.value.trim();
    if (!text || this.disabled) return;

    this.input.value = '';
    this.input.style.height = 'auto';
    this.updateSendButton();

    if (this.onSubmit) {
      this.onSubmit(text);
    }
  }

  updateSendButton() {
    const hasText = this.input.value.trim().length > 0;
    this.sendBtn.disabled = !hasText || this.disabled;
  }

  autoResize() {
    this.input.style.height = 'auto';
    this.input.style.height = Math.min(this.input.scrollHeight, 120) + 'px';
  }

  focus() {
    if (this.input) {
      this.input.focus();
    }
  }

  setDisabled(disabled) {
    this.disabled = disabled;
    this.input.disabled = disabled;
    this.sendBtn.disabled = disabled || !this.input.value.trim();
    this.input.placeholder = disabled ? 'Waiting for response...' : (this.config.placeholder || 'Type your message...');
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}
