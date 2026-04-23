# HD Hauling & Grading — Operations Platform
## CLAUDE.md — Project Context for Claude Code

**IMPORTANT: Update this file at the end of every session** when new routes, tables, conventions, or bug fixes land. Prevents knowledge loss between sessions.

### End-of-Session Checklist
1. **Update CLAUDE.md** — new routes, tables, files, or conventions
2. **Update memory files** — user preferences, feedback, project context
3. **Mark fixed bugs** — status "Fixed" in `hd_bug_reports` via Supabase (see Bug Report Workflow)
4. **Commit CLAUDE.md** with the final commit

---

## MCP Servers

Prefer MCP tools over manual approaches (curl, WebFetch) when one fits. Check `ToolSearch` at session start to see what's available.

- **Supabase** — direct SQL, migrations, table management (OAuth). Use for all DB work when possible.
- **GitHub** — PR creation, issue reads, repo operations.
- **Google Calendar** — `gcal_*` tools.

---

## Project Overview

Internal operations web app for HD Hauling & Grading (paving contractor): proposals, CRM, pipeline, scheduling, work orders, job costing, reporting, admin. Flask backend + single-file SPA (`index.html`). Deployed on Railway, source on GitHub, database on Supabase.

---

## Infrastructure

| Resource | Value |
|---|---|
| **Live URL** | https://hdapp.up.railway.app |
| **GitHub Repo** | https://github.com/niewdel/hd-app |
| **Supabase Project** | azznfkboiwayifhhcguz |
| **Supabase URL** | https://azznfkboiwayifhhcguz.supabase.co |

### Deployment
- Push to GitHub `main` → Railway auto-deploys (~60 seconds)
- Flask serves `index.html` at `/`; every other route is an API endpoint
- Commit + push via plain `git` on the command line

### Supabase Direct Access
Service role key is in memory file `reference_supabase_access.md`. Prefer the Supabase MCP tool; fall back to PostgREST when needed:
```bash
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/TABLE_NAME?select=*" \
  -H "apikey: SERVICE_ROLE_KEY" -H "Authorization: Bearer SERVICE_ROLE_KEY"
```
PATCH: `...rest/v1/TABLE?id=eq.ID` with a JSON body.

### Environment Variables (Railway)
- `SECRET_KEY` — Flask session key (must be non-default; app refuses to boot otherwise)
- `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_KEY`
- `GMAIL_TOKEN_JSON` — OAuth token; sends mail as `admin@hdgrading.com`
- `GOOGLE_PLACES_API_KEY` — browser-safe Places key. Optional; forms fall back to plain text if unset.

---

## Database Schema (Supabase / PostgreSQL)

**All tables have RLS DISABLED.** Backend uses the service role key for all queries.

### `hd_users`
id, username (unique), full_name, email, phone, pin_hash (bcrypt), role (`admin`/`user`/`field`/`dev`), active, created_at, created_by, avatar_data (TEXT, base64), failed_login_count, locked_until, last_login_at, password_updated_at, hourly_rate, welcome_seen_at (TIMESTAMPTZ — account-bound, not browser-bound), notif_prefs (JSONB — `{inapp:{mention,assignment,stage_change,due_date,weather}, email:{new_leads,jobs_won,assignment,mention,jobs_lost,new_applicants}}`).

**Conventions:**
- `username` is the canonical identifier (referenced by `created_by`, `assigned_to`, `submitted_by`, etc.). Format: lowercase `firstname.lastname`. Renames cascade via `_cascade_username` in `app.py`.
- `email` is independent and used for login alongside username. Login accepts EITHER (`@` in input → email lookup, `@hdgrading.com` enforced; no `@` → username lookup).
- `pin_hash` is bcrypt. Legacy SHA-256 hashes auto-migrate on next successful login.
- `password_hint` column does NOT exist.
- Avatar is stored in DB, not Flask session (session cookies have ~4KB limit; base64 images are 40–110KB).

### `proposals` (quotes AND projects share this table)
id, client_id, name, client, date, total, snap (JSONB — full proposal snapshot), stage_id (FK to pipeline_stages), status, notes, created_at, updated_at, created_by, archived, archived_at, share_token.

