# HeyJarvis Concierge — WordPress Plugin

Embed the HeyJarvis AI Concierge on your WordPress site with zero code editing.

## Installation

1. In your WordPress admin, go to **Plugins → Add New → Upload Plugin**.
2. Upload the `heyjarvis-concierge.zip` file.
3. Click **Install Now**, then **Activate**.
4. Go to **Settings → HeyJarvis Concierge** and paste your public client key (`pk_...`).
5. Click **Save Settings**.

The widget will appear on every page of your site.

## Configuration

| Setting | Description |
|---------|-------------|
| Public Client Key | Your `pk_...` key from the HeyJarvis dashboard |
| Widget Script URL | Override only if self-hosting the widget JS |
| Enable Widget | Site-wide on/off switch |
| Form Mode | Conversational (default) or structured form |
| Auto-Open | Open widget automatically on page load |
| Page Exclusions | One URL path per line where the widget should NOT appear |

## Page Exclusions

In the **Page Exclusions** textarea, enter one URL path per line:

```
/checkout/
/wp-login.php
/wp-admin/
/checkout/*
```

Glob patterns (`*`) are supported.

## Manual Installation

If you prefer not to use the plugin settings page, paste this into your theme's `footer.php` or a Custom HTML widget:

```html
<script src="https://app.heyjarvis.ai/widget.js" data-heyjarvis-client="pk_YOUR_KEY_HERE" async></script>
```

## Supported Page Builders

- Gutenberg (block editor)
- Classic Editor
- Elementor
- Divi
- Beaver Builder
- WPBakery
- Full Site Editing themes

## Troubleshooting

**Widget not appearing?**
- Check that your public client key is set in Settings → HeyJarvis Concierge.
- Check that "Enable Widget" is set to "Yes".
- Verify your domain is in the allowed domains list in the HeyJarvis dashboard.

**Widget conflicts with my theme?**
- The widget uses Shadow DOM and is fully CSS-isolated.
- If you see issues, disable other chat plugins that inject `<iframe>` elements.

## Requirements

- WordPress 5.8 or later
- PHP 7.4 or later

## Support

Email: support@heyjarvis.ai
Docs: https://docs.heyjarvis.ai
