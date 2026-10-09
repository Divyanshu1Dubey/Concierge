# Handoff: get Concierge live for Raleigh Dentistry

For: Avi, Divyanshu and Arpan · Branch: **`integrate-production-readiness`** (open a PR into `main`)

This branch is the latest `main` (including Arpan's Oct 7 commit) plus everything needed for launch.
All tests pass: `.venv/bin/python -m pytest -q`, or `uv run pytest -q`.

## Decisions already made

- **One front desk: `/frontdesk`.** It's the simple inbox (who needs a reply → reply → Approve & send),
  with Settings at `/frontdesk/settings`. The React app is retired: `/desk` and `/app` redirect to
  `/frontdesk`, and Render no longer builds `frontend/`. Delete `frontend/` and `static/dist/` in a cleanup PR
  once you agree.
- **Email goes through the clinic's own mailbox.** Raleigh's email is hosted by **Einstein Mail**
  (`mx.einsteinmail.com`), not Google. Settings → Email has an Einstein Mail preset
  (`smtp.einsteinmail.com:587` STARTTLS and `imap.einsteinmail.com:993` SSL, per Einstein support; username = full address).
- **Deploy on Render, paid plan with a disk.** The free plan wipes the SQLite database on every
  deploy and sleeps, which also stops the follow-up scheduler. `render.yaml` is already set up.
- **No demo data in production.** Demo logins, the demo clinic and the developer portal at `/` only exist
  when `APP_ENV` is not `production`.

**Still needed:** `main`'s history contains a real Gmail address and app password (from the old
`ensure_demo_data`). Revoke that app password in that Google account if it hasn't been done yet.

## 1. Deploy — done on Railway (project `heyjarvis-concierge`, service `concierge`)

Deployed from this branch with `railway up` (no GitHub link needed). `railway.toml` builds the `Dockerfile`:
1 replica, a volume at `/data`, `DATABASE_URL=/data/saas.db`, `APP_ENV=production`, current Gemini models,
and generated `JWT_SECRET`/`ENCRYPTION_KEY`. **Never change `ENCRYPTION_KEY` after launch:** clinic mailbox
passwords are encrypted with it. To redeploy after changes: `railway up -s concierge`.
(`render.yaml` still works if we ever move to Render.)

Still to set in Railway → concierge → Variables (secrets, never commit them):

| Variable | Value |
|---|---|
| `GEMINI_API_KEY` | from https://aistudio.google.com/apikey |
| `DEFAULT_SMTP_USER` / `DEFAULT_SMTP_PASSWORD` | a heyjarvis.ai Google Workspace address + its app password (myaccount.google.com/apppasswords). **Required:** staff login codes and teammate invites come from it. Host/port are already `smtp.gmail.com:465`. |
| `DEFAULT_SMTP_FROM` | optional, e.g. `HeyJarvis <avi@heyjarvis.ai>` (defaults to the user) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | optional; only for clinics on Google Workspace (see the end of this doc) |

### Production variables

- **Never set `CONCIERGE_DEMO`** in production: it brings back the demo clinic and its well-known logins.
- **Never set `GROQ_API_KEY`** (or `CONCIERGE_ALLOW_GROQ`) in production: patient messages go to Gemini only.
  Groq is used only when both are set.
- **`APP_ENV=production` is baked into the Docker image**, so a deleted Railway variable can't drop the server
  into development mode. Production also refuses to boot without strong `JWT_SECRET`/`ENCRYPTION_KEY`, and
  doesn't serve `/admin`, `/install`, the API docs or the old React bundle.
- uvicorn runs with `--no-access-log` (search URLs carry patient names/emails/phones). Errors are still logged.

Domain: Railway → concierge → Settings → Networking → Custom Domain `concierge.heyjarvis.ai` (port 8080),
then add the CNAME (and TXT, if shown) in **GoDaddy** DNS, where heyjarvis.ai's DNS lives.
Check: `https://concierge.heyjarvis.ai/health` returns `"ok": true`, and `/` redirects to `/frontdesk`.
`scheduler_last_tick_age_s` is the seconds since the mailbox/follow-up scheduler last finished cleanly (it runs
every 2 minutes; `null` until the first run). If it keeps growing, check the logs.

`railway.toml` is deprecated by Railway after 2026-12-01; the root `Dockerfile` is still picked up without it.

## 2. Create the clinic (≈2 min)

`railway ssh -s concierge`, then:

```bash
python -m saas.cli onboard --slug raleigh-dentistry \
  --name "Raleigh Comprehensive and Cosmetic Dentistry" \
  --owner-email <owner email> --domain raleighdentistry.com \
  --phone "(919) 828-3775" --address "119 North Boylan Avenue, Raleigh, NC 27603" \
  --hours "Mon-Thu 8am-5pm, every other Friday 8am-5pm"
```

It prints the front desk link and the website snippet. Sign-in uses emailed codes, so there's no password to hand out.

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
