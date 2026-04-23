# HD Hauling & Grading — Operations Platform
## CLAUDE.md — Project Context for Claude Code

**IMPORTANT: This file MUST be updated at the end of every session.** When a session ends or the user says they're done, update this file with any new routes, tables, features, conventions, or bug fixes before committing. This prevents knowledge loss between sessions.

### End-of-Session Checklist
1. **Update CLAUDE.md** — Add any new routes, tables, files, features, or conventions
2. **Update memory files** — Save any user preferences, feedback, or project context to memory
3. **Mark fixed bugs** — Every bug fixed must be marked as "Fixed" in `hd_bug_reports` table via Supabase API
4. **Commit CLAUDE.md** — Include in the final commit so it's available in the next session

---

## MCP Servers (Prioritize These)

Always check for and use available MCP tools before falling back to manual approaches (curl, WebFetch, etc.).

### Currently Installed
- **Google Calendar** — Use `gcal_*` tools for calendar operations (list events, create events, find free time, etc.)
- **Supabase** — Direct SQL execution and table management. Use Supabase MCP tools for all DB operations (creating tables, running migrations, querying data, updating bug reports). Authenticated via OAuth.

### Rule
When an MCP tool exists for a task, **always use it** instead of workarounds. Check `ToolSearch` at the start of each session to see what's available.

---

## Project Overview

An all-in-one internal web app for HD Hauling & Grading (paving contractor) — proposals, CRM, pipeline, scheduling, work orders, job costing, reporting, admin. Built with a Flask backend and a fully self-contained single-file frontend (`index.html`). Deployed on Railway, source on GitHub, database on Supabase.

---

## Infrastructure

| Resource | Value |
|---|---|
| **Live URL** | https://hdapp.up.railway.app |
| **GitHub Repo** | https://github.com/niewdel/hd-app |
| **Supabase Project** | azznfkboiwayifhhcguz |
| **Supabase URL** | https://azznfkboiwayifhhcguz.supabase.co |
| **Railway** | Auto-deploys from GitHub `main` branch |

### Supabase Direct Access
Bug reports and other DB tables can be queried directly via the Supabase REST API. The service role key is stored in the memory file `reference_supabase_access.md`. Use it like:
```bash
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/TABLE_NAME?select=*" \
  -H "apikey: SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer SERVICE_ROLE_KEY"
```
To update a record: `PATCH` to `...rest/v1/TABLE_NAME?id=eq.ID` with JSON body.

### Deployment
- Push to GitHub `main` branch → Railway auto-deploys (~60 seconds)
- Flask serves `index.html` as a static file from the root route `/`
- All other routes are API endpoints

---

## File Structure

```
/
├── index.html              # Entire frontend SPA — single self-contained file (~170KB+)
├── app.py                  # Flask backend (40+ routes)
├── generate_proposal.py    # PDF generator (ReportLab) — includes pricing options table
├── generate_change_order.py
├── generate_job_cost.py
├── generate_docx.py        # Word doc generator
├── generate_report.py      # Report PDF generator
├── generate_work_order.py
├── proposal_view.html      # PUBLIC page — shareable proposal view + client approval
├── lead_form.html          # PUBLIC page — quote-request form (iframe-aware)
├── applicants_form.html    # PUBLIC page — careers / job application form (iframe-aware, resume upload)
├── hd_logo.png             # Full logo (HD letters + HAULING & GRADING wordmark) — login screen + public form headers
├── hd-no-background.png    # Same as hd_logo.png but with transparent background — used in public form headers (replaces hd_logo)
├── hd-mark.png             # HD-only crop (no wordmark) — favicon + sidebar/topbar logo
├── requirements.txt
└── Procfile

NOTE: hd_logo_cropped.png is referenced by some PDF generators with a fallback to hd_logo.png; the cropped file does not currently ship in the repo.
```

---

## Database Schema (Supabase / PostgreSQL)

**All tables have RLS DISABLED.**

### `hd_users`
id, username (unique), full_name, email, phone, pin_hash (bcrypt), role (`admin`/`user`/`field`/`dev`), active, created_at, created_by, avatar_data (TEXT, base64 profile photo), failed_login_count, locked_until, last_login_at, password_updated_at, hourly_rate, welcome_seen_at (TIMESTAMPTZ — set when user dismisses the welcome modal; account-bound, not browser-bound), notif_prefs (JSONB — per-user notification preferences; shape `{inapp:{mention,assignment,stage_change,due_date,weather}, email:{new_leads,jobs_won,assignment,mention,jobs_lost}}`).

**Important conventions:**
- `username` is the canonical identifier referenced by `created_by`, `assigned_to`, `submitted_by`, etc., across many tables. Format: lowercase `firstname.lastname` (e.g. `justin.ledwein`, `kyle.harrison`). Renames cascade through `_cascade_username` in `app.py`.
- `email` is independent and used for login alongside username. Login accepts EITHER (`@` in input → email lookup with `@hdgrading.com` enforcement; no `@` → username lookup, no domain check).
- `pin_hash` is bcrypt; legacy SHA-256 hashes auto-migrate to bcrypt on next successful login.
- `password_hint` column does NOT exist — do not include it in inserts/updates.
- Avatar is stored in DB, NOT in Flask session (session cookies have ~4KB limit).

### `hd_access_log`
id, username, full_name, action (`login`/`logout`), success, ip_address, user_agent, logged_at.

### `proposals` (quotes/projects)
id, client_id, name, client, date, total, snap (JSONB — full proposal snapshot), stage_id (FK to pipeline_stages), status, notes, created_at, updated_at, created_by, archived, archived_at, share_token.