**Critical:**
- **NO top-level `project_number` column.** It lives in `snap.project_number`. Posting it in the row body returns PGRST204.
- **`snap` MUST be a dict, NOT `json.dumps(...)`.** PostgREST stores stringified JSON inside JSONB which breaks server-side `snap->>'key'` queries.
- **Proposal vs. project is a flag, not a table.** `snap.is_project === true` means live project; absent/false means still a proposal. The Pipeline panel filter is `snap.is_project === true` — rows without that flag are silently invisible. Both `convert_lead` and `/projects/create` set this correctly.
- Foreign keys `change_orders.proposal_id`, `hd_time_entries.project_id`, and `hd_notifications.project_id` all reference `proposals.id` regardless of lifecycle stage.
- Reports use `_isReportable(p)` and `_isProjectReportable(p)` (defined just above `selectReport()` in `index.html`). `_isReportable` strips archived rows AND any row in the **Disqualified** stage. `_isProjectReportable` additionally enforces `snap.is_project === true`. Use these in any new report/analytics function instead of inlining the check.

A separate `projects` table was considered and rejected (2026-04-21): refactoring the JSONB-stored work orders / change orders / linked proposals into a normalized schema across ~16 frontend filter sites and 4-5 foreign-key tables was high-cost, low-benefit.

### `pipeline_stages` (8 live stages as of 2026-04-22)
id, name, color, position, counts_in_ratio, is_closed.

1. **Lead** — counts_in_ratio:false, is_closed:false
2. **Takeoff** — false / false
3. **Waiting for Approval** — false / false (triggers approval-request notification to approver group)
4. **Approved** — false / false (internal pricing approval; locks proposal)
5. **Sent** — false / false (auto-set when PDF exported)
6. **Won** — true / true (triggers work-order auto-create + GC selection + jobs_won email)
7. **Lost** — true / true (triggers jobs_lost email)
8. **Disqualified** — false / true (excluded from reports via `_isReportable`)

Older code references stale stage names ("New Lead", "Estimate Sent", "Follow Up", "Under Review", "Scheduled", "In Progress", "Completed") — these no longer exist. Reports/funnel still have hardcoded stale lists in 5 places (deferred sweep).

### Other tables
- `clients` — id, name, company, phone, email, address, city_state, notes
- `hd_access_log` — id, username, full_name, action (login/logout), success, ip_address, user_agent, logged_at
- `hd_bug_reports` — id, title, description, severity, panel, status (Open/In Progress/Fixed/Closed), submitted_by, submitted_at, browser_info, screen_info, admin_notes, resolved_at
- `hd_reminders` — id, type, ref_id, ref_name, note, due_date, assigned_to, created_by, completed, completed_at, created_at
- `hd_leads` — id, name, company, email, phone, address, description, source, status (new/accepted/rejected), matched_client_id, created_proposal_id, submitted_at
- `hd_applicants` — id, name, email, phone, city_state, position, role_type, years_exp, work_eligible, age_18_plus, has_license, cdl_class, resume_path, resume_filename, resume_mime, note, source, status (new/reviewed/contacted/rejected/hired), reviewed_by, reviewed_at, admin_notes, submitted_at. Resume files live in the **private `resumes` Supabase Storage bucket** (5MB cap; PDF/DOC/DOCX only); `/applicants/<id>/resume` streams them server-side — bucket never exposed to browsers.
- `hd_notifications` — id, recipient, type, title, body, project_id, project_name, link, read, created_at
- `hd_tasks` — id, title, description, priority, status, visibility (public/private), assigned_to, created_by, due_date, ref_type, ref_id, ref_name, completed, completed_at, created_at, updated_at
- `hd_settings` — key (PK, TEXT), value (JSONB), updated_at
- `hd_time_entries` — id, username, work_order_id, project_id, clock_in, clock_out, clock_in/out_lat/lng, hours_worked, hourly_rate, labor_cost
- `hd_roadmap` — id, title, description, category, status, priority, version, created_at
- `change_orders` — id, proposal_id, number, date, description, snap (JSONB), add_total, deduct_total, revised_total, created_by, created_at
- `hd_email_log` — audit log for `/send-email` rate limiter (20 sends / 24h / user)
- `hd_bid_library` — the 130-item reusable line-item library (`BID_LIBRARY` in frontend)

---

## Backend (`app.py`) — API Routes

