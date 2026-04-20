# Kyle Handoff Readiness — Design Spec

**Date:** 2026-04-20
**Target handoff:** 2026-04-21 (morning)
**Option selected:** C — full audit sweep
**Estimated effort:** 5–7 hours of focused work, split across 5 commits

---

## 1. Goal

Kyle Harrison (CEO) gets a production login at `https://web-production-e19b3.up.railway.app` on 2026-04-21 and spends a full day across every panel of the HD platform without hitting broken states, silent data loss, footguns, stack traces, or dev artifacts. The deferred security items H1–H8 from the 2026-04-16 site sweep are resolved or explicitly waived with rationale.

## 2. Exit Criteria

Binary checklist — all must be true before the handoff text goes to Kyle:

- All 8 tonight-blockers fixed and verified live on Railway.
- H1, H3, H4, H6, H7, H8 fixed. H2 and H5 waived with a one-line rationale committed to this spec (see §7).
- Every panel has a working empty state, no stale error states, and no dev-console artifacts.
- Every PATCH/POST/DELETE UI handler shows an error toast on non-2xx and does not close its modal on failure.
- Kyle's admin session renders every panel except Users, Roadmap, and the "All Bug Reports" management list.
- Kyle can still submit a bug/feedback via the in-app form.
- Document generators handle missing/empty inputs without 500s.
- `docs/kyle-handoff.md` runbook committed to the repo.
- Post-deploy smoke test (walk every panel as Kyle, verify no console errors, verify dev-only surfaces invisible) passes.
- CLAUDE.md and MEMORY.md updated with new role split and any new conventions.

## 3. Role Model Change (architectural)

Current system has three roles in `hd_users.role`: `admin`, `user`, `field`. Plus one out-of-band role — `dev` — used by `@require_dev` for user management / logs / archived / restore / roadmap CRUD / roadmap tab (currently under Admin).

**New split — Admin vs Dev visibility:**

| Surface | Admin (Kyle) | Dev (Justin) |
|---|---|---|
| Dashboard, Projects, Pipeline, Schedule, Contacts | ✓ | ✓ |
| Build Proposal, Change Orders, Work Orders, Saved Docs | ✓ | ✓ |
| Reports, Analytics, Settings (all tabs), Tasks | ✓ | ✓ |
| Admin → Company info | ✓ | ✓ |
| Admin → Activity Log | ✗ | ✓ |
| Admin → Archived items | ✗ | ✓ |
| **Users management (table + create/edit)** | ✗ | ✓ |
| **Roadmap panel (new standalone)** | ✗ | ✓ |
| Bug Reports → Submit a Bug form | ✓ | ✓ |
| **Bug Reports → All Reports management list** | ✗ | ✓ |

**Implementation:** Introduce a new frontend attribute `data-dev-only-hidden`. CSS rule hides it by default. `showAdminElements()` extends to strip the attribute only when `window._userRole === 'dev'`.

Backend user-mgmt routes are already `@require_dev`, so Kyle's admin API calls are already rejected. This work is purely frontend visibility + routing.

**Accounts — confirmed state:**
- `id=1, justin@hdgrading.com, role=dev, active=true` — no change.
- `id=12, kharrison@hdgrading.com, role=admin, active=true` — no change. Kyle's password is set by Justin out-of-band.

## 4. Scope In — Six Workstreams

### WS1. Blocker fixes (fast, critical)
1. **Remove dev console noise** — `console.log` at `index.html:11209`.
2. **Hide Users tab from admin** — role-check in `showAdminTab` + tab button visibility.
3. **Promote Roadmap to standalone panel** — delete the nested Admin tab, ensure the standalone `panel-roadmap` is wired through `showPanel('roadmap')` with the `data-dev-only-hidden` attribute on its nav entry.
4. **Hide "All Bug Reports" list from admin** — admin still sees the submit form; `data-dev-only-hidden` on the management card.
5. **`SECRET_KEY` startup guard** — refuse to start if env var is missing or equals the default dev key.
6. **`ZeroDivisionError` guard** in `generate_job_cost.py` margin calc.
7. **Clear stale "Work order not found" state** when a valid WO loads.
8. **Loader timeouts** — weather widget + time-entry skeleton replace with error state after 5s fetch timeout.

### WS2. Silent-failure hardening (write-path integrity)
- Introduce `_safeFetch(url, opts)` helper in `index.html` that throws on non-2xx and propagates the `error` body.
- Audit every PATCH/POST/DELETE UI handler. Enforce this contract in all of them:
  - Check `response.ok`.
  - On failure, show an error toast with the server message.
  - Do not close the modal.
  - Do not update local state.