**There is NO top-level `project_number` column** — earlier docs were wrong. The project number lives inside `snap.project_number`. PostgREST 400s if you POST `project_number` in the row body. (Bit `convert_lead` 2026-04-22; backfilled.)

**`snap` MUST be passed as a dict object, NOT json.dumps(string).** PostgREST will store a stringified JSON inside the JSONB column if you pass a string, which breaks server-side jsonb queries (`snap->>'key'` returns NULL) and forces the frontend to double-`JSON.parse`. `/projects/create` does this correctly; `convert_lead` was fixed 2026-04-22.

**Design note — proposals and projects share this table.** A row with `snap.is_project = false` (or unset) is a proposal (estimate that may or may not become a job). A row with `snap.is_project = true` is a live project. **The Pipeline panel filter is `snap.is_project === true`** — rows without that flag are silently invisible there. New `convert_lead` flow now sets `is_project: true` so converted leads appear in Pipeline → Lead column.

This is intentional. The state transition from proposal → project is just a flag flip + linkage, with no data migration. Reports that need to scope to "actual projects" filter `snap.is_project === true`. Reports that span all opportunities iterate the full table.

A separate `projects` table was considered and rejected (2026-04-21): the cost of refactoring the JSONB-stored work orders / change orders / linked proposals into a normalized schema across ~16 frontend filter sites and 4-5 foreign-key tables was high, and the only benefit was conceptual cleanliness. The single-table + JSONB design is also a common Postgres pattern for entities that share most fields and differ by lifecycle stage.

Foreign keys: `change_orders.proposal_id`, `hd_time_entries.project_id`, and `hd_notifications.project_id` all reference `proposals.id` (the row's PK regardless of whether it's currently a proposal or a project).

Reports use the helpers `_isReportable(p)` and `_isProjectReportable(p)` (defined just above `selectReport()` in `index.html`) to filter source data. `_isReportable` strips archived rows AND any row in the **Disqualified** stage (counts_in_ratio:false in pipeline_stages — those deals never reached real evaluation, see 2026-04-22). `_isProjectReportable` additionally enforces `snap.is_project === true`. Use these in any new report or analytics function instead of inlining the check.

### `clients`
id, name, company, phone, email, address, city_state, notes.

### `pipeline_stages`
id, name, color, position, counts_in_ratio, is_closed.
**Live 8 stages** (verified via Supabase 2026-04-22):
1. Lead (id 19) — counts_in_ratio:false, is_closed:false
2. Takeoff (id 21) — false / false
3. Waiting for Approval (id 28) — false / false (triggers approval-request notification to approver group)
4. Approved (id 29) — false / false (internal pricing approval; locks proposal)
5. Sent (id 23) — false / false (auto-set when PDF exported)
6. Won (id 25) — true / true (triggers work-order auto-create + GC selection + jobs_won email)
7. Lost (id 26) — true / true (triggers jobs_lost email)
8. Disqualified (id 27) — false / true (excluded from reports via _isReportable)

NOTE: Older code references stale stage names like "New Lead", "Estimate Sent", "Follow Up", "Under Review", "Scheduled", "In Progress", "Completed" — these stages no longer exist. Reports/funnel still have hardcoded stale lists in 5 places (deferred sweep). The welcome modal + tour copy was fixed 2026-04-22.

### `hd_bug_reports`
id, title, description, severity (Minor/Major/Critical), panel, status (Open/In Progress/Fixed/Closed), submitted_by, submitted_at, browser_info, screen_info, admin_notes, resolved_at.

### `hd_reminders`
id, type (general/project/client), ref_id, ref_name, note, due_date, assigned_to, created_by, completed, completed_at, created_at.

### `hd_leads`
id, name, company, email, phone, address, description, source, status (new/accepted/rejected), matched_client_id, created_proposal_id, submitted_at.

### `hd_applicants` (new 2026-04-22)
id, name, email, phone, city_state, position, role_type (Office/Field/Either), years_exp (None/<1/1-3/3-5/5-10/10+), work_eligible BOOL, age_18_plus BOOL, has_license BOOL, cdl_class (None/Class A/Class B), resume_path, resume_filename, resume_mime, note, source, status (new/reviewed/contacted/rejected/hired), reviewed_by, reviewed_at, admin_notes, submitted_at.

Resume files live in the **`resumes` Supabase Storage bucket** (private; 5MB cap; PDF + DOC + DOCX only). Server-side proxy at `/applicants/<id>/resume` streams the file to authenticated office staff via the service-role key — bucket is never exposed to the browser directly.

### `hd_roadmap`
id, title, description, category, status, priority, version, created_at.

### `hd_notifications`
id, recipient, type, title, body, project_id, project_name, link, read, created_at.

### `hd_tasks`
id, title, description, priority (high/medium/low), status (open), visibility (public/private), assigned_to, created_by, due_date, ref_type (project/client), ref_id, ref_name, completed, completed_at, created_at, updated_at.

### `hd_settings`
key (PK, TEXT), value (JSONB), updated_at. Key-value store for app-wide settings (project_counter, company info, sender defaults, etc.).

### `hd_time_entries`
id, username, work_order_id, project_id, clock_in, clock_out, clock_in_lat, clock_in_lng, clock_out_lat, clock_out_lng, hours_worked, hourly_rate, labor_cost.

### `change_orders`
id, proposal_id, number, date, description, snap (JSONB), add_total, deduct_total, revised_total, created_by, created_at.

---

## Backend (`app.py`) — API Routes

