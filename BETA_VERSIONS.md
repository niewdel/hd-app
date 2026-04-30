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
