# Handoff: get Concierge live for Raleigh Dentistry

For: Divyanshu and Arpan · From: Avi · Branch: **`integrate-production-readiness`** (open a PR into `main`)

This branch is the latest `main` (including Arpan's Oct 7 commit) plus everything needed for launch.
All tests pass: `.venv/bin/python -m pytest -q`, or `uv run pytest -q`.

## Decisions already made

- **One front desk: `/frontdesk`.** It's the simple inbox (who needs a reply → reply → Approve & send),
  with Settings at `/frontdesk/settings`. The React app is retired: `/desk` and `/app` redirect to
  `/frontdesk`, and Render no longer builds `frontend/`. Delete `frontend/` and `static/dist/` in a cleanup PR
  once you agree.
- **Email goes through the clinic's own mailbox.** Raleigh's email is hosted by **Einstein Mail**
  (`mx.einsteinmail.com`), not Google. Settings → Email has an Einstein Mail preset
  (`smtp.einsteinmail.com:465`, `imap.einsteinmail.com:993`, both checked: valid TLS, password login).
- **Deploy on Render, paid plan with a disk.** The free plan wipes the SQLite database on every
  deploy and sleeps, which also stops the follow-up scheduler. `render.yaml` is already set up.
- **No demo data in production.** Demo logins, the demo clinic and the developer portal at `/` only exist
  when `APP_ENV` is not `production`.

**Still needed:** `main`'s history contains a real Gmail address and app password (from the old
`ensure_demo_data`). Revoke that app password in that Google account if it hasn't been done yet.

## 1. Deploy (≈20 min) — Divyanshu

1. Merge the PR into `main`.
2. Render → New → Blueprint → this repo. It reads `render.yaml`: **Starter plan, 1 instance,
   1 GB disk at `/data`**, `DATABASE_URL=/data/saas.db`, `APP_ENV=production`, current Gemini models,
   and auto-generated `JWT_SECRET` and `ENCRYPTION_KEY`. **Never change `ENCRYPTION_KEY` after launch:**
   clinic mailbox passwords are encrypted with it.
3. Set these secrets in the Render dashboard:

| Variable | Value |
|---|---|
| `APP_URL` | `https://concierge.heyjarvis.ai` |
| `GEMINI_API_KEY` | from https://aistudio.google.com/apikey |
| `DEFAULT_SMTP_HOST` / `DEFAULT_SMTP_PORT` / `DEFAULT_SMTP_USER` / `DEFAULT_SMTP_PASSWORD` / `DEFAULT_SMTP_FROM` | a HeyJarvis sending address (e.g. `noreply@heyjarvis.ai`). **Required:** staff login codes and teammate invites come from it. Without it nobody can sign in. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | optional; only for clinics on Google Workspace (see the end of this doc) |

4. Custom domain `concierge.heyjarvis.ai` in Render, then add the CNAME it shows in heyjarvis.ai's DNS.
   heyjarvis.ai itself stays on Vercel.
5. Check: `https://concierge.heyjarvis.ai/health` returns `{"ok": true}`, and `/` redirects to `/frontdesk`.

## 2. Create the clinic (≈2 min) — Divyanshu

In the Render shell:

```bash
PYTHONPATH=src python -m saas.cli onboard --slug raleigh-dentistry \
  --name "Raleigh Comprehensive and Cosmetic Dentistry" \
  --owner-email <Avi's email> --domain raleighdentistry.com \
  --phone "<clinic phone>" --hours "<office hours>"
```

It prints the front desk link and the website snippet. Send both to Avi. Sign-in uses emailed
codes, so there's no password to hand out.

## 3. Production test — Avi

1. Sign in at `/frontdesk?clinic=raleigh-dentistry` with the emailed code.
2. Settings → **Clinic details**: phone, address, hours (used in emergency replies and email signatures).
3. Settings → **Email**: connect a test mailbox, then **Send me a test email**.
4. Open `/concierge/raleigh-dentistry`, request an appointment with your own email, then **Approve & send**
   in the inbox. Reply from your inbox; within about 2 minutes the reply appears under "Needs your reply".

## 4. Go-live — Avi and the clinic

- [ ] **Ask Einstein Medical for the front desk mailbox password** (or a dedicated mailbox) so Settings →
      Email → Einstein Mail can connect. If the login username isn't the full email address, it goes under
      "Server settings".
- [ ] The clinic approves the follow-up wording (Settings → Follow-ups).
- [ ] HIPAA BAA signed.
- [ ] Add the front desk staff (Settings → Team → Add & send invite).
- [ ] Einstein Medical support pastes the snippet into the site's footer includes on every page.
- [ ] Test on raleighdentistry.com: Chat with us → request → it appears in the inbox.

## What changed (summary for review)

- **Security:** clinic-scoped admin routes, staff-only front desk, rate limits, XSS fixes, emailed login
  codes, demo-only shortcuts, a guard against clinic-entered mail servers pointing at internal addresses,
  and removed teammates lose access immediately.
- **Email:** sending from the clinic mailbox (Einstein Mail, Gmail, Microsoft 365, any IMAP/SMTP),
  read-only reply tracking, automatic Sent-folder detection, test email.
- **Follow-ups:** one editable cadence per clinic with reply rules; every email waits for approval.
- **Chat:** warm design, suggestion buttons, Gemini extraction, and an emergency reply that gives the
  clinic phone number.
- **Merged from main:** `middleware.py` import fix, lead filters, priority-sorted tasks; fixed
  `/fd/ai/action` drafting and the Shorten/Warmer rewrites (they never worked).
- **Deploy fixes:** `requirements.txt` uses `passlib[argon2]` (every login crashed without it);
  single worker (4 workers ran 4 mailbox schedulers).

## Known gaps (not launch blockers)

- SQLite on a disk is fine for a handful of clinics; move to Postgres before scaling.
- The chat collects requests but doesn't answer questions (insurance, hours) yet.
- Repo root has old scratch scripts (`fix_*.py`, test HTML, `public_api_stashed.py`) to delete.

## Optional: "Sign in with Google" (clinics on Google Workspace only)

Raleigh doesn't need this. For future Google clinics: create an OAuth client (Web) with redirect URI
`https://concierge.heyjarvis.ai/oauth/google/callback`, set `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`.
External apps in Testing mode disconnect every 7 days; an Internal app inside the clinic's Workspace doesn't.
Without it, Google clinics use an app password.