### Auth
| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | none | Username + password login (returns role, username, full_name, email, phone, avatar_data, notif_prefs, welcome_seen) |
| POST | `/auth/logout` | yes | Clears session |
| GET | `/auth/check` | none | Returns auth status + user shell (role, username, full_name, email, notif_prefs, welcome_seen) |
| GET | `/auth/prefs` | yes | Returns current user's `notif_prefs` JSONB |
| PATCH | `/auth/prefs` | yes | Replaces current user's `notif_prefs` (always scoped to session user — no way to write another user's prefs) |

### Proposals/Quotes
| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/quotes/save` | yes | Save proposal snapshot |
| GET | `/quotes/list` | yes | List all saved proposals |
| PATCH | `/quotes/update/<id>` | yes | Update existing proposal |
| DELETE | `/quotes/delete/<id>` | yes | Archive a proposal |

### Public Proposal Sharing (NO AUTH)
| Method | Route | Description |
|---|---|---|
| POST | `/proposal/share/<id>` | Generate share token (requires auth) |
| GET | `/proposal/view/<token>` | Public JSON data for shared proposal |
| POST | `/proposal/approve/<token>` | Client approves proposal (public) |
| GET | `/p/<token>` | Serves public proposal view page |

### Lead Intake (NO AUTH for submit)
| Method | Route | Description |
|---|---|---|
| GET | `/lead-form` | Serves public lead intake form (iframe-allowed) |
| POST | `/leads/submit` | Public lead submission with auto client dedup. Validates email (`_valid_email`) + phone (normalized to `000-000-0000` via `_normalize_phone`); rejects honeypot via `_honeypot_tripped`. Notifies office staff in-app + HTML email (default ON). |
| GET | `/leads/list` | List leads (requires auth) |
| PATCH | `/leads/<id>` | Update lead status (requires auth) |
| POST | `/leads/<id>/convert` | Convert lead to project + client (requires auth). Sets `snap.is_project: true` so it appears in Pipeline. Uses `sb_admin_headers` (RLS on proposals). Returns ok:false on insert failure instead of silently marking lead accepted. |
| GET | `/forms/config` | Public, no auth. Returns `{places_key}` so the two iframe forms can load Google Places Autocomplete. Rate-limited 60/min/IP. Returns empty string if `GOOGLE_PLACES_API_KEY` env var is unset → forms fall back to plain text inputs. |

### Applicant Intake (NO AUTH for submit) — added 2026-04-22
| Method | Route | Description |
|---|---|---|
| GET | `/applicants-form` | Serves public job application form (iframe-allowed) |
| POST | `/applicants/submit` | Multipart upload — uploads resume to `resumes` Storage bucket, inserts hd_applicants row, fans in-app notif + HTML email (default ON via `_users_opted_in('new_applicants', default=True)`). Validates email + phone (normalized to `000-000-0000`); rejects honeypot. |
| GET | `/applicants/list` | List applicants (?status=new\|all). Auth required. |
| PATCH | `/applicants/<id>` | Update status (reviewed/contacted/rejected/hired) + admin_notes. Stamps reviewed_by/at. |
| GET | `/applicants/<id>/resume` | Server-side proxy that streams the resume file from the private Storage bucket using the service-role key. Auth required. |

### Reminders
| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/reminders/list` | yes | List reminders (?filter=due/upcoming/completed) |
| POST | `/reminders/save` | yes | Create reminder |
| PATCH | `/reminders/<id>` | yes | Update/complete reminder |
| DELETE | `/reminders/<id>` | yes | Delete reminder |

### PDF/Word Generation
| Method | Route | Description |
|---|---|---|
| POST | `/generate-pdf` | Generate proposal PDF (opens in browser tab for preview) |
| POST | `/generate-docx` | Generate proposal Word doc |
| POST | `/generate-co-pdf` | Generate change order PDF |
| POST | `/generate-job-cost` | Generate job cost sheet |

### Pipeline & Projects
| Method | Route | Description |
|---|---|---|
| GET | `/pipeline/list` | List all proposals with stage info |
| GET | `/pipeline/stages` | List pipeline stages |
| PATCH | `/pipeline/move/<id>` | Move proposal to new stage |
| POST | `/projects/create` | Create new project |
| PATCH | `/projects/update/<id>` | Update project |

### Clients & Subcontractors
| Method | Route | Description |
|---|---|---|
| GET | `/clients/list` | List all clients |
| POST | `/clients/save` | Save/update a client |
| DELETE | `/clients/delete/<id>` | Delete a client |
| GET/POST/DELETE | `/subs/*` | Same CRUD for subcontractors |

### Bug Reports
| Method | Route | Description |
|---|---|---|
| POST | `/bugs/submit` | Submit bug report (requires auth) |
| GET | `/bugs/list` | List all bug reports (admin only) |
| PATCH | `/bugs/<id>` | Update bug status/notes (admin only) |

### Admin
| Method | Route | Description |
|---|---|---|
| GET | `/admin/users` | List all users |
| POST | `/admin/users` | Create user (requires: full_name, username, password) |
| PATCH | `/admin/users/<id>` | Update user |
| GET | `/admin/logs` | Activity log |

### Tasks
| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/tasks/list` | yes | List tasks (?filter=open/completed), respects visibility |
| POST | `/tasks/save` | yes | Create task |
| PATCH | `/tasks/<id>` | yes | Update task fields |
| DELETE | `/tasks/<id>` | yes | Delete task |

### Boot
| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/boot/data` | yes | Returns quotes + pipeline stages + proposals in one call (parallel server-side) |

### Backend Helpers (added 2026-04-20, updated 2026-04-22)

