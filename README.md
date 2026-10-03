# HeyJarvis Concierge: Raleigh Dental (Plugin 1)

Patient requests come in from the clinic website. AI reads each one live, the clinic's booking rules pick the
appointment type and length, and the front desk works entirely in **one dashboard**: pick a suggested time
(or type one), click **Send**. The reply goes to the patient by SMTP. Confirmations go out 48 hours before
each visit.

```
website widget / webhook ─▶ stored ─▶ AI triage (streamed reasoning) ─▶ booking rules ─▶ column-aware slots ─▶ Front Desk dashboard ─▶ SMTP
                                     Gemini 3.8 Flash → Flash-Lite → Groq → keywords                        (pick time, Send)
```

## Pages

| URL | What it is |
|---|---|
| `/` | Patient site demo: the same widget the clinic pastes into its website |
| `/desk` | **Front Desk**: request queue, the AI's reasoning live, suggested times, reply editor, Send, today's chair schedule (Dr 1, Dr 2, Hygiene), 48h confirmations |
| `/ops` | **Operations**: volume, which model handled each request, fallbacks and failures, time to draft, desk funnel, recent runs |

The dashboards show patient data, so they only answer on localhost until real login is added.

## How the "AI thinking" works

None of it is a fake animation. Each model call **streams**:
- Gemini returns reasoning summaries (`include_thoughts`). Gemini 3.8 Flash produces them; Flash-Lite answers without one.
- Groq's `gpt-oss-120b` streams its reasoning tokens.

Every real step is saved as an event: model attempt, failure and handoff, reasoning text, classification, booking rule, slot search. The Front Desk replays these events live with a shimmering "Gemini is thinking…" label, typed-out reasoning, and ✕/✓ handoffs between models.

## Booking rules (from the one-pager)

| Rule | Where |
|---|---|
| New patient 90 min = 60 hygiene + 30 doctor; no hygiene slot → full 90 with the doctor on column 2 | `schedule.py` slot finder |
| Emergency 60 min in a doctor column, same day when there's room (otherwise next openings, flagged) | `schedule.py` |
| 2 doctor columns, 1 hygiene column, lunch blocked, no double-booking (re-checked at send time) | `config/concierge.toml` + `schedule.py` |
| Confirmation 48h ahead | Front Desk "Confirmations due", or automatic with `CONCIERGE_AUTO_CONFIRM=1` |
| $65 broken/no-show fee, financing through Cherry + CareCredit (only when the patient asks) | reply + confirmation text |

The patient's stated preference ("weekday mornings", "Tue afternoons", "next week") filters the suggested times. The desk can override it with **Ignore preference**.

## Run it

```bash
uv venv && uv pip install -e ".[dev]"
cp .env.example .env               # add keys
pytest                             # 48 tests, no network
.venv/Scripts/python -m uvicorn concierge.api:app --port 8000
```

Then open http://localhost:8000/desk and click **Simulate patient request**.

SMTP: `CONCIERGE_SMTP_DRYRUN=1` saves every email to `outbox/sent/` instead of sending it. Set it to `0` once `SMTP_USER` / `SMTP_PASSWORD` work (Gmail needs an app password). The status chip in both dashboards shows live / dry-run / login failed.

## On the clinic website (any builder)

```html
<div id="concierge-form"></div>
<script src="https://YOUR-CONCIERGE-HOST/widget.js" defer></script>
```

This works in WordPress, Wix, Squarespace, Webflow and plain HTML. Add the site to `CONCIERGE_ALLOWED_ORIGINS`.
- The patient gets an instant "thanks" while the AI works in the background.
- The browser holds no secret.
- Each IP is limited to 5 requests per minute, and bot submissions are dropped by a hidden honeypot field.

## Before go-live (needs Avi, who owns all client communication)

- [ ] The clinic agrees the desk works in this dashboard. The one-pager said "no new software"; this version replaces the email-draft flow with the dashboard.
- [ ] Real office hours, lunch and time zone (`[hours]` in config), plus the length for returning-patient visits (60 min assumed)
- [ ] Real clinic phone and sending address; a working SMTP login (the Gmail app password currently fails)
- [ ] Clinic sign-off on patient-facing wording, especially the emergency safety line and confirmation email
- [ ] Login for `/desk` and `/ops` before hosting anywhere but localhost; HTTPS
- [ ] HIPAA: BAAs with Google (Vertex AI, not free AI Studio) and Groq, or run `CONCIERGE_USE_LLM=0`. `data/concierge.db` holds patient data: encrypted disk, backups, no git
- [ ] Rotate the Gmail app password and Groq key that were shared in chat
- [ ] Not covered: phone calls and texts (only web form / webhook intake)
