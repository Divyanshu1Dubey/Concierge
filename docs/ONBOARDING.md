# Onboarding a dental practice (agency runbook)

Time needed: about 20 minutes per practice, plus the practice's website change.

## 1. Before you start
- The server is running with working email (Settings → *Email Delivery* → **Send test email** succeeds).
- You have the practice's name, main email, phone, address, website and the doctor's (practice admin's) email.

## 2. Create the practice (agency admin)
1. Sign in as the agency admin → **Dental Practices** → **Onboard practice**.
2. Fill in practice details and the administrator's name and email.
3. Leave **Initial password** blank: the doctor receives an invite email with a link to set their own password.
   *If the invite email cannot be sent, a one-time password is shown once on screen. Share it securely.*

## 3. The doctor sets up the practice (practice admin)
After setting a password from the invite link, the doctor signs in and completes:

| Page | What to set |
|---|---|
| Practice Settings | Name, phone, email, address, website, timezone; which request types email the team |
| Hours & Services | Weekly office hours, emergency phone, emergency / after-hours / handoff messages, assistant guidance (facts the concierge may share) |
| Email & SMTP Delivery | Sender name, reply-to, routing emails (general / emergency / appointment / handoff). Click **Send test email** and confirm it arrives |
| Widget Customizer | Title, greeting, colour, position |
| Email Templates | Reply templates for each request type |
| Dentists & Staff | Invite front-desk staff (blank password → invite email) |

The assistant only answers from what is entered in **Hours & Services** and **Practice Settings**; it will not quote prices, insurance coverage or availability.

## 4. Install on the practice website
1. **Plugin & Embed Code** → copy the script tag, or download the WordPress plugin.
2. Add the website's domain under **Allowed domains** (requests from other sites are refused).
3. Paste the script before `</body>` (or install/activate the WordPress plugin).

## 5. Verify end to end (do this with the practice)
1. Open the practice website → the chat bubble appears.
2. Send a test request (e.g. "I need a cleaning", give a name, email, preferred day/time, confirm).
3. In the dashboard → **Appointment Requests**, the request appears for that practice only.
4. The team's routing email receives the "New request" alert.
5. Open the request → **Draft Reply** → send to your own test address → confirm it arrives.
6. Delete the test request (**Delete** on the request page) so it does not count as a real patient.

## 6. Staff training (10 minutes)
- Requests inbox: tabs, statuses, priority, internal notes, **Propose Visit Time**.
- Replying: drafts, templates, AI refine buttons; replies go from the practice email.
- A request is *not* a booked appointment until your team confirms it with the patient.
- Forgot password: use **Forgot password?** on the sign-in page.

## 7. Support & offboarding
- Locked out: practice admin or agency admin uses **Send reset link** (Team / Practices page).
- Suspend a practice: Dental Practices → toggle status. Staff are signed out and the widget stops.
- Patient asks for their data to be deleted: open the request → **Delete** (optionally with the conversation). Recorded in the audit log without patient details.