- `_safe_error(e, context)` — logs internally via `app.logger.exception`, returns generic `{'error': 'Internal error. Check logs.'}` with 500. Use in authed routes; do NOT use for 400/403 semantic responses or public routes.
- `_sb_eq(column, value)` — URL-safe PostgREST filter via `urllib.parse.quote`. Use instead of f-string interpolation in any route that builds a `?col=eq.{var}` filter.
- `_owns_or_admin(record_created_by)` — null-safe ownership check. Returns True for admin/dev unconditionally; for other roles compares `record_created_by` to `session.get('username')`. Apply on update/delete routes.
- `set_security_headers` allowlists `https://hdapp.up.railway.app` for CORS, AND allows iframe embedding for `/lead-form` + `/applicants-form` only (everything else gets `X-Frame-Options: DENY` + `frame-ancestors 'none'`). The same two form routes also get `https://maps.googleapis.com` / `https://maps.gstatic.com` whitelisted in CSP `script-src` + `connect-src` so Google Places Autocomplete works — strictly scoped to those two paths.
- `/send-email` rate-limit: 20 sends per rolling 24h per user. Audit log to `hd_email_log` table — must exist in Supabase or rate limit silently fails open.
- `_users_opted_in(email_pref_key, default=False)` — returns active office users (admin/user/dev) opted in to a given email pref. **`default=True`** treats users with `notif_prefs.email[key]==null` as opted-in (used for `new_leads` and `new_applicants` so existing users get emails without re-saving prefs).
- `_send_lead_email(lead)` and `_send_applicant_email(applicant)` — both use the Gmail OAuth (`GMAIL_TOKEN_JSON`) and send from `admin@hdgrading.com`. Sender Gmail account configured 2026-04-22. Both send `multipart/alternative` with HTML + plain-text fallback (2026-04-23).
- `_render_form_email_html(title, name, subtitle, rows, badges=None, free_text_label=None, free_text=None, cta_label, cta_url)` — returns inline-CSS branded HTML for form-submission notification emails. Red header bar, 560px card, zebra-striped key/value rows, optional eligibility pills (green for true, gray for false), optional blockquote for free text, red CTA button. All inputs HTML-escaped via `html.escape`.
- `_normalize_phone(raw)` — returns `000-000-0000` or `None`. Strips non-digits; accepts optional leading `1` (strips it). Used by both public submit routes to enforce format.
- `_valid_email(raw)` — regex check (`^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$`). Bounded at 254 chars to avoid ReDoS. Stricter than HTML5 `type=email` (requires TLD).
- `_honeypot_tripped(payload)` — returns True if hidden `website_url` field was filled. Dict-like input. Used by both public submit routes to short-circuit bot submissions with a fake 200.

### Sender info (changed 2026-04-22)
The "From" name/email/phone on proposal PDFs and prefilled email templates **always reflects the logged-in user** (sourced from `hd_users.full_name/email/phone`). The previous shared `hd_sender` app setting was removed — Settings → Account is the single place to update it. `hydrateSenderFromAccount()` re-derives the sender global from `window._userName/_userEmail/_userPhone`.

### Other Routes
- `/roadmap/*` — Roadmap CRUD (admin)
- `/notifications/*` — Notification system
- `/schedule/feed.ics` — ICS calendar feed
- `/settings/get`, `/settings/save` — App-level settings

---

## Frontend (`index.html`) — Architecture

### Single-File Design
The entire frontend is one HTML file. All CSS, JS, and HTML in one file. No build step, no bundler. This is intentional — keeps deployment simple.

### Panels (navigation sections)
| Panel ID | Description |
|---|---|
| `panel-dashboard` | Dashboard — KPIs, weather, today's schedule, reminders, **Forms & Applicants** (combined leads + careers feed with red `QUOTE` / blue `CAREER` badges), recent activity |
| `panel-build` | Proposal builder with pricing options |
| `panel-project` | Single project detail view |
| `panel-projects` | Projects list + pipeline (Kanban) |
| `panel-contacts` | Clients + Subcontractors tabs |
| `panel-schedule` | Calendar views (day/3-day/week/month) |
| `panel-co` | Change order form |
| `panel-reports` | Reporting module |
| `panel-settings` | Settings — materials, crew, equipment, company info |
| `panel-admin` | Admin — user management, activity log, archived items |
| `panel-bugs` | Bug reports tab |
| `panel-roadmap` | Product roadmap tab |
| `panel-tasks` | Tasks & Reminders — two-tab panel (Tasks / Reminders) |
| `panel-workorder` | Work order detail view |

### Authentication Flow
1. Page loads → startup IIFE calls `/auth/check`
2. If authenticated: hides login screen, shows app, calls `boot()`, then `showAdminElements()`
3. If not: shows login screen with canvas animation
4. `doLogin()` → POST `/auth/login` with `{username, password}` → on success: set `window._userRole`, call `boot()`, `showAdminElements()`
5. `doLogout()` → POST `/auth/logout` → `location.reload()`
6. Users have username + password (min 6 chars). Passwords are SHA-256 hashed server-side and stored in `pin_hash` column.
7. Three roles: `admin`, `user`, `field`. Field users see a reduced UI (elements with `data-field-hidden` are hidden).

### Admin Nav Visibility
- `nav-admin` element has `data-admin-hidden` attribute by default
- CSS: `[data-admin-hidden]{display:none}`
- `showAdminElements()` calls `removeAttribute('data-admin-hidden')` on all `[data-admin-hidden]` elements
- **Critical**: `boot()` crashes if called when sections/DOM aren't ready — wrapped in `try/catch` so `showAdminElements()` always runs after

