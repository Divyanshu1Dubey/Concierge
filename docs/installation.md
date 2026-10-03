# Installation Guide

Add HeyJarvis Concierge to your website in minutes. Choose your platform below.

---

## Universal JavaScript Snippet (Recommended)

This works on **any** website. Paste this before `</body>`:

```html
<script
  async
  src="https://YOUR-HOST/widget.js"
  data-heyjarvis-client="YOUR_PUBLIC_KEY"
  data-heyjarvis-form="false"
  data-heyjarvis-auto-open="false"
></script>
```

Replace:
- `YOUR_HOST` with your HeyJarvis app URL (for example `https://your-app.railway.app`)
- `YOUR_PUBLIC_KEY` with your public API key from the HeyJarvis dashboard

**Optional attributes:**
- `data-heyjarvis-form="true"` — show a form instead of chat mode
- `data-heyjarvis-auto-open="true"` — open the widget automatically after 500ms

---

## WordPress

### Option A: Insert Headers and Footers plugin
1. Install and activate the [Insert Headers and Footers](https://wordpress.org/plugins/insert-headers-and-footers/) plugin.
2. Go to **Settings → Insert Headers and Footers → Scripts in Footer**.
3. Paste the universal snippet above.
4. Save.

### Option B: Theme editor
1. Go to **Appearance → Theme File Editor**.
2. Select your theme and open `footer.php`.
3. Paste the snippet before `</body>`.
4. Save.

---

## Webflow

1. Open your project in Webflow.
2. Click the **Project Settings** icon (gear icon).
3. Go to the **Custom Code** tab.
4. Paste the snippet in **Before `</body>` Tag Code**.
5. Save and publish.

---

## Wix

1. Go to your Wix site dashboard.
2. Click **Settings → Advanced → Tracking & Analytics**.
3. Click **+ Add New Code** under **Custom Code**.
4. Paste the snippet.
5. Set **Place Code in:** `Body - end`.
6. Save and publish.

---

## Squarespace

1. Go to **Settings → Advanced → Code Injection**.
2. Scroll to **Footer**.
3. Paste the snippet in the **Footer** code box.
4. Save.

---

## Plain HTML

1. Open your site files locally.
2. Open the main HTML file (for example `index.html`).
3. Paste the snippet before `</body>`.
4. Upload the updated file.

---

## Google Tag Manager (GTM)

1. Open your GTM workspace.
2. Go to **Tags → New**.
3. Click **Tag Configuration → Custom HTML**.
4. Paste the snippet.
5. Under **Triggering**, select **All Pages**.
6. Save and publish your container.

---

## React / Next.js

### React (client component)
Create a `HeyJarvisWidget.jsx` component:

```jsx
'use client';
import { useEffect } from 'react';

export default function HeyJarvisWidget({ publicKey }) {
  useEffect(() => {
    const script = document.createElement('script');
    script.src = process.env.NEXT_PUBLIC_HEYJARVIS_WIDGET_URL || '/widget.js';
    script.setAttribute('data-heyjarvis-client', publicKey);
    script.setAttribute('data-heyjarvis-form', 'false');
    script.setAttribute('async', '');
    document.body.appendChild(script);
    return () => document.body.removeChild(script);
  }, [publicKey]);

  return null;
}
```

Use it in your layout:
```jsx
import HeyJarvisWidget from './HeyJarvisWidget';

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        {children}
        <HeyJarvisWidget publicKey="pk_xxx" />
      </body>
    </html>
  );
}
```

### Next.js App Router
Add to `app/layout.tsx`:
```tsx
import HeyJarvisWidget from '@/components/HeyJarvisWidget';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <HeyJarvisWidget publicKey={process.env.NEXT_PUBLIC_HEYJARVIS_KEY!} />
      </body>
    </html>
  );
}
```

---

## iframe Embed Option

If you prefer an iframe, use your hosted concierge page URL:

```html
<iframe
  src="https://YOUR-HOST/concierge/your-tenant-slug"
  title="Chat with us"
  allow="microphone"
  style="width:100%;max-width:960px;height:620px;border:0;border-radius:14px;"
></iframe>
```

Set a height that works for your layout. For mobile, `height: 100dvh` works well.

---

## Troubleshooting

### Widget does not appear
- Confirm the `src` URL is correct and reachable.
- Confirm `data-heyjarvis-client` matches your public key exactly.
- Check the browser console for 404s or JS errors.
- Ensure the script is loaded after `</body>` or with `async`/`defer`.

### Chat returns an error
- Verify your tenant is enabled in the HeyJarvis dashboard.
- If using a custom domain, confirm the domain is added and verified in **Settings → Domains**.
- Check that `widget.js` is served from the same host as your API, or that CORS is configured.

### CORS / origin errors
- Add your site domain in **Settings → Domains** inside the HeyJarvis dashboard.
- Verify the domain is marked **Verified**.
- If testing locally, add `localhost` or `127.0.0.1` as a development domain.

### Messages do not send
- Confirm the backend health endpoint returns `{"ok": true}`.
- Ensure SMTP or email delivery settings are configured if you expect lead notifications.

### Styling conflicts
- The widget is scoped to avoid conflicts. If issues persist, remove custom CSS resets that may affect `all: initial` behavior.