### Auth
| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | none | Username + password login. Returns role, username, full_name, email, phone, avatar_data, notif_prefs, welcome_seen |
| POST | `/auth/logout` | yes | Clears session |
| GET | `/auth/check` | none | Returns auth status + user shell |
| GET | `/auth/prefs` | yes | Returns current user's `notif_prefs` |
| PATCH | `/auth/prefs` | yes | Replaces current user's `notif_prefs` (always scoped to session user) |

### Proposals / Quotes
| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/quotes/save` | yes | Save proposal snapshot |
| GET | `/quotes/list` | yes | List all saved proposals |
| PATCH | `/quotes/update/<id>` | yes | Update existing proposal |
| DELETE | `/quotes/delete/<id>` | yes | Archive a proposal |

### Public Proposal Sharing
| Method | Route | Description |
|---|---|---|
| POST | `/proposal/share/<id>` | Generate share token (auth) |
| GET | `/proposal/view/<token>` | Public JSON data for shared proposal |
| POST | `/proposal/approve/<token>` | Client approves proposal (public) |
| GET | `/p/<token>` | Serves public proposal view page |

### Lead Intake
| Method | Route | Description |
|---|---|---|
| GET | `/lead-form` | Public lead intake form (iframe-allowed) |
| POST | `/leads/submit` | Public. Auto client dedup. Validates email (`_valid_email`) + phone (normalized via `_normalize_phone` to `000-000-0000`); rejects honeypot via `_honeypot_tripped`. In-app + HTML email notifications (default ON). |
| GET | `/leads/list` | List leads (auth) |
| PATCH | `/leads/<id>` | Update lead status (auth) |
| POST | `/leads/<id>/convert` | Convert lead to project + client (auth). Sets `snap.is_project: true` so it appears in Pipeline. |
| GET | `/forms/config` | Public. Returns `{places_key}` so iframe forms can load Google Places Autocomplete. Rate-limited 60/min/IP. Empty string if `GOOGLE_PLACES_API_KEY` unset → forms fall back to plain text. |

### Applicant Intake
| Method | Route | Description |
|---|---|---|
| GET | `/applicants-form` | Public job application form (iframe-allowed) |
| POST | `/applicants/submit` | Multipart upload. Uploads resume to `resumes` bucket, inserts row, fans in-app notif + HTML email (default ON). Same validation + honeypot as leads. |
| GET | `/applicants/list` | List applicants (`?status=new|all`, auth) |
| PATCH | `/applicants/<id>` | Update status + admin_notes; stamps reviewed_by/at |
| GET | `/applicants/<id>/resume` | Server-side proxy; streams resume via service-role key (auth) |

### Reminders
| Method | Route | Description |
|---|---|---|
| GET | `/reminders/list` | `?filter=due/upcoming/completed` |
| POST | `/reminders/save` | Create |
| PATCH | `/reminders/<id>` | Update/complete |
| DELETE | `/reminders/<id>` | Delete |

### PDF / Word Generation
| Method | Route | Description |
|---|---|---|
| POST | `/generate-pdf` | Proposal PDF (preview) |
| POST | `/generate-docx` | Proposal Word doc |
| POST | `/generate-co-pdf` | Change order PDF |
| POST | `/generate-job-cost` | Job cost sheet |

### Pipeline & Projects
| Method | Route | Description |
|---|---|---|
| GET | `/pipeline/list` | All proposals with stage info |
| GET | `/pipeline/stages` | Pipeline stages |
| PATCH | `/pipeline/move/<id>` | Move proposal to new stage |
| POST | `/projects/create` | New project |
| PATCH | `/projects/update/<id>` | Update project |

### Clients & Subcontractors
| Method | Route | Description |
|---|---|---|
| GET | `/clients/list` | List clients |
| POST | `/clients/save` | Save/update |
| DELETE | `/clients/delete/<id>` | Delete |
| GET/POST/DELETE | `/subs/*` | Same CRUD for subs |

### Bug Reports
| Method | Route | Description |
|---|---|---|
| POST | `/bugs/submit` | Submit (auth) |
| GET | `/bugs/list` | List (admin) |
| PATCH | `/bugs/<id>` | Update status/notes (admin) |

### Admin
| Method | Route | Description |
|---|---|---|
| GET | `/admin/users` | List all users |
| POST | `/admin/users` | Create (requires `full_name`, `username`, `password`; 6-char min) |
| PATCH | `/admin/users/<id>` | Update |
| GET | `/admin/logs` | Activity log |

### Tasks
| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/tasks/list` | yes | `?filter=open/completed`; respects visibility |
| POST | `/tasks/save` | yes | Create |
| PATCH | `/tasks/<id>` | yes | Update |
| DELETE | `/tasks/<id>` | yes | Delete |

### Other Routes
- `/boot/data` (GET, auth) — parallel server-side fetch of quotes + stages + proposals
- `/roadmap/*` — Roadmap CRUD (admin)
- `/notifications/*` — Notification system
- `/schedule/feed.ics` — ICS calendar feed
- `/settings/get`, `/settings/save` — App-level settings

### Backend Helpers

- `_safe_error(e, context)` — logs via `app.logger.exception`, returns generic `{'error': 'Internal error. Check logs.'}` with 500. Use in authed routes; NOT for 400/403 semantic responses or public routes.
- `_sb_eq(column, value)` — URL-safe PostgREST filter via `urllib.parse.quote`. Use instead of f-string interpolation in any `?col=eq.{var}` filter.
- `_owns_or_admin(record_created_by)` — null-safe ownership check; True for admin/dev unconditionally. Apply on update/delete routes.
- `set_security_headers` — allowlists `https://hdapp.up.railway.app` for CORS; allows iframe embedding for `/lead-form` + `/applicants-form` only (everything else gets `X-Frame-Options: DENY` + `frame-ancestors 'none'`). The same two form routes also get `https://maps.googleapis.com` / `https://maps.gstatic.com` whitelisted in CSP `script-src` + `connect-src` for Places — strictly scoped.
- `/send-email` rate-limit: 20 sends per rolling 24h per user. Audit log in `hd_email_log` — must exist in Supabase or the limiter silently fails open.
- `_users_opted_in(email_pref_key, default=False)` — returns active office users (admin/user/dev) opted in to a given email pref. **`default=True`** treats users with `notif_prefs.email[key]==null` as opted-in (used for `new_leads` and `new_applicants` so existing users get emails without re-saving prefs).
- `_send_lead_email(lead)` / `_send_applicant_email(applicant)` — Gmail OAuth (`GMAIL_TOKEN_JSON`), send from `admin@hdgrading.com`. Both send `multipart/alternative` (HTML + plain-text fallback).
- `_render_form_email_html(title, name, subtitle, rows, badges=None, free_text_label=None, free_text=None, cta_label, cta_url)` — returns inline-CSS branded HTML for form-submission notifications. Red header bar, 560px card, zebra-striped key/value rows, optional eligibility pills (green for true, gray for false), optional blockquote for free text, red CTA button. All inputs HTML-escaped via `html.escape`.
- `_normalize_phone(raw)` — returns `000-000-0000` or `None`. Strips non-digits; strips optional leading `1`. Used by both public submit routes.
- `_valid_email(raw)` — regex check (`^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$`), bounded at 254 chars. Stricter than HTML5 `type=email` (requires TLD).
- `_honeypot_tripped(payload)` — True if hidden `website_url` field was filled. Used by both public submit routes to short-circuit bot submissions with a fake `{ok:true}`.

### Sender info
The "From" name/email/phone on proposal PDFs and prefilled email templates **always reflects the logged-in user** (sourced from `hd_users.full_name/email/phone`). Settings → Account is the single place to update it. `hydrateSenderFromAccount()` re-derives the sender global from `window._userName/_userEmail/_userPhone`. The old shared `hd_sender` app setting was removed.

---

## Frontend (`index.html`) — Architecture

Single-file SPA — all CSS/JS/HTML in one file, ~170KB. No build step, no bundler, no TypeScript. Intentional.

### Panels
| Panel ID | Description |
|---|---|
| `panel-dashboard` | Dashboard — KPIs, weather, today's schedule, reminders, **Forms & Applicants** (combined leads + careers feed with red `QUOTE` / blue `CAREER` badges), recent activity |
| `panel-build` | Proposal builder with pricing options |
| `panel-project` | Single project detail |
| `panel-projects` | Projects list + pipeline (Kanban) |
| `panel-contacts` | Clients + Subcontractors tabs |
| `panel-schedule` | Calendar (day/3-day/week/month) |
| `panel-co` | Change order form |
| `panel-reports` | Reporting |
| `panel-settings` | Settings — materials, crew, equipment, company info |
| `panel-admin` | Admin — user management, activity log, archived items |
| `panel-bugs` | Bug reports |
| `panel-roadmap` | Product roadmap |
| `panel-tasks` | Tasks & Reminders (two-tab) |
| `panel-workorder` | Work order detail |

### Authentication Flow
1. Startup IIFE calls `/auth/check`
2. If authenticated: hide login, show app, call `boot()`, then `showAdminElements()`
3. If not: show login with canvas animation
4. `doLogin()` → POST `/auth/login` → on success: set `window._userRole`, call `boot()`, `showAdminElements()`
5. `doLogout()` → POST `/auth/logout` → `location.reload()`
6. Passwords are bcrypt-hashed server-side, stored in `hd_users.pin_hash`. Legacy SHA-256 hashes auto-migrate on next login.
7. Four roles: `admin`, `user`, `field`, `dev`.

### Role Visibility Model

- `dev` (Justin): sees everything — Users, Activity Log, Archived, Roadmap, Bug Reports.
- `admin` (Kyle): Dashboard, Projects, Pipeline, Build Proposal, Saved Docs, Schedule, Contacts, Change Orders, Work Orders, Analytics, Reports, Settings, Feedback panel, Admin → Company + Archived tabs. Hidden from admin: Users, Activity Log, Roadmap, Bug Reports. The Welcome modal copy deliberately does NOT mention what's hidden from admin.
- `user`: standard role; sees Feedback; no admin surfaces.
- `field`: reduced UI — Dashboard, Schedule, Work Orders, time tracking only. No pricing, no Feedback.

**Attribute rules:**
- `data-admin-hidden` — hidden from user/field, visible to admin+dev
- `data-dev-hidden` — hidden from everyone except dev
- `data-field-hidden` — hidden only from field

`showAdminElements()` removes these attributes based on `window._userRole`. The Roadmap panel is a top-level nav entry with `data-dev-hidden`, not a nested Admin tab. Admin tab list is `['company','users','activity','deleted']` — no `'roadmap'`.

### Global Variables (non-obvious ones)
- `window._userRole` — `'admin' | 'user' | 'field' | 'dev'`
- `MAT` (editable in Settings) vs `MAT_DEFAULT` (authoritative fallback, never corrupted by saved data)
- `jcProductivity` — NOT `productivity`. Using the wrong name causes ReferenceError that crashes `boot()`.
- `BID_LIBRARY` — 130 reusable line items; stored in `hd_bid_library` + localStorage cache. No "Load Defaults" button — fully user-managed.
- `CREWS` / `CREWS_DEFAULT` — 7 crews (Asphalt, Stone, Grading, Utility, Erosion Control, Striping, Signage). `_migrateLegacyTrades()` converts old trade strings (e.g. `b-storm-drain` → `b-utility`).

### Material System & Tonnage Formulas
Tonnage uses **two formulas** depending on material trade (resolved via `MAT_TRADE`):
- **Asphalt** (`b-asphalt`): `(SF / 9) × (lbs/2000) × depth_inches`. Density per SY per inch (115 lbs/SY/inch).
- **Stone / default**: `SF × (depth_inches / 12) × (lbs/2000)`. Density per cubic foot (150 lbs/CF).

The 4th arg `matType` to `tons()` is required — it determines which formula. Always use `getMatCost(type)` (resolves MAT → MAT_DEFAULT → bid library fallback), never `MAT[type]` directly, in calculations.

When Settings customization renames standard materials (e.g., "ABC" → "Heavy Duty ABC"), `_applyMatPrices` backfills `LBS` / `DRATE` / `DDEPTH` / `MAT_TRADE` from `MAT_DEFAULT` and `DEFAULT_BID_LIBRARY`.

### Frontend Helpers
- `_safeFetch(url, opts)` — fetch wrapper; throws on non-2xx with the server's `{error}` message. Use in every save/delete/update handler. Pattern: try/catch; toast in catch; do NOT close the modal on failure.
- `_wxSelectedDay` / `_selectWxDay(idx)` / `_wxVideoUrl(code, tod)` / `_wxTimeOfDay(data)` — dashboard weather widget. Hero uses `<video>` from `/static/wx/wx-*.mp4` (9 files mapping Open-meteo weather codes × time of day). Data from Open-meteo API at Concord, NC (`35.4088, -80.5795`), cached 30 min in `_weatherCache`.

---

## Known Issues & Important Notes

### ⚠️ File Editing
**Do NOT edit `index.html` with string concatenation or template literals of mixed quote styles** — has caused corruption repeatedly. Use:
- DOM API (`createElement`, `addEventListener`) for dynamic content
- Simple, consistent-quote-style string replacements
- Verify with `src.includes('functionName')` before pushing

`renderExtra()` and `renderBadgeList()` specifically MUST use DOM API, not innerHTML string building.

### ⚠️ boot() Error Handling
`boot()` is wrapped in try/catch in both doLogin and auth/check paths because `renderJCDefaults()` can throw if called before the DOM is ready. `showAdminElements()` must always run AFTER boot(), even if boot throws.

### ⚠️ Proposal Number in buildPayload()
`buildPayload()` must use `indexOf(lastSavedQuoteId)` in `linked_proposals` to find the correct proposal index (P1, P2, etc.). Do NOT use `linked_proposals.length + 1` — the current proposal is already in the array after saving.

### ⚠️ Striping / Lump-Sum Items
For striping items (`crew === 'b-striping'`), breakdown markup % must use `item.markup` directly, NOT `(bid-cost)/cost` — the latter produces astronomical numbers because `mat_cost` and `calcItemLabor()` both return 0 for striping.

### ⚠️ Admin Nav Attribute
`data-admin-hidden` + CSS `[data-admin-hidden]{display:none}`. Do NOT use inline `style.display=''` to show it — that clears the inline style but the CSS rule still hides it. Use `removeAttribute('data-admin-hidden')`.

### ⚠️ Flask Function Name Collisions
When adding a new route, grep for `def <function_name>` first. Flask refuses to boot if two routes share a function name (took down prod for 3 min on 2026-04-22).

### ⚠️ Public Form Conventions (`lead_form.html` + `applicants_form.html`)
- **Phone**: client mask auto-formats to `555-123-4567`. Server normalizes via `_normalize_phone`. Stored format in `hd_leads.phone` / `hd_applicants.phone` is always `000-000-0000`.
- **Email**: HTML `pattern` requires TLD; server re-validates via `_valid_email`.
- **Honeypot**: hidden `<input name="website_url">` on both forms. Filled → server returns fake `{ok:true}` and skips all DB writes / notifications / email. Log line: `[honeypot] /leads/submit rejected submission from <ip>`.
- **Google Places**: both forms fetch `/forms/config` on load and inject Maps JS only if `places_key` is non-empty. Fails closed to plain text — forms always work without the key. Key must be referrer-restricted in Google Cloud console.

---

## Bug Report Workflow

Bug reports live in `hd_bug_reports`. Prefer the Supabase MCP tool. Fallback PostgREST:
```bash
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/hd_bug_reports?select=*&order=submitted_at.desc" \
  -H "apikey: SERVICE_ROLE_KEY" -H "Authorization: Bearer SERVICE_ROLE_KEY"
```
Filter open only: append `&status=eq.Open`.

**Mark fixed (MANDATORY after any bug fix):**
```bash
curl -s -X PATCH "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/hd_bug_reports?id=eq.BUG_ID" \
  -H "apikey: SERVICE_ROLE_KEY" -H "Authorization: Bearer SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" -H "Prefer: return=minimal" \
  -d '{"status":"Fixed","admin_notes":"...","resolved_at":"ISO_TIMESTAMP"}'
```

---

## Pending / Future Work

- [ ] Phase tabs: multi-phase support partially built, not fully wired
- [ ] Badge Manager: dynamically inject CSS for custom badge colors
- [ ] Concrete items: allow custom `cy_per_lf` override per item
- [ ] Verify material costs populate correctly for all presets after Settings customization
- [ ] Replace schedule-panel weather canvas with video for visual consistency with dashboard
- [ ] Per-user ICS calendar feed tokens
- [ ] File upload magic-byte validation
- [ ] Full visual redesign rollout per `REDESIGN_*.md` docs
- [ ] Hardcoded stale pipeline stage lists in 5 reports/funnel places (deferred sweep)
