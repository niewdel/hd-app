# Welcome to the HD Platform

## Login

- **URL:** https://web-production-e19b3.up.railway.app
- **Username:** kharrison@hdgrading.com
- **Temporary password:** E4BxWGR0Vn5tQMle

First step once you're in: open Settings → My Profile → change your password to something only you know.

## What This App Is

HD Hauling & Grading's internal operations platform. Everything we use to run the business — proposals, CRM, project pipeline, scheduling, work orders, job costing, exports, reporting, admin. Built in-house. Every panel you see is live production data.

## What I Want From You

Walk every panel. Build a test proposal. Move it through the pipeline (New Lead → Estimate Sent → Approved → Scheduled). Export a PDF. Add a test client. Log a test work order. Then go through the panels you'd actually use day-to-day and tell me what's confusing, what's missing, what you'd change.

The surfaces where your input matters most:
- **Dashboard** — does the top-of-screen view feel like the right summary?
- **Build Proposal** — does the flow from blank → sent proposal make sense?
- **Pipeline** — does it show what you need to see to run the business?
- **Reports & Analytics** — anything missing for the decisions you actually make?

## What's Intentionally Polish-Pending

We did a full hardening sweep the night before handoff. A few things were explicitly deferred so you don't flag them as bugs:

- **Full visual redesign** — direction is locked in (Field Ops Premium tone with Command Center density and Executive Industrial polish on exports), but the rollout is multi-week. What you see today is the current system, not the redesign.
- **Mobile UX** — the app works on mobile but hasn't had a dedicated mobile pass. Tables and dense views will feel cramped on a phone. iPad is fine.
- **ICS calendar feed tokens** — per-user rotation is deferred. Single shared token still powers the schedule export feed.
- **File-upload magic-byte validation** — deferred (no execution risk; static-asset serving only).
- **Weather widget videos** — first-load takes a moment to fetch the video; subsequent loads are instant from browser cache.

## How to Report a Bug or an Idea

In-app **Bug Reports** panel. "Submit a Bug" form, type a short description, set severity, attach a screenshot if relevant, submit. That goes into the queue I review.

This is faster than texting because I can triage and code-fix from one place.

## When to Text Me Directly

For:
- You can't log in at all.
- You see a stack trace or a 500 error page.
- You think data you saved is gone.
- Something you expected to be there isn't.

For everything else, the Bug Reports panel beats a text thread.

— Justin

## Smoke Test (Justin runs after deploy)

Walk these as `dev` (Justin):
- Dashboard loads, weather video plays, no console errors.
- Projects → Pipeline → Bid Calendar — all three views render.
- Build Proposal → save a test proposal → edit → delete.
- Contacts → create / edit / delete a test client.
- Schedule → create a work order → clock in → clock out → delete.
- Reports → open each category.
- Settings → Material Prices → click "Restore Defaults" → cancel the confirm.
- Admin → Company / Users / Activity / Archived all visible.
- Standalone Roadmap → visible in nav.
- Bugs → both Submit form and All Reports card visible.

Walk these as `admin` (Kyle's account):
- Admin → ONLY Company tab visible (no Users/Activity/Archived).
- No Roadmap nav entry.
- Bugs → Submit form visible, All Reports NOT visible.
- Console clean.

Failure test:
- As admin, edit a client → toggle DevTools Network "Offline" → click Save → expect red toast, modal stays open.
- Toggle Online → Save → success toast, modal closes.
