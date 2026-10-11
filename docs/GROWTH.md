# Growth & conversion platform: setup and operations

Everything here is optional and switches on as configuration is added. The **Integrations** page
(`/dashboard/integrations`) always shows the true state of each piece: *Working*, *Test mode*,
*Needs setup*, *Awaiting Google approval* or *Not connected*.

## What is included

| Area | Where | Works without extra setup? |
|---|---|---|
| Inquiry source tracking (channel, landing page, referrer, UTM tags) | Request page, Growth | Yes (widget sends it automatically) |
| Follow-up queue with drafted replies (waiting requests, patients who replied, unconfirmed visit times, reschedule requests, Google reviews), ranked by priority | Follow-ups | Yes; refreshes when staff open it |
| Front-desk alert emails for overdue requests | Email | Needs the scheduler + working email |
| Confirmation reminders (re-issues the confirm link) | Follow-ups | Yes (staff send) |
| Weekly practice briefing email | Growth | Needs the scheduler + working email ("Send it now" works anytime) |
| Funnel, source and weekly trend analytics | Growth | Yes |
| Suggested answers for unanswered patient questions | Practice Knowledge | Needs AI configured |
| Website check (facts consistency, booking, search basics, structured data) | Website Check | Yes; Lighthouse scores need `PAGESPEED_API_KEY` |
| Website facts export (Dentist + FAQ structured data, FAQ HTML) | Website Check | Yes |
| Installation verification (script present, practice key, server, allowed domain) | Plug-in & Embed Code | Yes |
| Real openings from the practice system when proposing a visit time | Request page | Needs NexHealth |
| Recall list (CSV import, auto-add on completed visits), recall / reactivation / review-request drafts | Recall List, Growth | Off by default; admin must enable and accept the outreach notice |
| Opt-outs (email unsubscribe link, SMS STOP/START, staff-recorded) | Recall List | Yes |
| Text messages | Request page, Follow-ups | Needs Twilio (or `SMS_BACKEND=console` for testing) |
| Google Business Profile (reviews, reply drafts, publish replies, profile posts) | Integrations | Needs Google API approval + OAuth client |
| NexHealth practice-management availability | Integrations | Needs NexHealth API key + BAA |

**Safety rules built in:** no patient message is ever sent without a staff member pressing Send (or
"Send all drafts" when a practice admin explicitly enables batch approval). Outreach respects opt-outs,
adds an unsubscribe link (email) or STOP notice (text), and review requests go to every completed visit
the same way (no screening of happy patients, which Google's policy forbids).

## Operations: system status, backups and restore drills

- **System Status** (`/dashboard/system`, agency admins): live production-readiness checks (secret key, debug,
  public URL, demo logins, email, reply collection, SMS mode, scheduler secret and health, job failures, newest
  verified backup, free disk, shared cache, widget origin policy, integrations) plus per-practice setup gaps.
  Each problem shows its fix. No secret value is ever displayed.
- **Restore drill**: `python manage.py restore_drill` (or the button on System Status) copies the newest backup to
  a temporary file, checks integrity and core tables, migrates the copy to the current schema and runs Django's
  checks. The live database is never touched. The daily backup job verifies every backup it writes.
- **Shared cache**: without Redis each gunicorn worker has its own cache, so login rate limits and short locks are
  per worker. Set `CACHE_BACKEND=database` to share them through the SQLite file (`start.sh` runs
  `createcachetable`).
- **Widget origins**: requests from `file://` pages, sandboxed iframes (`Origin: null`) and `localhost` skip each
  practice's allowed domains unless `WIDGET_ALLOW_LOCAL_ORIGINS=false`. Keep it on while demo pages are opened
  from disk; turn it off once they are hosted.

## Scheduler (needed for alerts, briefings and overnight reply collection)

Jobs (each runs at most once per window; repeated calls are skipped): reply collection (10 min),
follow-up scan and alerts (15 min), outreach drafts (hourly), Google review replies (hourly, connected practices),
briefings (hourly check, sent once per week), monthly website re-checks (daily, max 5), verified SQLite backup
(daily), job-log cleanup (daily).

1. Set `CRON_SECRET` on the web service (a long random value).
2. Add a Railway **Cron** service (schedule `*/10 * * * *`) whose command is:
   ```sh
   curl -fsS -X POST -H "X-Cron-Secret: $CRON_SECRET" https://<your-app>/api/v1/growth/cron/run/
   ```
   The web service owns the SQLite volume, so jobs run there; the cron container only makes the call.
3. Check `/dashboard/integrations` → *Scheduled jobs* shows a recent run. Agency admins can see job
   history at `GET /api/v1/growth/cron/status/`.

Locally: `python manage.py run_scheduled_jobs [--job followups] [--force]`.

## Email

Railway Hobby blocks outbound SMTP. Use the existing Resend backend (`RESEND_API_KEY`, verified domain)
or Railway Pro before relying on alerts and briefings.

## Text messages (Twilio)

1. Create a Twilio account and number; complete **A2P 10DLC** brand and campaign registration (US).
2. Either set `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` platform-wide, or let each
   practice connect its own account on the Integrations page (credentials are verified, then stored encrypted).
3. Point the number's incoming-message webhook to `https://<your-app>/api/v1/growth/sms/inbound/`.
   Requests are validated with Twilio's signature; STOP/START replies update opt-outs automatically.
Costs are per message (Twilio pricing) plus registration fees.

## Google Business Profile

1. In Google Cloud, create a project and request **Business Profile API access** (Google's form; review
   takes about 14 days; you need an owner/manager email on a live profile).
2. After approval, enable the Business Profile APIs, create an OAuth web client with redirect URI
   `https://<your-app>/api/v1/growth/integrations/google/callback/`, and set
   `GOOGLE_BUSINESS_CLIENT_ID` / `GOOGLE_BUSINESS_CLIENT_SECRET`. The consent screen may need verification
   for the `business.manage` scope.
3. A practice admin presses **Connect Google Business Profile**, chooses the location, and can then read
   reviews, draft and publish replies, and post updates. Nothing is published without a person pressing Publish.

## NexHealth (practice-management sync)

Requires a NexHealth Synchronizer API key (usage-based pricing), the practice subdomain and location ID, and
a signed BAA before real patient data flows. Enter them on the Integrations page and press **Test connection**
(lists providers). Availability can then be read via `GET /api/v1/growth/integrations/nexhealth/slots/`.
Booking into the practice system is intentionally not automated yet.

## Website check

Fetches only public http(s) sites on ports 80/443. The hostname is resolved once, every address must be public,
and the connection is pinned to that address (TLS still verifies the real hostname; environment proxies are
ignored), so DNS rebinding cannot redirect it. Every redirect repeats the checks. Pages are capped at 2.5 MB and 10 s. Add `PAGESPEED_API_KEY` (free) for
Lighthouse scores, which load in the background.

## Data and privacy notes

- Staff alerts and briefings use patient first names only.
- Integration secrets are encrypted (AES-256-GCM, key derived from `SECRET_KEY`) and never returned by the API. Changing `SECRET_KEY` makes stored integration credentials unreadable; reconnect integrations afterwards.
- Outreach programs require a practice admin to accept a notice that the practice is responsible for
  patient-communication and privacy obligations. HeyJarvis does not claim HIPAA compliance; vendors that
  handle patient data (email, SMS, NexHealth) need BAAs where applicable.
