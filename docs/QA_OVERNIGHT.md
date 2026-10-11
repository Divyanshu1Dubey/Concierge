# Overnight engineering run: QA, fixes and phases 9-14

Branch `ScalableMade` at `05e1a32`, local working tree only. Nothing was committed, pushed or deployed, and no
real patient was contacted. Every browser run used an isolated copy of the database with email and SMS
recorded locally (console backends).

## 1. Test execution report (actual results)

| Check | Command | Before (re-verified at start) | After |
|---|---|---|---|
| Backend tests | `cd backend && python -m coverage run --source=apps -m pytest -q` | 217 passed | **424 passed, 0 failed, 0 skipped** |
| Backend line coverage | `python -m coverage report` | 76% | **81%** (growth module 81%, follow-ups 91%, integrations 89%) |
| Frontend unit tests | `cd frontend && npx vitest run` | none existed | **7 passed** |
| TypeScript | `npx tsc --noEmit -p .` | pass | pass |
| Production build | `npm run build` (mirrored to `backend/dist`) | pass | pass |
| Migrations | `manage.py makemigrations --check` | none pending | none pending (2 new choice-only migrations applied locally after a verified backup) |
| Deploy checklist | `manage.py check --deploy --settings=config.settings.production` (throwaway key) | only `SECURE_HSTS_PRELOAD` advisory | unchanged |
| Python CVEs (production requirements) | `pip-audit -r requirements.txt` and `-r backend/requirements.txt` | — | **no known vulnerabilities** |
| npm advisories | `npm audit --omit=dev` | — | 2 moderate (react-router); not reachable, see section 4 |
| Browser suites (8) | managed QA server + `run_browser_suites.sh` | 7 suites; **3 failures found** on the true baseline | **166 / 166 checks passed in one run** (re-run after the accessibility changes) |
| Accessibility (axe-core 4.9, WCAG 2 A/AA, serious + critical) | `a11y_audit.py` on login + 9 dashboard pages | 14 rule violations (hundreds of elements) | **0** |

Browser suites: smoke 33, accounts 9, production 19, ui_check 13, widget 17, branding 17, phase-9 41,
overnight 17 (new: priority ordering, patient-replied follow-up, install check, SSRF refusal, System Status,
restore drill in the browser, mobile layouts, no 5xx or page errors).

## 2. Defects found and fixed

| # | Defect | Severity | Fix | Regression test |
|---|---|---|---|---|
| 1 | Website check vulnerable to **DNS rebinding** (resolve, then connect separately) | High | Resolve once, require every address to be public, connect to that pinned IP with TLS hostname verification; ignore environment proxies; bounded total time | `test_overnight_security.py` (pinning, TOCTOU, mixed answers, 16 private ranges, redirects, proxies); live-verified against example.com |
| 2 | `SMS_BACKEND=console` could still **send live texts** if Twilio credentials were present | High | Test mode always wins; webhook signatures use a dedicated signing-token helper | `SmsSafetyTests` |
| 3 | Duplicate or replayed Twilio webhooks were **processed twice** | Medium | Dedupe by `MessageSid` | `test_duplicate_or_replayed_webhook_processed_once` |
| 4 | AI replies could state **unapproved prices, insurers or "you're booked"**; correct refusals mentioning "diagnosis" were wrongly withheld | High | Grounded reply check against the practice's approved facts; obvious injection gets a fixed reply without calling the model | `test_overnight_ai.py` (31 tests) |
| 5 | **Patient replies never reached the follow-up queue** (reply reopened the request but no task) | Medium | New "patient replied" follow-up (email or text), auto-closes when answered | `InboundTests`, browser suite |
| 6 | HTML-only email replies stored **empty**; unknown charsets **crashed** the parser; replies from a different address not flagged | Medium | HTML-to-text fallback, safe decoding, staff note for mismatched sender | `InboundTests` |
| 7 | Responsive grids without a base column **overflowed on phones** (Growth page 172 px; 30 grids at risk) | Medium | `grid-cols-1` base everywhere, `min-w-0` on cards | 390 px checks in browser suites |
| 8 | New overdue requests appeared in Follow-ups **up to a minute late** | Low | 10 s throttle plus invalidation on request, offer, inbound email or text changes | `QueueFreshnessTests` |
| 9 | Follow-up scan did **one query per request** (600-1,200 queries per practice) | Medium | Known-key cache and batched lookups: steady-state 38 ms / 22 queries per practice at 400 requests | scale test (below) |
| 10 | 32-bit confirmation codes had **no collision retry** (rare 500 at scale) | Low | Retry on collision | `ConfirmationCodeTests` |
| 11 | Two backups in the same second **overwrote each other**; backups never restore-tested | Medium | Unique names; `restore_drill`; daily job verifies each backup | `BackupTests`; real drill on the newest live backup passed |
| 12 | Branding browser suite depended on data left by another suite | Test | Suite creates its own request | suite passes standalone and in sequence |
| 13 | Recall task used email even after an email opt-out when a phone existed | Low (Phase 9) | Channel follows opt-outs | `test_email_opt_out_falls_back_to_text_channel` |
| 14 | **Accessibility**: body and helper text below WCAG AA contrast across every page (warm grays at 2.4-4.4:1); unlabeled status filter and key fields; scrollable code blocks not keyboard-reachable | Medium | Darkened `stone-400`/`stone-500` palette tokens (5.1:1+ for body text), small text moved off `gray-400`, `aria-label`s, `tabIndex` on scroll regions | axe audit: 0 serious/critical; all browser suites green |