### Role Visibility Model (updated 2026-04-21)

- `dev` (Justin): sees everything, including Users / Activity Log / Archived / Roadmap / Bug Reports.
- `admin` (Kyle): sees Dashboard, Projects, Pipeline, Build Proposal, Saved Docs, Schedule, Contacts, Change Orders, Work Orders, Analytics, Reports, Settings, the Feedback panel, and the Admin → Company + Archived tabs. Hidden from admin: Users, Activity Log, Roadmap, Bug Reports (entire panel — admin uses Feedback instead, which is simpler / less specific). The Welcome modal copy intentionally does NOT mention what's hidden from admin (don't tip them off to features they don't have access to).
- `user`: standard operational role, sees the Feedback panel; no admin surfaces.
- `field`: reduced UI — Dashboard, Schedule, Work Orders, time tracking only. No pricing surfaces, no Feedback, no Bug Reports.

**Attribute rules:**
- `data-admin-hidden` — hidden from user/field, visible to admin+dev.
- `data-dev-hidden` — hidden from everyone except dev.
- `data-field-hidden` — hidden only from field.

`showAdminElements()` (around index.html:3852) removes these attributes based on `window._userRole`.

The Roadmap panel is now a standalone nav entry with `data-dev-hidden`, not a nested Admin tab. Admin tab list in `showAdminTab` is `['company','users','activity','deleted']` — no `'roadmap'`.

### Key Global Variables
```js
window._userRole      // 'admin' or 'user'
window._userName      // full name
window._userUsername  // username
window._adminUsers    // {id: userObject} map for edit modal

// Pricing data
MAT        // {material: costPerTon} — editable in Settings
MAT_DEFAULT // original defaults (for reset)
LBS        // {material: lbsPerTon} — hidden, not shown in UI
DRATE      // {material: defaultBidRate}
DDEPTH     // {material: defaultDepth}
LBADGE     // {material: badgeCssClass}
LTYPES     // array of material names

// Concrete types
CTYPES     // [{id, name, desc, unit, cy_per_lf}]
           // cy_per_lf = cubic yards per linear foot

// Badge definitions
BADGE_DEFS // {cssClass: {label, color}} — editable in Settings

// Bid Items Library
BID_LIBRARY  // [{id, name, desc, unit, material, mat_cost, crew, prod_rate, sub_cost, has_trucks, depth, category}]
_libId       // auto-increment counter for library items

// Crews (7 total)
CREWS_DEFAULT  // Asphalt, Stone, Grading, Utility, Erosion Control, Striping, Signage
CREWS          // loaded from Supabase/localStorage, migrated by _migrateLegacyTrades()

// Job cost
jcCrewRate      // crew day rate ($)
jcOverheadPct   // overhead %
jcProductivity  // tons/day (note: variable name is jcProductivity, NOT productivity)

// Proposal state
sections       // pavement preset sections array (multi-layer, with SF)
pavementItems  // pavement single items (from + Add Item / library)
concItems      // concrete items array
extraItems     // additional items array
siteWorkItems  // site work items array
```

### Material Pricing System
- Materials stored in `MAT` object (cost $/ton) — editable in Settings
- `MAT_DEFAULT` is the authoritative fallback — never corrupted by saved data
- `getMatCost(type)` helper resolves material cost with fallbacks: MAT → MAT_DEFAULT → bid library base material → mat_cost. **Always use `getMatCost()` instead of `MAT[type]` in calculations.**
- `LBS` stores density — 115 lbs/SY/inch for asphalt, 150 lbs/CF for stone
- `DRATE` stores default bid rates, `DDEPTH` stores default depths (non-zero)
- `LBADGE` maps material name → CSS badge class (= MAT_TRADE)
- `renderMatTable()` renders the settings table — all rows are deletable including defaults
- Density column intentionally removed from UI (still used in calculations)

### Tonnage Formulas (TWO different formulas based on material trade)
```js
function tons(sf, d, lbs, matType) {
  // Asphalt (b-asphalt): (SF/9 * lbs/2000) * depth_inches
  // Stone/default:        SF * depth_inches/12 * lbs/2000
}
```
- **Asphalt**: `(SF / 9 × 115 / 2000) × depth"` — density is per SY per inch
- **Stone**: `SF × depth" / 12 × 150 / 2000` — density is per cubic foot
- The 4th arg `matType` is required — determines which formula via `MAT_TRADE[matType]`

### Material Data Resolution
When Settings customization replaces standard material names (e.g., "ABC" → "Heavy Duty Aggregate Base Course"), `_applyMatPrices` backfills missing data from:
1. `MAT_DEFAULT` for standard materials
2. `DEFAULT_BID_LIBRARY` for bid library items (resolves `material` reference to base material)
3. Populates `LBS`, `DRATE`, `DDEPTH`, `MAT_TRADE` for all entries

### Concrete CY Calculation
```js
// cy_per_lf values per concrete type:
// 18" Standard C&G: 0.028, 24": 0.037, 30": 0.046
// 6" Vertical Curb: 0.012, 6" Mountable: 0.012
// Valley Gutter: 0.049, Ribbon Curb: 0.019
// Concrete Flume: 0.019, Thickened Edge: 0.009

function calcConcCY(item) {
  // returns cubic yards = qty * cy_per_lf
}
```
CY is displayed in green next to each concrete row result.