- Known offenders (non-exhaustive — full list produced during WS2 execution):
  - `saveBugUpdate`, `deleteReminder`, `closeClientModal`, `closeSubModal`, `saveQuote` lock path, `saveClient`, `saveSub`, `saveReminder`, `deleteClient`, `deleteSub`, task PATCH/DELETE handlers, change-order delete.
- Confirm-dialog flows: if the first confirm succeeds but the fetch fails, the UI state must not desync.

### WS3. Backend hardening — H-items
For each 2026-04-16 deferred item: fix or waive with rationale.

| # | Item | Disposition | Implementation |
|---|---|---|---|
| H1 | `/send-email` unrestricted | **Fix** | Per-user rate limit (20 sends / rolling 24h). `hd_email_log` audit table (sender, to, subject, attachment_ref, sent_at). No recipient whitelist yet. |
| H2 | ICS feed token deterministic | **Waive** | Single-user context, rotation plan deferred. One-line rationale in commit body. |
| H3 | PostgREST query-param injection | **Fix** | Centralize via `_sb_eq(column, value)` helper using `urllib.parse.quote()`. Migrate all 40+ call sites. |
| H4 | Missing ownership checks | **Fix** | Add `_owns_or_admin(record_created_by, session_username, session_role)` guard. Apply to `/quotes/delete`, `/quotes/update`, `/projects/update`, `/change-orders/delete`, `/clients/delete`, `/tasks/<id>`, `/reminders/<id>`. Null-safe — admin/dev always passes. |
| H5 | File upload extension-only | **Waive** | No execution vector, low urgency, cost to add `python-magic` dependency > benefit tonight. |
| H6 | `SECRET_KEY` default fallback | **Fix (WS1)** | Startup guard — see WS1. |
| H7 | No CORS config | **Fix** | Explicit `Access-Control-Allow-Origin` header for the Railway domain in `set_security_headers`. |
| H8 | Error messages leak details | **Fix** | `_safe_error(e, context)` helper that logs internally + returns generic client message. Migrate ~30 authed-route error paths. |

**Legacy data backfill (runs once before H4 deploys):**
- One-shot SQL: `UPDATE proposals SET created_by='estimates@hdgrading.com' WHERE created_by IS NULL;` — same for `change_orders` and any other table with a null `created_by`.
- `estimates@hdgrading.com` is a string-only value. Not a real login row. Serves as the default "company" author on legacy / imported records.
- Committed as a migration: `docs/superpowers/migrations/2026-04-20-created-by-backfill.sql`.

### WS4. Per-panel polish pass
Order by Kyle-relevance:

1. **Dashboard** — empty states for today's schedule, weather error state, activity feed fallback.
2. **Projects (Pipeline/List/Map)** — filter-empty state, Kanban scroll affordance, bid-date card consistency.
3. **Build Proposal** — visible lock indicator when `_proposalLocked=true`, autocomplete overflow at narrow desktop widths, Item Library picker empty state.
4. **Project Detail** — activity log scroll affordance, empty states for linked proposals/COs/WOs.
5. **Contacts** — search empty state, client/sub row action clarity.
6. **Schedule** — calendar overflow scroll affordance, queue panel height fix.
7. **Reports** — report picker discovery, output table overflow.
8. **Settings** — **add "Restore Defaults" button to Material Prices card** (wire to `applyMatDefaults()` — foot-gun removal).
9. **Admin** — company info polish. Users/Activity/Archived/Roadmap treated per §3.
10. **Tasks** — add-task button wiring, tab switching reliability.
11. **Work Order** — stale error clear, clock-in/out null-guard, empty state for "no active WO."
12. **Change Orders** — empty state, numeric-field guards before save.
13. **Bugs** — admin sees submit form only (per §3).
14. **Roadmap** — moved to standalone, dev-only (per §3).

Cross-cutting: no TODO/placeholder text surfaced, no lorem-ipsum, no broken images, no typos on user-facing copy.

### WS5. Document generator hardening
- `generate_proposal.py` pricing-options table — auto-wrap or truncate long option descriptions (target: 150 char hard limit with `…` suffix).
- `generate_change_order.py` — validate `add_total`, `deduct_total` are numeric before `float()`. Return 400 with a clear message if not.
- `generate_job_cost.py` — margin calc `ZeroDivisionError` guard (WS1 item, but covered here for completeness).
- Spot-check all 8 generators with two payloads each:
  - One realistic (real saved proposal).
  - One stripped (missing optional fields).
- No formatting regressions — compare against a known-good prior PDF.