## 3. Scale test (isolated SQLite, 20 practices x 400 requests, emails, offers, texts)

| Operation | Before | After |
|---|---|---|
| Follow-up scan, repeat (steady state) | 321 ms, 615 queries | **38 ms, 22 queries** |
| Follow-up scan, first run (creates 191 tasks) | 452 ms, 1,189 queries | 422 ms, 935 queries (dominated by inserts, once) |
| Analytics overview 30 / 90 days | 36 / 52 ms | unchanged |
| Briefing build | 17 ms | unchanged |

## 4. Security and reliability findings (open)

| Finding | Status | Action |
|---|---|---|
| Previously published demo logins still active locally | Open (needs your deploy) | `lock_demo_accounts --confirm --deactivate` after deploy; System Status flags it |
| Without Redis the cache is per gunicorn worker: login rate limits are ~3x looser, short locks not global | Mitigation added, opt-in | Set `CACHE_BACKEND=database` (verified cross-process); System Status warns |
| Widget accepts `file://`, `Origin: null` and localhost for any practice key | Kept for the local demo page; now configurable | Set `WIDGET_ALLOW_LOCAL_ORIGINS=false` once demo pages are hosted |
| react-router advisories (open redirect via backslash; SSR deserialisation) | Not reachable: every navigation target is a fixed internal path or server-supplied internal path; no SSR | Upgrade to v7 is breaking; schedule separately |
| `markdown` 3.5.2 / `python-dotenv` 1.0.1 CVEs | Local venv / dev-only, not in deployed requirements | Dev pin bumped to `python-dotenv==1.2.2` |
| Integration secrets encrypted with a key derived from `SECRET_KEY` | By design | Rotating `SECRET_KEY` requires reconnecting integrations (documented) |
| `SECURE_HSTS_PRELOAD` not set | Advisory | Optional |
| A git worktree `.claude/worktrees/audit` (branch `audit/production-hardening`, Oct 10) exists | Pre-existing, untouched | Your decision |

No secrets were found in the frontend bundles or logs (scan of built JS for key/token patterns: only UI labels matched).

## 5. Feature-to-test traceability (summary)

