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
