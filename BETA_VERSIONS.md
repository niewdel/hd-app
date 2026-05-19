# HD Platform — Beta Release Log

Ledger of every tagged beta push. Newest first. Each entry names the version,
the commit SHA it was cut from, what changed since the previous version, and
the Supabase migration state it expects.

## Workflow

1. Make changes locally. Do NOT auto-push every commit.
2. When a batch of changes is ready to hand off to Kyle for testing, we:
   - Bump `APP_VERSION` in `index.html`
   - Add an entry to the top of this file
   - Commit everything together with a `chore(release): vX.Y.Z` message
   - Push to `origin/main`
   - Tag the commit: `git tag vX.Y.Z && git push origin vX.Y.Z`
3. Kyle tests the new beta on Railway. If something breaks badly we can
   roll back via `git checkout vX.Y.Z-1 && git push -f` OR, less
   destructively, revert individual commits on top of `main`.

## Versioning

Semver-ish: `MAJOR.MINOR.PATCH`. While in beta we stay on `1.x`:
- **Patch** (1.0.1, 1.0.2): bug fixes, small tweaks, copy changes
- **Minor** (1.1.0): new features, additive work, no data migration
- **Major** (2.0.0): breaking changes, schema migrations that require planning

## Rollback notes

- **Frontend**: `git checkout vX.Y.Z -- index.html app.py && git push` or check
  out the whole tag and force-push to main (destructive — coordinate).
- **Database**: schema changes are tracked via Supabase migrations. See the
  "Supabase schema state" line on each entry below. If a rollback crosses a
  migration, may need to write a down-migration SQL manually.
- **Railway**: rolls back automatically on the next push. Can also roll back
  from the Railway dashboard (Deployments → pick an old one → "Redeploy").

---

## v1.2.0 — 2026-05-19 — Security hardening (pre-auth exposure fix)

**Why this is a minor bump and not a patch:** three pre-authentication
information leaks have been closed. The fixes change how the app is served
to unauthenticated visitors; they do not change any data model or in-app
behavior for logged-in users.

**Supabase schema state:** unchanged.

### What changed

1. **Source-code / repo leakage is closed.** Flask was configured with
   `static_folder='.', static_url_path=''`, which meant every file in the
   repo root was downloadable at the URL root — `/app.py`, `/security.py`,
   `/generate_proposal.py`, `/CLAUDE.md`, `/.git/config`, every `*.md`, and
   the Python source for the proposal generator were all `HTTP 200` from
   `https://hdapp.up.railway.app`. A new `before_request` filter in
   `app.py` enforces a strict allowlist of public assets (logos, driver
   CSS/JS, favicon) and `static/` for weather media; everything else
   returns `404`, including direct fetches of `index.html` and
   `login.html`. Env vars were the only credential store, so no secrets
   were leaked, but the source surface was readable.

2. **The `/` route is now server-gated.** Previously, every visitor was
   served the full 1.1 MB single-file SPA and the login screen was a
   CSS overlay on top of the already-loaded app. View-source / DevTools
   revealed all hardcoded pricing constants and the entire panel
   structure. Now: an unauthenticated `GET /` returns the standalone
   `login.html` (~7 KB, no app code), and only authenticated sessions
   ever receive the full app HTML.

3. **Pricing constants moved server-side.** All `MAT` (material costs),
   `CREWS_DEFAULT` (daily rates + productivity), `JC_*_DEFAULT`,
   `MOB_*_DEFAULT`, `TRUCK_*_DEFAULT`, `DRATE_DEFAULT`, `LBS_DEFAULT`,
   `DDEPTH_DEFAULT`, and `DDEPTH_INITIAL` literals were deleted from
   `index.html` and moved to a new `pricing_defaults.py` module. They
   are injected into the rendered HTML at request time via a placeholder
   replacement in `_render_index_for_session()` and read by the JS as
   `window.__HD_DEFAULTS__`. Customer-level overrides in
   `hd_settings` continue to overlay on top exactly as before.

### How auth flow works now

- `GET /` (anon) → `login.html` with `Cache-Control: no-store`.
- `POST /auth/login` (unchanged: bcrypt + rate limit + lockout).
- On login success the JS does `window.location.replace('/')`; the
  server now serves the full SPA because the session cookie is set.
