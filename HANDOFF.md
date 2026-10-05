# Handoff: get Concierge live for Raleigh Dentistry

For: Divyanshu · From: Avi · Branch: `production-readiness`

## What changed (summary)

- **Security:** every admin route is now scoped to the user's clinic. The public widget key
  no longer opens the front desk. Passwords are required, the app refuses placeholder secrets
  in production, logins and public lead endpoints are rate-limited, patient text is escaped
  in the dashboard (XSS fix), and staff log in with emailed one-time codes.
- **Email:** approved drafts are sent from the **clinic's own Gmail** (Google sign-in or app
  password). Patient replies and desk-sent mail are read back over read-only IMAP.
- **Follow-up:** one editable cadence per clinic, with reply rules. A background scheduler
  drafts due follow-ups, and a person approves each one before it sends.
- **Chat:** Gemini pulls out the patient's details, with rules as a fallback. The widget is now
  clickable on host sites, and `/widget.js` is served at the root.
- **Bug fixes:** missing argon2 dependency, a database deadlock, and broken front desk
  endpoints and dashboard loading.
- **Tests:** 271 pass (`uv run pytest`).

## 1. Get the branch into GitHub (≈5 min)

Avi's GitHub account (`avisanghavi`) can't push to this repo. Either:

- **A.** Add `avisanghavi` as a collaborator (repo → Settings → Collaborators) and Avi pushes; **or**
- **B.** Apply the bundle Avi sends you (`concierge-production-readiness.bundle`):
  ```bash
  cd Concierge && git fetch /path/to/concierge-production-readiness.bundle production-readiness:production-readiness
  git push -u origin production-readiness
  ```

Then open a PR from `production-readiness` into `main`, review it, and merge.

## 2. Deploy on Railway (not Vercel) (≈20 min)

heyjarvis.ai stays on Vercel. This service has to be always-on: it checks Gmail every
2 minutes and keeps a database file.

1. Railway → New Project → Deploy from GitHub → this repo, branch `main`.
2. Add a **Volume** mounted at `/data`.
3. Variables:

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `APP_URL` | `https://concierge.heyjarvis.ai` |
| `DATABASE_URL` | `/data/saas.db` |
| `JWT_SECRET` | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEY` | same command, a different value. **Never change it after launch** (mailbox credentials are encrypted with it) |
| `GEMINI_API_KEY` | Avi adds it for testing |
| `DEFAULT_SMTP_HOST` / `PORT` / `USER` / `PASSWORD` / `FROM` | a HeyJarvis sending mailbox (e.g. Google Workspace `noreply@heyjarvis.ai` + app password, host `smtp.gmail.com`, port `465`). **Required:** staff login codes are sent from it |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | optional, see step 4 |

4. Keep **1 replica** (the scheduler runs inside the web process).
5. Settings → Networking → custom domain `concierge.heyjarvis.ai`, then add the CNAME
   Railway shows in heyjarvis.ai's DNS (Vercel → Domains, or wherever DNS lives).
6. Check that `https://concierge.heyjarvis.ai/health` returns `{"ok": true}`.

## 3. Create the clinic (≈2 min)

In a Railway shell:

```bash
uv run python -m saas.cli onboard --slug raleigh-dentistry \
  --name "Raleigh Comprehensive and Cosmetic Dentistry" \
  --owner-email <Avi's email for testing> --domain raleighdentistry.com
```

It prints the front desk link and the website snippet. Send both to Avi. Logins use an
emailed code, so there's no password to hand out.

## 4. Optional: Google sign-in for the clinic mailbox

Without this, the clinic connects with a Google app password (Settings → "Use an app password instead").

1. console.cloud.google.com → new project → OAuth consent screen.
   - **Internal** (best) only works if the project is created in the clinic's own
     Google Workspace (their admin). No Google review, and tokens don't expire.
   - **External / Testing** (HeyJarvis account): add the clinic address as a test user.
     Google disconnects it **every 7 days** until the app passes Google's verification for the Gmail scope (takes weeks).
2. Credentials → OAuth client ID → Web application → redirect URI
   `https://concierge.heyjarvis.ai/oauth/google/callback`
3. Put the ID and secret in Railway, then redeploy. The "Sign in with Google" button appears automatically.

## 5. Avi's production test (Avi does this)

1. Log in at `/frontdesk?clinic=raleigh-dentistry` with an emailed code.
2. Settings → connect a test Gmail.
3. Chat as a patient on `/concierge/raleigh-dentistry`, then Run follow-ups → Send → reply →
   Sync mail. The reply should show up labelled and the cadence should react.
4. Remove the test Gemini key or Gmail afterwards if wanted.

## 6. Go-live (Avi + clinic)

- [ ] Clinic approves the cadence wording (Settings → Follow-up cadence).
- [ ] HIPAA BAA signed (Avi).
- [ ] Clinic connects their real mailbox.
- [ ] Add the clinic's real front desk email as an owner (`POST /api/admin/tenants/{id}/members` with role `owner`).
- [ ] Einstein Medical support pastes the snippet into the site's **footer includes**
      (the site is Einstein Medical, not WordPress), or it goes in through the clinic's GTM.
- [ ] Test on raleighdentistry.com: click Chat with us → submit → it appears in the front desk.

## Known gaps (not blockers)

- There's no self-serve "add staff" screen in the front desk yet (`POST /api/admin/tenants/{id}/members` works).
- SQLite on a volume is fine for one clinic. Move to Postgres before many clinics.
- Repo root has old scratch scripts (`fix_*.py`, test HTML) that are safe to delete in a cleanup PR.
