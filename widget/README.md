# HeyJarvis Embeddable Widget

Framework-independent chat widget for the HeyJarvis AI Concierge platform.

## Installation

### Option 1: Script Tag (Recommended)

Add this before the closing `</body>` tag of your website:

```html
<script
  src="https://cdn.heyjarvis.io/widget/latest/widget.js"
  data-practice-slug="YOUR_PRACTICE_SLUG"
  data-api-url="https://api.heyjarvis.io"
  data-primary-color="#06B6D4"
  data-title="Your Practice Name"
  data-subtitle="How can we help?">
</script>
```

### Option 2: WordPress Plugin

Install and activate the HeyJarvis WordPress plugin from your admin panel.

### Option 3: npm

```bash
npm install @heyjarvis/widget
```

```javascript
import HeyJarvis from '@heyjarvis/widget';
// The widget auto-initializes via script tag.
// For programmatic control:
HeyJarvis.open();
HeyJarvis.close();
HeyJarvis.toggle();
HeyJarvis.destroy();
```

## Configuration

| Attribute | Global Variable | Type | Default | Description |
|-----------|----------------|------|---------|-------------|
| `data-practice-slug` | `practiceSlug` | string | `''` | Your practice identifier |
| `data-api-url` | `apiUrl` | string | `''` | HeyJarvis API base URL |
| `data-primary-color` | `primaryColor` | string | `#06B6D4` | Theme color (hex) |
| `data-title` | `title` | string | `'HeyJarvis'` | Widget header title |
| `data-subtitle` | `subtitle` | string | `'How can we help?'` | Welcome subtitle |

### Global Config

You can also set configuration globally before the widget script loads:

```javascript
window.heyjarvisConfig = {
  practiceSlug: 'my-practice',
  apiUrl: 'https://api.heyjarvis.io',
  primaryColor: '#06B6D4',
  title: 'My Practice',
  subtitle: 'How can we help?'
};
```

## API Requirements

The HeyJarvis API must expose the following endpoints:

### POST `/api/v1/conversations/`

Creates a new conversation session.

**Request body:**
```json
{
  "practice_slug": "string",
  "channel": "widget",
  "metadata": { "user_agent": "string" }
}
```

**Response:**
```json
{
  "id": "uuid",
  "session_id": "uuid",
  "messages": [],
  "status": "active"
}
```

### GET `/api/v1/conversations/{id}/`

Retrieves a conversation with all messages.

**Response:**
```json
{
  "id": "uuid",
  "session_id": "uuid",
  "status": "active",
  "messages": [
    {
      "id": "uuid",
      "direction": "inbound",
      "content": "Hello!",
      "created_at": "2026-01-01T00:00:00Z"
    },
    {
      "id": "uuid",
      "direction": "outbound",
      "content": "Hi there! How can I help?",
      "created_at": "2026-01-01T00:00:01Z"
    }
  ]
}
```

### POST `/api/v1/messages/`

Sends a message to a conversation.

**Request body:**
```json
{
  "conversation": "uuid",
  "direction": "inbound",
  "content": "string",
  "channel": "widget"
}
```

**Response:**
```json
{
  "id": "uuid",
  "conversation": "uuid",
  "direction": "inbound",
  "content": "string",
  "created_at": "2026-01-01T00:00:00Z"
}
```

## Features

- **Framework-independent**: Works with any website (plain HTML, React, Vue, WordPress, etc.)
- **Session persistence**: Uses localStorage to maintain conversation across page reloads
- **Auto-polling**: Checks for new messages every 2 seconds when panel is closed
- **Mobile responsive**: Full-screen mode on devices under 480px
- **Markdown formatting**: Basic bold, italic, and line-break support
- **Typing indicator**: Animated dots while waiting for bot response
- **Message timestamps**: AM/PM format on all messages
- **Keyboard shortcuts**: Enter to send, Shift+Enter for newline, Escape to close
- **Public API**: `HeyJarvis.open()`, `HeyJarvis.close()`, `HeyJarvis.toggle()`, `HeyJarvis.destroy()`
- **Accessibility**: ARIA labels, keyboard navigation
- **Themeable**: Custom primary color with auto-generated gradients
- **Self-contained**: No external dependencies (CSS and JS are inline)

## Browser Support

- Chrome 60+
- Firefox 55+
- Safari 11+
- Edge 79+

## License

(c) 2026 HeyJarvis. All rights reserved.
