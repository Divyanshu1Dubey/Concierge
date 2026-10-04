# Widget Installation Guides

## Universal JavaScript Snippet

This is the primary installation method. It works on every platform.

```html
<script
  async
  src="https://app.heyjarvis.ai/widget.js"
  data-heyjarvis-client="YOUR_PUBLIC_KEY"
  data-heyjarvis-form="false"
  data-heyjarvis-auto-open="false">
</script>
```

Replace `YOUR_PUBLIC_KEY` with your public client key from the HeyJarvis dashboard.

Place this before `</body>` on every page where you want the widget.

## WordPress

### Installation

1. Download the plugin ZIP from your HeyJarvis dashboard
2. In WordPress admin, go to Plugins → Add New → Upload Plugin
3. Select the ZIP file and install
4. Activate the plugin
5. Go to Settings → HeyJarvis Concierge
6. Paste your Client Key
7. Save

### Features

- Site-wide enable/disable
- Page exclusions
- Auto-open toggle
- Form/conversational mode
- Async loading
- No theme conflicts

### Manual Installation

If you can't use the plugin:

```php
<!-- Add to your theme's footer.php before </body> -->
<script
  async
  src="https://app.heyjarvis.ai/widget.js"
  data-heyjarvis-client="YOUR_PUBLIC_KEY"
  data-heyjarvis-form="false"
  data-heyjarvis-auto-open="false">
</script>
```

## Webflow

1. Go to Project Settings → Custom Code
2. In "Before </body> Code", paste:
```html
<script
  async
  src="https://app.heyjarvis.ai/widget.js"
  data-heyjarvis-client="YOUR_PUBLIC_KEY"
  data-heyjarvis-form="false">
</script>
```
3. Save and publish

## Wix

1. Go to Settings → Advanced → Custom Code
2. Click "Add Custom Code"
3. Paste the snippet
4. Set placement: "Body - start"
5. Add to all pages
6. Save and publish

## Squarespace

1. Go to Settings → Advanced → Code Injection
2. In "Footer", paste the snippet
3. Save

## React

```jsx
// App.js or _app.js
import { useEffect } from 'react';

function App() {
  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://app.heyjarvis.ai/widget.js';
    script.async = true;
    script.setAttribute('data-heyjarvis-client', 'YOUR_PUBLIC_KEY');
    script.setAttribute('data-heyjarvis-form', 'false');
    document.body.appendChild(script);
  }, []);

  return <YourApp />;
}
```

## Next.js

```tsx
// app/layout.tsx or pages/_app.tsx
'use client';

import { useEffect } from 'react';

export default function RootLayout({ children }) {
  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://app.heyjarvis.ai/widget.js';
    script.async = true;
    script.setAttribute('data-heyjarvis-client', 'YOUR_PUBLIC_KEY');
    document.body.appendChild(script);
  }, []);

  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

## Google Tag Manager

1. In GTM, create a new Custom HTML tag
2. Paste the snippet
3. Set trigger: "All Pages"
4. Publish

```html
<script
  async
  src="https://app.heyjarvis.ai/widget.js"
  data-heyjarvis-client="YOUR_PUBLIC_KEY"
  data-heyjarvis-form="false">
</script>
```

## Plain HTML

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Website</title>
</head>
<body>
  <!-- Your website content -->

  <!-- HeyJarvis Concierge -->
  <script
    async
    src="https://app.heyjarvis.ai/widget.js"
    data-heyjarvis-client="YOUR_PUBLIC_KEY"
    data-heyjarvis-form="false">
  </script>
</body>
</html>
```

## Testing Installation

After installing:

1. Open your website in an incognito window
2. Look for the chat launcher in the bottom-right corner
3. Click it to open the Concierge
4. Verify it loads your tenant's branding and greeting

In your HeyJarvis dashboard, check:
- Widget status shows "Connected"
- Analytics show widget_loaded event
- Conversations appear when visitors interact
