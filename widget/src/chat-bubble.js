/**
 * HeyJarvis Widget - Chat Bubble Component
 * The floating chat bubble button
 */

export class ChatBubble {
  constructor(container, config, onClick) {
    this.container = container;
    this.config = config;
    this.onClick = onClick;
    this.isVisible = false;
    this.unreadCount = 0;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <button
        class="hj-widget-chat-bubble"
        type="button"
        aria-label="Open chat"
        title="Chat with us"
      >
        <span class="hj-widget-chat-bubble-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
        </span>
        <span class="hj-widget-chat-bubble-badge" style="display: none;">
          <span class="hj-widget-chat-bubble-badge-count">0</span>
        </span>
      </button>
    `;

    this.bubble = this.container.querySelector('.hj-widget-chat-bubble');
    this.badge = this.container.querySelector('.hj-widget-chat-bubble-badge');
    this.badgeCount = this.container.querySelector('.hj-widget-chat-bubble-badge-count');

    this.bubble.addEventListener('click', () => {
      if (this.onClick) {
        this.onClick();
      }
    });
  }

  show() {
    this.isVisible = true;
    this.bubble.classList.add('hj-widget-chat-bubble-visible');
  }

  hide() {
    this.isVisible = false;
    this.bubble.classList.remove('hj-widget-chat-bubble-visible');
  }

  setUnreadCount(count) {
    this.unreadCount = count;
    if (count > 0) {
      this.badge.style.display = 'flex';
      this.badgeCount.textContent = count > 99 ? '99+' : count;
    } else {
      this.badge.style.display = 'none';
    }
  }

  pulse() {
    this.bubble.classList.add('hj-widget-chat-bubble-pulse');
    setTimeout(() => {
      this.bubble.classList.remove('hj-widget-chat-bubble-pulse');
    }, 2000);
  }
}