### Settings Panel Cards (in order)
1. **Sender Information** — name, email, phone for proposal header
2. **Job Cost Defaults** — crew day rate, overhead %, productivity (t/day)
3. **Material Prices** — editable table (cost, rate, depth, badge) + delete all rows
4. **Layer Badges** — add/remove/rename badge types (Base, Binder, Surface, Millings, Concrete)
5. **Item Library** — reusable line items with descriptions (UI label is "Item Library", code var is `BID_LIBRARY`)

### Item Library (code: BID_LIBRARY)
- Stored in Supabase (`hd_bid_library`) + localStorage cache — 130 items
- No "Load Defaults" button — library is fully user-managed
- Each item has: name, desc, unit, material, mat_cost, crew, prod_rate, sub_cost, has_trucks, depth, category
- `renderLibraryList()` — renders in Settings (columns: Category, Name, Description, Unit, Crew)
- `openLibraryPicker()` — modal picker in Build Proposal

### Estimating Engine (Site Work / Extra / Pavement Items)
- **calcItemDays(item)**: uses `item.prod_rate` first, falls back to crew default productivity
- **calcItemLabor(item)**: days × crew daily_rate (or sub_cost × qty for concrete/traffic control)
- **calcItemTrucking(item)**: trucks × days × truck daily rate (for has_trucks items)
- **calcItemBid(item)**: (material + labor + trucking) × (1 + markup%)
- **Special item types:**
  - Concrete (`_isConcreteItem`): sub_cost per unit, no crew days
  - Striping (`_isStripingItem`): lump sum price + markup only
  - Sub cost items (`_isSubCostItem`): labor = qty × sub_cost (traffic control, concrete)
  - Export/import items (`has_trucks`): show Trucks field, trucking added to cost
- **Single-item sections** (`singleItem:true`): compact layout, SF inline, no header/footer
- **Auto-save**: 2-second debounce, quiet mode (no toast)
- **Autocomplete**: `_autoSelected` flag prevents change handler from overwriting title

### Crew System (7 crews)
```
Asphalt Crew    | b-asphalt | $5,000/day | 400 TON/day
Stone Crew      | b-stone   | $2,500/day | 800 TON/day
Grading Crew    | b-grading | $4,000/day | 500 CY/day
Utility Crew    | b-utility | $3,500/day | 120 LF/day
Erosion Ctrl    | b-erosion | $1,800/day | 2,000 LF/day
Striping Crew   | b-striping| $2,500/day | 5,000 LF/day
Signage Crew    | b-signage | $1,000/day | 40 EA/day
```
- `_migrateLegacyTrades()` converts old trade strings (b-storm-drain→b-utility, etc.)
- `_resolveTradeForMat()` resolves material→trade via MAT_TRADE, MAT_TRADE_DEFAULT, bid library

### Login Page
- Full-screen black background with animated red particle network canvas (`initLoginCanvas()`)
- Canvas: 60 nodes drifting, connected with red lines when within 160px
- White top bar with HD logo
- "HD HAULING & GRADING" title: `font-size:30px`, red, letter-spaced
- Username + PIN fields, ACCESS TOOL button

### Admin Panel
- **User Management tab**: table of all users, Edit button for all (including self), Deactivate for others only
- **Activity Log tab**: timestamped logins with IP, filterable by user
- Edit user modal uses `window._adminUsers[id]` lookup (not JSON.stringify inline) to avoid escaping issues with special chars in names

### Frontend Helpers (added 2026-04-20)

- `_safeFetch(url, opts)` (around index.html:3845) — async fetch wrapper. Throws on non-2xx with the server's `{error}` message attached. Use in EVERY save/delete/update UI handler. Pattern: wrap in try/catch; show error toast in catch; do NOT close the modal on failure.
- `_wxVideoUrl(code, tod)` — maps weather code + time of day to `/static/wx/wx-*.mp4` path.
- `_wxTimeOfDay(data)` — returns `'dawn' | 'day' | 'dusk' | 'night'` for the selected day, using API sunrise/sunset when available with clock-heuristic fallback.
- `_wxSelectedDay` — module-level integer, default 0 (today). `_selectWxDay(idx)` updates it and re-renders both hero and daily strip.

### Weather Widget Architecture (rebuilt 2026-04-20)

- Open-meteo API at `latitude=35.4088, longitude=-80.5795` (Concord, NC), 30-min cache via `_weatherCache` global.
- Hero band uses `<video autoplay loop muted playsinline>` from `/static/wx/wx-*.mp4` (Mixkit free-for-commercial-use clips, ~36 MB total). Mapped via `_wxVideoUrl(code, tod)`.
- 9 video files: `wx-clear-day`, `wx-clear-night`, `wx-partly-day`, `wx-partly-night`, `wx-overcast`, `wx-fog`, `wx-rain` (also covers drizzle and heavyrain), `wx-snow`, `wx-storm`.
- Daily forecast strip: 7 clickable tiles. Tapping a tile sets `_wxSelectedDay` and the hero swaps to that day's data + video.
- Schedule panel weather widget is unchanged (still uses canvas animation system) — explicit scope decision; can migrate to video later for visual consistency.

---

## Known Issues & Important Notes

### ⚠️ File Editing Warning
**Do NOT edit `index.html` using string concatenation or template literals with mixed quote styles.** All previous corruption was caused by this. Always use:
- DOM API (`createElement`, `addEventListener`) for dynamic content
- Simple string replacements with consistent quote style
- Test with `src.includes('functionName')` before pushing

### ⚠️ boot() Error Handling
`boot()` is wrapped in `try/catch` in both the doLogin and auth/check paths because `renderJCDefaults()` can throw if called before the DOM is ready. `showAdminElements()` must always run AFTER boot(), even if boot throws.

