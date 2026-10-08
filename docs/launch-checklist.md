# Launching a clinic

The current, step-by-step launch guide (Render deploy, clinic onboarding, mailbox connection,
team invites, go-live checklist) is in [HANDOFF.md](../HANDOFF.md).

Per-clinic summary:

1. `PYTHONPATH=src python -m saas.cli onboard --slug <clinic-id> --name "<Clinic name>" --owner-email <email> --domain <website-domain> --phone "<phone>" --hours "<hours>"`
2. The owner signs in at `/frontdesk?clinic=<clinic-id>` with an emailed code.
3. Settings → Clinic details, Email (Einstein Mail / Google / Microsoft 365 / other IMAP+SMTP), Team, Follow-ups.
4. The website snippet printed by `onboard` goes before `</body>` on every page.