### WS6. Runbook + handoff
Create `docs/kyle-handoff.md`. One page. Sections:
1. **Login** — URL, Kyle's username, how his password reaches him.
2. **What this app is** — one paragraph framing: HD's internal ops tool (proposals, pipeline, scheduling, docs).
3. **What Justin wants from Kyle** — scope of the eval, specific surfaces Kyle should touch, what "useful feedback" looks like.
4. **What's intentionally polish-pending** — transparent list of what we explicitly did not finish tonight (redesign rollout, mobile UX, etc.), so Kyle knows what to skip flagging.
5. **How to report a bug or idea** — in-app Bug Reports panel (submit form). One click, one screenshot, one description.
6. **When to escalate to Justin directly** — phone number for showstoppers (login broken, data loss, can't export).

Post-deploy smoke test checklist (not in runbook — internal):
- Log in as `kharrison@hdgrading.com`, walk every panel once, open DevTools console, confirm zero errors and zero log lines.
- Confirm Users / Roadmap / Bug Reports list are invisible.
- Confirm submit-a-bug form is visible and working.
- Log in as `justin@hdgrading.com`, confirm all dev-only surfaces reappear.
- Save a test proposal, edit it, export PDF, export DOCX, delete it. Verify no silent failures.
- Create a test client, edit, delete.
- Create a test work order, clock in, clock out, export daily report.

## 5. Scope Out (explicit)

These are NOT in tonight's ship:

- Any redesign work from `REDESIGN_BRIEF.md`, `REDESIGN_VISUAL_DIRECTIONS.md`, `REDESIGN_PAGE_SEQUENCE.md`, `REDESIGN_ACCOUNT_ARCHITECTURE.md`, or `REDESIGN_EXPORT_GUIDELINES.md`. That's a multi-week arc. Tonight is "handoff-ready," not "redesigned."
- H2 (ICS token) and H5 (magic-byte file upload) — waived.
- Mobile UX work beyond "doesn't overflow or break" — a real mobile pass is its own project.
- Feature additions — no new panels, no new routes, no new document types.
- Test coverage — no unit or integration tests added. We rely on the smoke test + Kyle's feedback loop.
- Feedback-system rebuild — no changes to the existing bug reports / feedback flow beyond the admin-visibility split.

## 6. Sequencing & Commit Strategy

Five commits, each independently revertable, each auto-deployed to Railway (~60s):

1. **Commit 1 — WS1 blockers.** Smallest, fastest, ship first to flush the obvious stuff.
2. **Commit 2 — WS3 backend hardening** + the `created_by` backfill migration. Highest-risk commit; revertable if anything goes sideways.
3. **Commit 3 — WS2 silent-failure** + `_safeFetch` helper. Biggest frontend mechanical change. Goes after backend because some handlers' error flows depend on the WS3 generic error messages.
4. **Commit 4 — WS4 per-panel polish + WS5 doc generator guards.**
5. **Commit 5 — WS6 runbook + CLAUDE.md + MEMORY.md updates.**

Each commit followed by: Railway redeploy, live smoke check on `/auth/check`, manual walk of a relevant surface, then continue.

## 7. Risk & Rollback

**Highest-risk items:**
- **H3 query-param helper** — touches 40+ call sites. A single bad edit silently breaks a page. Mitigation: write the helper, migrate one route, test, then migrate the rest in a single mechanical pass with a consistent find/replace.
- **H4 ownership checks** — could lock legacy records out if `created_by` is null. Mitigation: backfill to `estimates@hdgrading.com` first, then the null-safe guard also allows admin/dev to pass unconditionally.
- **H8 `_safe_error` migration** — subtle behavior change across ~30 routes. Mitigation: preserve original HTTP status codes; only the body message changes.
- **WS2 `_safeFetch` rollout** — if the helper has a bug, every save goes dark. Mitigation: ship helper + migrate one handler + verify before propagating.

**Rollback posture:** each commit is atomic and revertable via `git revert`. Railway redeploys on push, so a revert deploys the prior good state in ~60s.

## 8. Deferred Items — Rationale

| # | Waived? | Rationale |
|---|---|---|
| H2 | Yes | ICS token is static per `SECRET_KEY`; current user base is two trusted users; rotation flow is a larger auth feature. |
| H5 | Yes | File upload extension-only check is fine against execution risk (static-asset serving). Magic-byte lib adds a Python dependency for marginal value tonight. |

Both are re-evaluated in the next security batch, not as part of this ship.

## 9. Open Items for the Implementation Plan

Things the writing-plans skill will need to resolve:
- Exact file:line list for every edit site in WS2 (produced by a grep pass at plan time, not here).
- Exact `_sb_eq` helper signature and migration order for WS3.
- Runbook draft — content is outlined in WS6; actual text is written during the plan.
- Smoke-test script — we'll either write a one-shot `smoke.sh` or walk it manually. Plan-time call.

## 10. Success = Kyle's Morning

If, at 9am on 2026-04-21, Kyle can log in, click every nav item, build a proposal, move it through the pipeline, export a PDF, and submit one piece of feedback — all without seeing an error, a broken state, or a dev artifact — this ship worked.