### ⚠️ Avatar Data — DB Not Session
Avatar data (base64 profile photos) MUST be stored in `hd_users.avatar_data` column, NOT in Flask session. Session cookies have a ~4KB limit; base64 images are 40-110KB. Images are compressed to 256px max / 0.7 quality on the client side.

### ⚠️ Proposal Number in buildPayload()
`buildPayload()` must use `indexOf(lastSavedQuoteId)` in `linked_proposals` to find the correct proposal index (P1, P2, etc.). Do NOT use `linked_proposals.length + 1` — the current proposal is already in the array after saving.

### ⚠️ Striping/Lump-Sum Items in Breakdown
For striping items (`crew === 'b-striping'`), the breakdown markup % must use `item.markup` directly, NOT `(bid-cost)/cost`. The latter produces astronomical numbers because `mat_cost` and `calcItemLabor()` both return 0 for striping items.

### ⚠️ Variable Name: `jcProductivity`
The productivity variable is `jcProductivity` — NOT `productivity`. Using `productivity` causes a ReferenceError that crashes `boot()`.

### ⚠️ Admin Nav
Uses `data-admin-hidden` attribute + CSS `[data-admin-hidden]{display:none}`. Do NOT use inline `style.display=''` (empty string) to show it — this clears the inline style but the CSS class rule still hides it. Use `removeAttribute('data-admin-hidden')` instead.

### ⚠️ Pushing to GitHub
The only safe way to push is via the GitHub Contents API with proper base64 encoding:
```js
const bytes = new TextEncoder().encode(src);
let bin = '';
for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
const b64 = btoa(bin);
// Verify roundtrip before pushing:
const rt = new TextDecoder('utf-8').decode(Uint8Array.from(atob(b64), c => c.charCodeAt(0))) === src;
```
Always verify roundtrip. Never use `btoa(unescape(encodeURIComponent(src)))` — causes file doubling.

### renderExtra() and renderBadgeList()
These functions MUST use the DOM API, not innerHTML string building. Previous versions using HTML strings caused `SyntaxError: Unexpected identifier` that broke the entire app.

### ⚠️ Public form conventions (lead_form.html + applicants_form.html)
- **Phone input**: client-side mask auto-formats to `555-123-4567` on `input`; HTML `pattern="[0-9]{3}-[0-9]{3}-[0-9]{4}"` + `maxlength="12"`. Server normalizes via `_normalize_phone` (accepts any input, rejects if not 10 digits). Stored format in `hd_leads.phone` / `hd_applicants.phone` is always `000-000-0000`.
- **Email input**: HTML `pattern` requires TLD; server re-validates via `_valid_email`.
- **Honeypot**: hidden `<input name="website_url">` on both forms (visually offscreen, `aria-hidden="true"`, `tabindex="-1"`). Real users never touch it; if filled, the server returns a fake `{ok:true}` and skips all DB writes / notifications / email. Log line: `[honeypot] /leads/submit rejected submission from <ip>`.
- **Google Places**: both forms fetch `/forms/config` on load, then inject `maps.googleapis.com/maps/api/js?libraries=places&loading=async` only if the key is present. If the key or fetch fails, inputs stay as plain text — forms keep working.
- **Env var**: `GOOGLE_PLACES_API_KEY` is a browser-exposed key; lock it down in Google Cloud console with HTTP-referrer restrictions (`https://hdapp.up.railway.app/*` + any embed domain) and API restrictions (Places + Maps JavaScript only).

---

## Default Seed Data

### Admin User
- Username: `justin`
- Full Name: Justin Ledwein
- Role: admin

### Default Materials
```js
MAT = {'ABC':30, '#57 Stone':35, 'S9.5B':100, 'S9.5C':90, 'I19.0C':90, 'B25.0C':90, 'Concrete':200, ...}
LBS = {'ABC':150, '#57 Stone':150, 'S9.5B':115, 'S9.5C':115, 'I19.0C':115, 'B25.0C':115, 'Concrete':150, ...}
DDEPTH = {'ABC':6, '#57 Stone':3, 'S9.5B':1.5, 'S9.5C':2, 'I19.0C':2.5, 'B25.0C':4, 'Concrete':4}
```

### Presets (Proposal Builder)
```js
PRESETS = [
  {name:'Light Duty Asphalt', layers:[{type:'ABC',depth:6}, {type:'S9.5C',depth:2}]},
  {name:'Heavy Duty Asphalt', layers:[{type:'ABC',depth:8}, {type:'I19.0C',depth:2.5}, {type:'S9.5C',depth:1.5}]},
  {name:'Parking Lot', layers:[{type:'ABC',depth:6}, {type:'S9.5C',depth:2}]},
  {name:'NCDOT Pavement', layers:[{type:'B25.0C',depth:5}, {type:'I19.0C',depth:4}, {type:'S9.5C',depth:3}]},
  {name:'Mill & Overlay', layers:[{type:'S9.5B',depth:1.5}, {type:'S9.5C',depth:1.5}]},
  {name:'Stone Driveway', layers:[{type:'ABC',depth:6}, {type:'#57 Stone',depth:3}]},
]
```
- Presets have `name` (friendly) and `description` fields per layer — NO `rate` field (uses DRATE defaults)
- Presets can be overridden from localStorage (`hd_presets`) or Supabase
- Material dropdown always includes the layer's `type` even if not in LTYPES (prevents mismatch)