- `POST /auth/logout` → existing flow (returns JSON, client reloads).
- Mid-session expiry: the in-page auth-check IIFE in `index.html` now
  redirects to `/` on `{authenticated: false}`, which serves `login.html`.

### Files touched

- `app.py` — `before_request` allowlist, conditional `/` route,
  `_render_index_for_session()` helper, `pricing_defaults` import.
- `pricing_defaults.py` — new module with all the JSON-serialized
  defaults plus a `serialize()` entry point.
- `login.html` — new standalone page. ~7 KB. No app code.
- `index.html` — pricing literals replaced with `_hdDef()` lookups
  against `window.__HD_DEFAULTS__`; injection placeholder added in
  `<head>`; login overlay hidden by default (kept only as a defensive
  fallback for session-expiry recovery).

### Rollback

If anything breaks for Kyle: `git checkout v1.1.4 -- index.html app.py
login.html pricing_defaults.py && git commit && git push`. The static
allowlist is the most defensible piece — leave it in if at all possible.

---

## v1.1.4 — 2026-04-30

**Commit:** tagged `v1.1.4`
**Supabase schema state:** unchanged from v1.1.3. One-shot data backfill applied (see Data section).

### Bug fix
- **Pipeline card totals no longer drift from proposal totals.** When an existing linked proposal was edited in the builder, the proposal's own `total` was updated but the parent project row's stored `proposals.total` was left at the value it had when the proposal was first linked. Pipeline cards read that stored column directly, so they showed stale numbers (e.g. Fordham's Cleaners pipeline $19,928 vs. proposal $25,307; PB Express off by $300K). Project-summary view was always correct because it recomputes from `linked_proposals` live.

### Frontend
- `saveQuote()` (`index.html` ~line 10492): after a successful PATCH on an existing proposal, scan `pipelineProposals` for any project whose `snap.linked_proposals` contains this proposal's id, recompute via `calcProjectTotal`, and PATCH the project's `total` if it changed. The new-proposal-link branch (`_pendingProjectLink`) was already correct and is unchanged.
- `updateProjectTotal()` at `index.html:6179` is the same shape as the new logic but had zero callers — leaving it in place for future use.

### Data
- Backfilled 7 stale projects with `UPDATE proposals SET total = sum(linked proposal totals)`. None had change orders so a flat sum was correct. Affected: PB Express - Grier Rd ($10K → $310,030), CSG Transportation Facility ($10K → $102,730), Michelin MARC ($125,903 → $155,403), The Loom at Fort Mill ($12,400 → $22,000), Fordham's Cleaners ($19,928 → $25,307), Woodlawn Community Fellowship ($232,547 → $235,247), Iredell Urgent Care MOB ($66,776 → $66,676). Audit query returns zero stale rows post-backfill.

---

## v1.1.3 — 2026-04-30

**Commit:** tagged `v1.1.3`
**Supabase schema state:** unchanged from v1.1.2. (The `hd_notifications.link` column already existed; this release is the first to populate it.)

### UX
- **Notifications are now clickable deep-links.** Clicking a "new lead" notification jumps to Contacts → Leads with the lead modal open; "new applicant" jumps to Contacts → Applicants with the applicant modal open; approval / public-approval notifications continue to land on the project summary. Old rows without a link still fall through to the previous `project_id` behavior, so nothing regresses.

### Backend
- New helper `_notif_link(kind, ref_id)` returns `'kind:id'` or `None`. Used at every `hd_notifications` insert site so the `link` column is populated:
  - `/leads/submit` → `lead:<id>`
  - `/applicants/submit` → `applicant:<id>`
  - `/pipeline/move/<id>` (Waiting for Approval) → `project:<id>`
  - `/pipeline/approve/<id>` → `project:<id>`
  - `/p/<token>` (public approval) → `project:<id>`
  - `/notifications/send` accepts an optional `link` in the body; defaults to `project:<id>` when `project_id` is set.

### Frontend
- New `_routeNotification(n)` parses the link (`kind:id`) and dispatches via `showPanel('contacts')` + `showContactsTab(...)` + `viewLead`/`viewApplicant`, or `openProjectSummary` for project links. Click handler at `index.html:15787-15790` now calls it instead of inlining the old project-only branch.

### PDF
- **Tightened spacing between site-plan heading and image.** Old layout sat the image area ~0.5"/0.58" below the slot top and then vertically centered the image inside that area, compounding into a wide gap under short headings. The image now sits a small fixed gap (~0.12"–0.16") below the heading and top-aligns within the slot, so the heading and image visually belong together.

---

## v1.1.2 — 2026-04-30

**Commit:** tagged `v1.1.2`
**Supabase schema state:** unchanged from v1.1.1.

### UX
- **Site plans pack 2-per-page in the exported proposal PDF.** 1 plan → full page (unchanged). 2 plans → stacked vertically on a single page with a hairline divider between them. 3+ plans → paginate 2 per page; the last page may carry a single plan. Per-plan headings shrink slightly (16pt → 13pt) when stacked so they don't dominate the slot.

---

## v1.1.1 — 2026-04-30

**Commit:** tagged `v1.1.1`
**Supabase schema state:** unchanged from v1.1.0.

### Fix
- **Proposal PDF: removed division grouping in the BID ITEMS table.** The grouped layout was silently mis-bucketing items: any line whose payload arrived with an empty `division` (e.g., concrete curb & gutter, pavement markings — both rendered without a `badgeCls` upstream) was inheriting the last division header in scope, so concrete and striping rows were appearing under "ASPHALT". Until the upstream classifier (`getLineItemsForPayload` at `index.html:10299` derives division from `badgeCls`, while the builder breakdown uses `_divisionForItem(item)` which derives from `trade` — they disagree) is reconciled, the PDF renders bid items as a flat list.

---

## v1.1.0 — 2026-04-30

**Commit:** tagged `v1.1.0`
**Supabase schema state:** one-time backfill applied to `proposals.snap`. Every row that previously had `snap.site_plan_url` or `snap.site_plan_data` now also has `snap.site_plans = [{url|data, label:''}]` — 8 rows touched, all URL-based. The legacy `site_plan_url` / `site_plan_data` keys are intentionally **left in place** for one release as a rollback safety net; cleanup is a follow-up. No DDL, no policy changes.

### Features
- **Multiple site plans per project.** Up to 8 plans per proposal/project, each with an optional label, attached as separate `Exhibit A` pages (in user-controlled order) on the exported proposal PDF.
  - Project summary card: replaced single thumbnail with a horizontal-scroll list. Each card has thumbnail (iframe for PDFs, img for images), label input, drag handle, delete. "+ Add Site Plan" tile at end (hidden at 8). Multi-select in the file picker uploads sequentially.
  - Proposal builder: the topbar "Site Plans" action opens a modal with the same UI. Plans live in memory as base64 until the proposal is saved; on save, they're flushed to Supabase Storage and the snap is rewritten with URL refs in a second PATCH.
  - PDF heading per plan: `Exhibit A — {label}` if a label is set, else `Exhibit A — Site Plan {n} of {total}` (single-plan output is unchanged).
  - Drag-to-reorder + label edits both fire a debounced `PATCH /site-plan/<id>` (full-array replace).
- **Storage layout change.** New uploads land at `project-{id}/site-plan-{uuid8}.{ext}` (no more upsert overwrite). DELETE route removes the underlying blob best-effort.

### Backend
- `POST /upload/site-plan/<int:project_id>` — now appends to `snap.site_plans`, accepts optional `label` form field, caps at `SITE_PLANS_MAX = 8`.
- `DELETE /site-plan/<int:project_id>` (new) — body `{index}`, splices the entry + best-effort Storage cleanup.
- `PATCH /site-plan/<int:project_id>` (new) — body `{plans: [...]}`, full-array replace for reorder + label edits.
- New helpers: `_load_proposal_snap`, `_site_plans_from_snap`, `_storage_path_from_url`.

### Fixes
- **Dashboard weather hero rain pill** moved from top-right (was overlapping the day pill / temperature) to bottom-right; "— plan crew" tagline removed. (Feedback #3)
- **Schedule panel rain alert** simplified to `<strong>X% chance of rain today</strong> — plan accordingly.` (Feedback #2 — the previous "Rain likely. Plan indoor tasks or have tarps ready." copy didn't fit a sitework context.)
- Both feedback items marked `reviewed` in `hd_feedback`.

### Out of scope this release
- Public proposal view (`/p/<token>`) does not render plans inline — clients still see plans only via the PDF download.
- Cleanup of legacy `snap.site_plan_url` / `snap.site_plan_data` fields — follow-up migration once multi-plan is confirmed stable.

---

## v1.0.2 — 2026-04-29

**Commit:** tagged `v1.0.2`
**Supabase schema state:** RLS now enabled on every public table with a permissive `backend_only_deny_direct_access` policy that blocks `anon` + `authenticated` (`USING (false) WITH CHECK (false)`). Service role bypasses RLS, so backend stays unaffected. Function lockdown:
- `public.purge_old_archived_proposals()` — `SET search_path = pg_catalog, public`; `EXECUTE` revoked from `PUBLIC, anon, authenticated` (pg_cron continues to run it as `postgres`).
- `public.rls_auto_enable()` — `EXECUTE` revoked from `PUBLIC, anon, authenticated` (event trigger `ensure_rls` continues to fire as the table creator).
- `hd_applicants` and `hd_companies` had RLS / policies / grants brought in line with the rest of the schema. `REVOKE ALL ... FROM anon, authenticated` applied to both.
- All Supabase security advisors come back clean (`{"lints":[]}`).
- Pipeline stage `Takeoff` (id 21) renamed to `Takeoff Done`.

### Security
- All Supabase security advisor findings resolved (1 ERROR, 1 INFO, 5 WARN → 0).
  Anon key now hits `permission denied` on every table and both RPC functions
  (`purge_old_archived_proposals`, `rls_auto_enable`).

### UX
- Pipeline: stage 2 renamed `Takeoff` → `Takeoff Done`. Tutorial + welcome
  modal copy updated to match.
- Contacts → Clients / Companies: removed the inline red ✕ delete buttons
  from each card. Delete is now inside the Edit modal as a `Delete Client`
  / `Delete Company` button anchored bottom-left in red, only visible in
  edit mode. Standard `confirm()` flow; modal closes on success.

---

## v1.0.1 — 2026-04-27

**Commit:** tagged `v1.0.1`
**Supabase schema state:** unchanged from v1.0.

### Fix
- `/auth/check` now returns `phone` and `avatar_data` alongside the rest of
  the user payload. Previously these were only included in `/auth/login`,
  so a fresh sign-in showed them correctly but every subsequent page reload
  wiped `window._userPhone` and `window._userAvatar` to empty strings —
  Kyle was hitting this every time he refreshed. The save flow and DB were
  always correct; only the read path on reload was leaking.

---

## v1.0 — 2026-04-24

**Commit:** tagged `v1.0` (see `git log --oneline --decorate`)
**Tag command:** `git tag v1.0 && git push origin v1.0`
**Supabase schema state:** all migrations through `feedback_add_status_fields`, `archive_auto_delete_90d`, plus pg_cron job `purge-archived-proposals` active.

**First production beta.** What Kyle is receiving:

### Features
- Proposals + projects + pipeline (Kanban / List / Map / Bid Calendar)
- Unified Line Items card in Proposal Builder (pavement sections,
  library items, custom qty × unit × price items with internal cost /
  margin tracking)
- Single grouped Line Item Breakdown with division subtotals + PDF export
- Contacts: Clients / Companies / Leads / Applicants tabs; CRM-style
  company entities with role flags (customer/subcontractor/both) and
  auto-fetched domain logos (Google faviconV2 + icon.horse fallback)
- Schedule (day/week/month, drag-to-assign)
- Reports (pipeline ratios, job costing, crew utilization, financials)
- Settings (materials, crew rates, item library — 41 items, company info)
- Feedback panel with mark-reviewed + delete for admin/dev
- Branded HTML email notifications for lead + applicant submissions
  (`estimates@hdgrading.com` always-on for leads)
- First-login interactive tutorial (Driver.js-based, navigates panels
  and spotlight-highlights features). Re-launchable from Help & Tour.
- Public iframe-able forms: `/lead-form`, `/applicants-form` with phone
  masking, strict email validation, honeypot spam protection, and
  optional Google Places address autocomplete
- Archive auto-delete: archived proposals hard-delete after 90 days via
  daily pg_cron job; manual × button for earlier permanent deletion
- Sidebar version pill shows `Beta v{APP_VERSION}` (this file's
  header)

### Known limits / deferred
- Full visual redesign rollout (multi-week, per REDESIGN_*.md docs)
- Mobile UX not polished — iPad is fine
- ICS calendar feed uses a single shared token (per-user rotation deferred)
- File upload magic-byte validation deferred
- Some construction client company logos appear as initials because
  their websites don't host a high-res favicon — paste a logo URL
  override on the company record to fix
