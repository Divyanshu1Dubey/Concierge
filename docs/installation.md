# HeyJarvis Concierge — Installation Guide

*Tested with: web-production-21c4f.up.railway.app*

---

## Overview

There are **four ways** to add HeyJarvis Concierge to any website:

| Method | Difficulty | Best For |
|--------|-----------|----------|
| 1. Universal Script Tag | Easy | Any website |
| 2. Direct iframe | Easy | Quick embed, no customization |
| 3. Hosted Page Link | Easiest | Sharing via email/social |
| 4. WordPress Plugin | Medium | WordPress sites |

---

## Method 1: Universal Script Tag (Recommended)

This is the **primary** installation method. One line of code adds the full widget to any site.

### Step 1: Get your Public Client Key

Log into your HeyJarvis dashboard and copy your **Public Client Key**.
It looks like: `pk_xxxxxxxxxxxxxxxxxxxx`

### Step 2: Paste this snippet

Place this **anywhere** in your HTML, preferably just before the closing `</body>` tag:

```html
<script
  async
  src="https://web-production-21c4f.up.railway.app/widget.js"
  data-heyjarvis-client="YOUR_PUBLIC_CLIENT_KEY">
</script>
```

Replace `YOUR_PUBLIC_CLIENT_KEY` with your actual key.

### Step 3: Done

That's it. The widget will:
- Load asynchronously (won't block your page)
- Auto-detect your page URL and referrer
- Show the chat launcher in the bottom-right corner
- Handle the entire conversation flow
- Create structured leads

### Supported Platforms

| Platform | Where to paste |
|----------|---------------|
| WordPress | Appearance → Widgets, or use "Custom HTML" block |
| Webflow | Page Settings → Custom Code → `</body>` tag |
| Wix | Settings → Tracking & Analytics → Custom Code |
| Squarespace | Settings → Advanced → Code Injection → Footer |
| Shopify | Online Store → Themes → Edit code → `theme.liquid` |
| React/Next.js | Add to your root layout component |
| Plain HTML | Before `</body>` |
| Google Tag Manager | Trigger on "All Pages", paste in Custom HTML tag |

---

## Method 2: Direct iframe Embed

If you want the full Concierge experience as a standalone section on a page:

```html
<iframe
  src="https://web-production-21c4f.up.railway.app/concierge/YOUR_TENANT_SLUG"
  width="100%"
  height="600"
  frameborder="0"
  style="border-radius: 12px; max-width: 500px;"
  title="HeyJarvis Concierge">
</iframe>
```

Replace `YOUR_TENANT_SLUG` with your tenant slug (e.g., `raleigh`).

---

## Method 3: Hosted Page Link

Every tenant gets a standalone Concierge URL. Use this to:

- Share via email: *"Click here to request an appointment"*
- Link from social media
- Open as a standalone booking page

```
https://web-production-21c4f.up.railway.app/concierge/YOUR_TENANT_SLUG
```

Example for Raleigh:
```
https://web-production-21c4f.up.railway.app/concierge/raleigh
```

---

## Method 4: WordPress Plugin

### Option A: Code Snippets Plugin (no PHP file needed)

1. Install the **"WPCode"** or **"Code Snippets"** plugin
2. Add a new snippet with type "HTML Snippet"
3. Paste:

```html
<script
  async
  src="https://web-production-21c4f.up.railway.app/widget.js"
  data-heyjarvis-client="YOUR_PUBLIC_CLIENT_KEY">
</script>
```

4. Set it to run on "Frontend" / "Everywhere"
5. Save and activate

### Option B: Theme's functions.php

Add to your child theme's `functions.php`:

```php
function heyjarvis_concierge_widget() {
    ?>
    <script
      async
      src="https://web-production-21c4f.up.railway.app/widget.js"
      data-heyjarvis-client="YOUR_PUBLIC_CLIENT_KEY">
    </script>
    <?php
}
add_action('wp_footer', 'heyjarvis_concierge_widget');
```

---

## Testing Locally

### Step 1: Start the server

```bash
python -m uvicorn saas.main:app --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Open the test HTML file

Save the test file (provided below) as `test-concierge.html` and open it in your browser:

```bash
# Option A: Direct open
start test-concierge.html

# Option B: Serve via simple HTTP server
python -m http.server 8080
# Then open http://localhost:8080/test-concierge.html
```

### Step 3: Verify

1. You should see the Concierge form appear
2. Fill in the form and submit
3. Check the outbox folder for the generated email

---

## How the Widget Works

### Data Flow

```
Visitor loads your page
        │
        ▼
widget.js loads asynchronously
        │
        ▼
Widget renders form into #concierge-form (or floating launcher)
        │
        ▼
Visitor fills form / interacts with chat
        │
        ▼
On submit: POST to /public/requests
        │
        ▼
Server processes:
  • Validates origin/domain
  • Rate limits
  • Creates conversation record
  • Creates lead record
  • Generates email draft / sends notification
        │
        ▼
Front desk receives the request
```

### What Gets Sent

The widget submits this data to the server:

| Field | Source | Required |
|-------|--------|----------|
| `name` | Visitor input | Yes |
| `email` | Visitor input | Yes |
| `phone` | Visitor input | No |
| `message` | Visitor input | Yes |
| `intent` | AI-detected from message | Auto |
| `page_url` | Current page URL | Auto |
| `referrer` | Document.referrer | Auto |
| `user_agent` | Navigator.userAgent | Auto |
| `tenant_id` | From public key | Auto |

### Security

- The **public key** is not a secret — it's safe to embed in JavaScript
- Your **tenant secrets** (SMTP passwords, API keys) are never sent to the browser
- Domain validation ensures requests come from your allowed domains
- Rate limiting prevents abuse

---

## Troubleshooting

### Widget doesn't appear

1. Check browser console for errors (F12 → Console)
2. Make sure `data-heyjarvis-client` has the correct public key
3. Verify the script URL matches your Railway URL
4. Check that the page URL is in your allowed domains

### Form submits but no email arrives

1. Check the `outbox/sent/` folder for saved emails (if in dry-run mode)
2. Verify SMTP settings in the dashboard
3. Check server logs for errors

### "Not Found" or 404 errors

1. Make sure you're using the correct tenant slug
2. Verify the Railway deployment is running (`curl https://web-production-21c4f.up.railway.app/health`)

---

## Current URLs

| Service | URL |
|---------|-----|
| **Railway App** | https://web-production-21c4f.up.railway.app |
| **Health Check** | https://web-production-21c4f.up.railway.app/health |
| **API Docs** | https://web-production-21c4f.up.railway.app/docs |
| **Widget JS** | https://web-production-21c4f.up.railway.app/widget.js |
| **Front Desk** | https://web-production-21c4f.up.railway.app/desk |
| **Operations** | https://web-production-21c4f.up.railway.app/ops |

---

## Next Steps

1. Test with the HTML file below
2. Create your tenant in the dashboard
3. Get your public client key
4. Add the script tag to your website
5. Verify the form appears and submits correctly
6. Check that emails arrive at your front desk
