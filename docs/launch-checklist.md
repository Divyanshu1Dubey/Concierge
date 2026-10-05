# Launching a clinic (first one: Raleigh Dentistry)

## 1. Host the concierge (not on Vercel)

The concierge needs an always-on process (it checks Gmail every 2 minutes), a
persistent database file, and long-lived SMTP/IMAP connections. Vercel's
serverless functions can't do that. Keep heyjarvis.ai on Vercel and run this
service on Railway (config already in the repo) at a subdomain:

1. Railway → New project → deploy this repo.
2. Add a **Volume** mounted at `/data`.
3. Variables:
   | Variable | Value |
   |---|---|
   | `APP_ENV` | `production` |
   | `APP_URL` | `https://concierge.heyjarvis.ai` |
   | `DATABASE_URL` | `/data/saas.db` |
   | `JWT_SECRET` | 64 random chars (`python -c "import secrets;print(secrets.token_urlsafe(48))"`) |
   | `ENCRYPTION_KEY` | another 32+ random chars. **Never change it later**: stored mailbox credentials are encrypted with it |
   | `GEMINI_API_KEY` | from https://aistudio.google.com/apikey |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | see step 3 (optional if using an app password) |
4. Keep **one** instance/worker (the mailbox scheduler runs inside it).
5. Custom domain `concierge.heyjarvis.ai` in Railway, then add the CNAME it
   shows in heyjarvis.ai's DNS (wherever the domain is managed, e.g. Vercel → Domains).
6. Check `https://concierge.heyjarvis.ai/health` returns `{"ok": true}`.

The server refuses to start in production if `JWT_SECRET` / `ENCRYPTION_KEY` are placeholders.

## 2. Create the clinic

From a Railway shell (or locally pointed at the production database):

```bash
python -m saas.cli onboard --slug raleigh-dentistry \
  --name "Raleigh Comprehensive and Cosmetic Dentistry" \
  --owner-email <front desk login email> --domain raleighdentistry.com
```

It prints the front desk link and the website snippet. Staff log in with a 6-digit code emailed
to them, so set `DEFAULT_SMTP_HOST/PORT/USER/PASSWORD/FROM` (a HeyJarvis sending address) in Railway.

## 3. Connect the clinic's Gmail

Two options in **Front desk → Settings → Clinic mailbox**:

**A. Sign in with Google (recommended).** Needs a Google Cloud OAuth client:
1. console.cloud.google.com → new project → *APIs & Services → OAuth consent screen*.
   - If the project is created **inside the clinic's Google Workspace** (by their admin), choose
     **Internal**: no Google review, tokens don't expire.
   - If it's in HeyJarvis's own Google account it must be **External**. While in *Testing*
     mode, add the clinic address as a test user, and note that Google expires the
     connection **every 7 days** (reconnect in Settings). Going to *Production* with the Gmail
     scope requires Google's verification and security assessment (weeks).
2. *Credentials → Create OAuth client ID → Web application*. Authorized redirect URI:
   `https://concierge.heyjarvis.ai/oauth/google/callback`
3. Put the client ID/secret in Railway variables, redeploy.

**B. App password.** Google Account → Security → 2-Step Verification → App passwords.
Works today if the clinic's Workspace admin hasn't disabled app passwords.

Then **Settings → Follow-up cadence**: review the steps and rules and wording before the first patient.

## 4. Put the widget on raleighdentistry.com

The site runs on **Einstein Medical** (not WordPress). Ask Einstein support to add the
snippet to the site's footer includes on every page, or add it through the clinic's
Google Tag Manager if the clinic controls that container. Then:

- open the site, click **Chat with us**, submit a test request with your own email;
- confirm it appears in the front desk, the first-reply draft appears under **To approve**,
  sending it reaches your inbox, and replying + **Sync mail** shows the reply.

## 5. Before real patients

- [ ] Clinic has approved the cadence wording and the AI reply instructions.
- [ ] Business associate agreement (BAA) in place: patient emails and chats are stored in HeyJarvis.
- [ ] Owner can log in with an emailed code (needs DEFAULT_SMTP_* set).
- [ ] Someone checks **To approve** daily (nothing is sent automatically).