### Crew & Trucking System
```js
CREWS = [
  {name:'Asphalt Crew', trade:'b-asphalt', daily_rate:5000, productivity:400, prod_unit:'TON'},
  {name:'Stone Crew', trade:'b-stone', daily_rate:2500, productivity:800, prod_unit:'TON'},
  {name:'Concrete Crew', trade:'b-concrete', daily_rate:3500, productivity:50, prod_unit:'CY'},
  // ... more crews
]
MAT_TRADE = {'ABC':'b-stone', 'S9.5B':'b-asphalt', 'I19.0C':'b-asphalt', ...}
```
- `getCrewParam(matType, param)` — resolves crew by material's trade
- Trucking: `trucks × $800/day × days` (TRUCK_RATE=$100/hr × 8hrs)
- `calcTruckCount` uses `tons/day ÷ tons_per_truck` (default 100 t/truck)
- `updTrucks` and `updLyrDays` must use crew-specific productivity and include `days_override` in temp objects

---

## Bug Report Workflow

Bug reports are stored in the `hd_bug_reports` table in Supabase and viewed in the app's Bug Reports tab.

### How to read bug reports
Query the Supabase REST API directly:
```bash
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/hd_bug_reports?select=*&order=submitted_at.desc" \
  -H "apikey: SERVICE_ROLE_KEY" -H "Authorization: Bearer SERVICE_ROLE_KEY"
```
Filter by status: append `&status=eq.Open` to the URL.

### How to mark a bug as fixed
After fixing a bug, ALWAYS update its status in Supabase:
```bash
curl -s -X PATCH "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/hd_bug_reports?id=eq.BUG_ID" \
  -H "apikey: SERVICE_ROLE_KEY" -H "Authorization: Bearer SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" -H "Prefer: return=minimal" \
  -d '{"status":"Fixed","admin_notes":"Description of what was fixed","resolved_at":"ISO_TIMESTAMP"}'
```
**This is mandatory.** Every bug fix must update the bug report status to "Fixed" with a note describing the fix.

---

## Pending / Future Work

- [ ] Phase tabs: multi-phase support partially built but not fully wired
- [ ] Badge Manager: dynamically inject CSS for custom badge colors
- [ ] Concrete items: allow custom `cy_per_lf` override per item
- [ ] Truck calculator: user reported still needs testing after override fixes (2026-03-30)
- [ ] Verify material costs populate correctly for all presets after Settings customization
- [ ] Replace schedule-panel weather canvas with video for visual consistency with dashboard
- [ ] Per-user ICS calendar feed tokens (deferred from H2)
- [ ] File upload magic-byte validation (deferred from H5)
- [ ] Full visual redesign rollout per `REDESIGN_*.md` docs

---

## Common Tasks

### Add a new API route
1. Edit `app.py`
2. Add route with `@app.route(...)` decorator
3. Use `@require_auth` or `@require_admin` decorator as needed
4. Push to GitHub → Railway redeploys

### Add a new settings card
1. Add HTML card div inside `#panel-settings` in `index.html`
2. Add JS render function (use DOM API, not innerHTML strings)
3. Call the render function from `showPanel()` when `name === 'settings'`
4. Persist to `localStorage` if user-editable

### Update material pricing defaults
Edit the `MAT`, `LBS`, `DRATE`, `DDEPTH`, `LBADGE` objects near line ~920 in `index.html`.

### Add a new concrete type
Add an entry to `CTYPES` array with `{id, name, desc, unit:'LF', cy_per_lf:X}`.

### Create a new user
Use the Admin panel in the app, or POST to `/admin/users` with `{username, full_name, password, role}`.
Required fields: `full_name`, `username`, `password` (min 6 chars). Optional: `email`, `phone`, `role`.

### Fix a bug report
1. Read bug reports from Supabase (see Bug Report Workflow section)
2. Fix the code
3. Update the bug status to "Fixed" in Supabase with admin_notes (MANDATORY)
4. Commit and push

---

## Skill References

- Before performing any algorithmic art tasks, read and follow the instructions in `skills/algorithmic-art/SKILL.md`.
- Before performing any brand guidelines tasks, read and follow the instructions in `skills/brand-guidelines/SKILL.md`.
- Before performing any canvas design tasks, read and follow the instructions in `skills/canvas-design/SKILL.md`.
- Before performing any Claude API tasks, read and follow the instructions in `skills/claude-api/SKILL.md`.
- Before performing any document co-authoring tasks, read and follow the instructions in `skills/doc-coauthoring/SKILL.md`.
- Before performing any Word document (.docx) tasks, read and follow the instructions in `skills/docx/SKILL.md`.
- Before performing any frontend design tasks, read and follow the instructions in `skills/frontend-design/SKILL.md`.
- Before performing any internal communications tasks, read and follow the instructions in `skills/internal-comms/SKILL.md`.
- Before performing any MCP server building tasks, read and follow the instructions in `skills/mcp-builder/SKILL.md`.
- Before performing any PDF tasks, read and follow the instructions in `skills/pdf/SKILL.md`.
- Before performing any PowerPoint (.pptx) tasks, read and follow the instructions in `skills/pptx/SKILL.md`.
- Before performing any skill creation tasks, read and follow the instructions in `skills/skill-creator/SKILL.md`.
- Before performing any Slack GIF creation tasks, read and follow the instructions in `skills/slack-gif-creator/SKILL.md`.
- Before performing any theme/styling tasks, read and follow the instructions in `skills/theme-factory/SKILL.md`.
- Before performing any web artifact building tasks, read and follow the instructions in `skills/web-artifacts-builder/SKILL.md`.
- Before performing any web application testing tasks, read and follow the instructions in `skills/webapp-testing/SKILL.md`.
- Before performing any spreadsheet (.xlsx) tasks, read and follow the instructions in `skills/xlsx/SKILL.md`.