| Area | Acceptance criteria | Tests | Result | Gaps |
|---|---|---|---|---|
| Tenant isolation & roles | Every growth object endpoint 404s across practices; anonymous 401; front desk 403 on admin actions | `IsolationMatrixTests` (7 object endpoints, 12 staff, 11 admin-only) | pass | — |
| Auth tokens | Expired, tampered, refresh-as-access, rotated refresh, deactivated user all rejected | `TokenEdgeTests` + existing auth suites | pass | — |
| AI concierge | Only approved facts; no prices, insurers or bookings unless approved; injection, provider failure and empty-output handling | `test_overnight_ai.py` | pass | live model behaviour not measured (fake provider) |
| Attribution | 19 channel cases, encoding, bounds, malformed input, Android app referrers | `test_overnight_flows.py`, phase-9 | pass | — |
| Follow-ups | Creation, dedupe, thresholds, alerts (once, retried on mail failure), priority order, patient replies, snooze, batch policy, isolation | phase-9, reliability, flows, phases | pass | — |
| Confirmation links | Transitions, replay, supersede, expiry, DST midnight | existing confirmation suite + DST test | pass | — |
| Email inbound | Threading, duplicate, unmatched, forged domain, HTML-only, bad charset, sender mismatch | flows + onboarding suites | pass | real IMAP mailbox not exercised |
| Analytics & briefing | Window edges, spam excluded, `None` instead of fake zeros, value estimate only with practice figure, once-per-week send | flows + phase-9 | pass | — |
| Website check | SSRF/DNS rebinding, limits, findings, facts export escaping, install check | security + phase-9 + phases | pass | PageSpeed live call not exercised (no key) |
| Recall & outreach | CSV (aliases, BOM, Latin-1, garbage, size, row cap), opt-outs, acknowledgement gate, fair review requests | phase-9 + auth | pass | — |
| SMS | Test-mode safety, payload, error codes, timeouts, signatures, STOP/START, duplicates, status callbacks | security + integrations + phase-9 | pass | not sent through real Twilio |
| Google Business Profile | OAuth state, token refresh/revocation, 403/429, pagination, reply/post validation, review tasks, disconnect | integrations + phases | pass (mocked) | **not verified against Google** (needs API approval) |
| NexHealth | Auth, token cache, slots normalisation, errors, openings on the request page | integrations + phases | pass (mocked) | **not verified against NexHealth** (needs key + BAA) |
| Scheduler & backups | Each job, window lock, failure isolation, crash recovery, cron secret rotation, backup retention, restore drill | reliability + security | pass; real restore drill passed on live backup | — |
| UI journeys | Pages load, actions persist, permissions, mobile, no 5xx or page errors | 8 browser suites | 166/166 | — |
| Accessibility | No serious/critical WCAG 2 A/AA violations | axe-core audit (10 pages) | 0 violations | manual screen-reader pass not done |

## 6. Phases implemented tonight

| Phase | Delivered | Acceptance evidence |
|---|---|---|
| 9 Reliability | DNS-rebinding-safe fetching; backup verification + `restore_drill`; **System Status** page (readiness checks with fixes, job history, run jobs, restore drill); shared-cache option; SMS test-mode guarantee; webhook dedupe | security/reliability tests; live drill passed |
| 10 Integrations | Google review replies as follow-ups (publish on Send); NexHealth openings on the request page; quiet "not connected" states | phases tests (mocked) |
| 11 Conversion | Explainable priority ranking with "Contact first"; patient-replied follow-ups; queue freshness | phases/flows tests, browser suite |
| 12 Intelligence | Grounded AI reply checks (no unapproved claims); briefing recommendations already evidence-based | AI tests |
| 13 Website tools | Installation verification (script, key, server, domain) | phases tests, browser suite |
| 14 Scale | Synthetic 8,000-request test; follow-up scan made ~15x cheaper in steady state | scale test |

## 7. Integration readiness

| Integration | Code | Tested with | Real external verification | Blocker |
|---|---|---|---|---|
| Email (SMTP/Resend) | done | locmem/console | earlier phases (SMTP) | Railway Hobby blocks SMTP; use Resend |
| IMAP replies | done | parser tests | no | IMAP credentials |
| Twilio SMS | done | mocks | **no** | account, number, A2P 10DLC (paid) |
| Google Business Profile | done | mocks | **no** | Google API approval + OAuth client |
| NexHealth | read-only slots | mocks | **no** | API key, BAA (paid) |
| PageSpeed | done | mocks | no | free API key |
| Scheduler | done | local + browser | n/a | `CRON_SECRET` + Railway cron service |

## 8. Continuation handoff

1. **Approve and deploy** (see the deployment plan in the chat report), then run `lock_demo_accounts` and set
   `CRON_SECRET`, `CACHE_BACKEND=database`, email (Resend).
2. Point a cron service at `/api/v1/growth/cron/run/`, then confirm System Status shows no blockers.
3. Apply for Google Business Profile API access; get a NexHealth sandbox key to verify the adapters for real.
4. Schedule the react-router v7 upgrade as its own change with the full browser suite.
5. Next engineering candidates: run the axe audit inside CI with the browser suites; a manual screen-reader pass;
   bulk task creation for very large first scans; an "assign to me" control on follow-ups.

Reproduce locally: `tmp/overnight/qa_server.py start|stop` (isolated DB, console email/SMS), `prep_qa_db.py`,
`run_browser_suites.sh`, `scale_test.py` (job temp folder).
