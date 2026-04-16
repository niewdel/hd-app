# HD Platform — Auth, Security, 2FA, RLS & UX Hardening

**Date:** 2026-04-16
**Owner:** Justin Ledwein (justin@hdgrading.com, dev)
**Goal:** Harden the HD Hauling & Grading internal web app before external users (starting with Kyle) are given logins. Ship in 5 batches, verifying each before the next.

---

## 1. Scope & constraints

### In scope (today)
1. **Login modernization** — enforce `@hdgrading.com` domain, username = email, show-password toggle, remove password-hint leak.
2. **Password security** — bcrypt hashing with zero-downtime SHA-256 fallback migration, min-length + complexity rules.
3. **Account protection** — per-IP and per-account rate limiting, lockout, audit logging.
4. **Forgot-password flow** — email magic-link with signed, one-use, 1h-expiry token via Gmail API.
5. **Email-code 2FA** — 6-digit code, 10-min expiry, single use, 3 sends/hour, required on every login for all users.
6. **Session hardening** — regenerate session ID on login + password change, HttpOnly/Secure/SameSite cookies, CSRF double-submit.
7. **CSP header** — strict policy with per-request nonce for inline scripts.
8. **Supabase RLS lockdown** — enable RLS on all 13 unprotected tables, add explicit policies matching current backend access patterns, revoke anon grants.
9. **UX/A11y sweep** — top ~10 high-impact fixes (focus visibility, contrast, keyboard nav, form labels, live regions, loading states).

### Out of scope (future)
- SMS/phone 2FA (Twilio dep, cost, SIM-swap risk).
- TOTP authenticator-app 2FA (can be added in Settings post-launch).
- Trusted-device "remember for 30 days" (adds complexity; revisit after v1 is stable).
- Full WCAG 2.1 AA audit (multi-day effort; today is triage).
- Supabase Auth migration (would require re-implementing everything around a different auth model).

### Hard constraints
- **Zero-downtime:** existing `justin@hdgrading.com` login must keep working throughout.
- **No local test infrastructure:** all validation happens post-deploy via Railway.
- **Single-file frontend:** every `index.html` edit must use the DOM API or carefully-escaped string replacements; previous corruption came from mixed quote styles.
- **Backend uses service role key:** the Flask app bypasses RLS. Enabling RLS is defense-in-depth against anon-key leaks, not a functional change.

### Known critical items surfaced during recon
- `app.py:17` — `SECRET_KEY` env var confirmed set on Railway; no action needed.
- `app.py:52` — passwords hashed with unsalted SHA-256. Must migrate.
- `app.py:149` — `password_hint` returned to the client on failed login — account-enumeration leak. Must remove.
- `app.py:124` — username-based login. Change to email with domain enforcement.
- 13 Supabase tables have RLS disabled (see Supabase advisor output in §6).
- `index.html:3624` — `roleLabel()` already handles `'dev'`; user's stale session is the visible symptom. Forcing re-login after migrations fixes this.

---

## 2. Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (SPA)                           │
│  index.html — login, 2FA entry, password reset, CSRF cookie    │
└────────────┬────────────────────────────────────────────────────┘
             │ HTTPS + session cookie + CSRF header
┌────────────▼────────────────────────────────────────────────────┐
│                     Flask backend (app.py)                      │
│                                                                 │
│  Auth layer:                                                    │
│    • /auth/login       domain check → bcrypt verify             │
│                        → issue 2FA code (email) → pending       │
│    • /auth/2fa/verify  consume code → issue session             │
│    • /auth/logout      invalidate session                       │
│    • /auth/forgot      issue signed reset token, email link     │
│    • /auth/reset       consume token → set new bcrypt hash      │
│    • /auth/change-password (authed)                             │
│                                                                 │
│  Rate limiter: in-memory token bucket keyed by IP+email         │
│  CSRF: double-submit cookie on POST/PATCH/DELETE                │
│  CSP nonce: per-request, injected into index.html               │
└────────────┬────────────────────────────────────────────────────┘
             │
    ┌────────┴─────────┐
    │                  │
┌───▼────────┐  ┌──────▼──────────────┐
│ Gmail API  │  │ Supabase (PostgREST)│
│ — 2FA mail │  │ — RLS enabled       │
│ — reset    │  │ — service_role from │
│ — notif    │  │   backend only      │
└────────────┘  └─────────────────────┘
```

### Key new modules
- `auth_email.py` — Gmail API wrapper. Sends 2FA codes, reset links, and piggybacks the existing notification emails through the same sender.
- `security.py` — password hashing (bcrypt + SHA-256 fallback), CSRF tokens, rate limiter, signed tokens (`itsdangerous.URLSafeTimedSerializer`).
- Changes to `app.py` — rewrite login flow, add 2FA routes, forgot-password routes, security headers, CSP nonce injection.
- Changes to `index.html` — login form rewrite (username → email, show/hide toggle, forgot link, 2FA screen, reset screen), CSRF fetch wrapper.

### Data-flow: first login for a migrated user
```
1. User visits /, unauthenticated → login screen
2. Enters email + password → POST /auth/login
3. Backend: domain check → user lookup → bcrypt verify
   (if SHA-256 match on fallback, rehash as bcrypt and save)
4. Generate 6-digit code, store (hashed) in hd_2fa_codes with 10m expiry
5. Email code via Gmail API to user.email
6. Return {pending_2fa: true, email_hint: "j***@hdgrading.com"}
7. Frontend shows 2FA entry screen
8. User enters code → POST /auth/2fa/verify
9. Backend: lookup hashed code by (user_id, code_hash), check not expired, not used
10. Mark code used, apply_user_session(), return {ok: true, ...}
11. SPA boots
```

### Data-flow: forgot password
```
1. User clicks "Forgot password?" on login
2. Enters email → POST /auth/forgot
3. Backend: if user exists, generate signed token (1h TTL, single-use),
   email link https://.../reset?token=XYZ. Always return 200 "check your email"
   (don't leak whether account exists).
4. User clicks link → frontend shows reset form
5. Enter new password twice → POST /auth/reset with token
6. Backend: verify signature, verify not-consumed, verify not-expired
7. Set new bcrypt hash, mark token consumed, invalidate other sessions for user
8. Redirect to login
```

---

## 3. Components & files

### New Python modules

**`security.py`** (~150 lines)
- `hash_password(pw: str) -> str` — bcrypt with cost 12.
- `verify_password(pw: str, stored: str) -> tuple[bool, bool]` — returns `(is_valid, needs_rehash)`. Detects legacy SHA-256 hashes by length (64 hex chars) and verifies; if valid, flags for rehash.
- `generate_2fa_code() -> str` — 6-digit numeric, URL-safe.
- `hash_2fa_code(code: str) -> str` — SHA-256 of code (these are single-use short-lived, so SHA is fine).
- `make_token_serializer()` — returns `URLSafeTimedSerializer(SECRET_KEY, salt='hd-reset-v1')` for reset tokens.
- `rate_limiter_check(key: str, limit: int, window_s: int) -> tuple[bool, int]` — returns `(allowed, retry_after_s)`. In-memory dict with timestamp list per key; no Redis dependency.
- `csrf_token_issue(session) -> str` — create token, store in session.
- `csrf_token_verify(session, token) -> bool` — constant-time compare.
- `mask_email(email: str) -> str` — returns `"j***@hdgrading.com"` for UI feedback.

**`auth_email.py`** (~100 lines)
- `get_gmail_service()` — lazy-initialized Gmail API client using refresh token from env.
- `send_2fa_code(to_email: str, code: str)` — sends branded 6-digit code email.
- `send_reset_link(to_email: str, reset_url: str)` — sends reset link email.
- `send_welcome_email(to_email: str, temp_password: str)` — sends onboarding email for new users.
- Graceful degradation: if Gmail creds missing, log + raise; auth routes return 503 with clear message.

### Database changes (`supabase-migration-2026-04-16.sql`)

```sql
-- 2FA codes table
create table hd_2fa_codes (
  id bigserial primary key,
  user_id bigint not null references hd_users(id) on delete cascade,
  code_hash text not null,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  ip_address text,
  created_at timestamptz default now()
);
create index idx_hd_2fa_codes_user on hd_2fa_codes(user_id, expires_at);

-- Password reset tokens (token itself is signed; table tracks consumption)
create table hd_password_resets (
  id bigserial primary key,
  user_id bigint not null references hd_users(id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  ip_address text,
  created_at timestamptz default now()
);
create index idx_hd_password_resets_token on hd_password_resets(token_hash);

-- Login attempt tracking for lockout
create table hd_login_attempts (
  id bigserial primary key,
  identifier text not null,        -- email or username
  ip_address text,
  success boolean not null,
  attempted_at timestamptz default now()
);
create index idx_hd_login_attempts_id on hd_login_attempts(identifier, attempted_at);

-- Add columns to hd_users
alter table hd_users add column if not exists failed_login_count int not null default 0;
alter table hd_users add column if not exists locked_until timestamptz;
alter table hd_users add column if not exists last_login_at timestamptz;
alter table hd_users add column if not exists password_updated_at timestamptz;

-- Drop password_hint column (leak fix; no longer used)
-- NOTE: only drop after Batch 1 ships and we verify no callers remain.
-- alter table hd_users drop column if exists password_hint;
```

### Backend changes (`app.py`)

- `/auth/login` rewritten:
  1. Strip + lowercase + validate domain (`@hdgrading.com`).
  2. Rate-limit by IP and by identifier.
  3. Look up user by `username` (which == email post-migration).
  4. `verify_password()` against `pin_hash`; rehash as bcrypt if legacy.
  5. If valid: generate + email 2FA code, return `{pending_2fa: true, email_hint}`.
  6. Set a short-lived `pending_2fa` session key (user_id + issued_at) in the Flask signed cookie. Not authenticated yet — no `authenticated=True` flag set until code is verified.
  7. On failure: log attempt, increment `failed_login_count`, lock if ≥10.
- `/auth/2fa/verify` new:
  1. Require `hd_pending_2fa` session key < 10 min old.
  2. Look up code by user_id + hash, check expiry, check not consumed.
  3. Mark consumed, call `apply_user_session()`, regenerate session ID.
- `/auth/forgot` new: always returns 200. If user exists, issues signed token + emails link.
- `/auth/reset` new: verifies token, updates password, bumps `password_updated_at`. `require_auth` extended to check session's `login_at >= user.password_updated_at`; any session issued before the last password change is rejected, forcing re-login on all devices.
- `/auth/change-password` updated: use bcrypt, invalidate other sessions.
- Every POST/PATCH/DELETE route wrapped by new `@require_csrf` decorator (except `/auth/login`, `/auth/forgot`, `/auth/reset`, public `/leads/submit`, public `/proposal/approve/*`).
- `set_security_headers()` extended with `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy`.
- New `/csrf/token` GET endpoint for frontend to fetch on boot.

### Frontend changes (`index.html`)

- **Login screen:**
  - Rename username field to "Email", type=email, placeholder "you@hdgrading.com".
  - Add show/hide password eye button (accessible, aria-label).
  - Add "Forgot password?" link below login button.
  - On submit: if response has `pending_2fa`, switch to 2FA screen.
- **New 2FA screen** (separate block, hidden by default):
  - 6-digit input (1 field, auto-submit on 6th digit).
  - "Code sent to j***@hdgrading.com. Didn't get it? [Resend]"
  - Resend rate-limited client-side (30s) + server-side (3/hr).
- **New forgot-password screen** — email input, "Send reset link" button.
- **New reset-password screen** — served at `/reset?token=...`, validates token client-side for UX, backend for truth.
- **CSRF wrapper** — override `window.fetch` for same-origin requests; read `X-CSRF-Token` from cookie, include as header on mutations.
- **Boot order** — fetch `/csrf/token` before any other call; retry-once logic.

---

## 4. Phased rollout — 5 batches

Each batch: ship → smoke test → move on. If any batch breaks prod, we roll back that batch's commit only.

### Batch 1 — Auth core hardening
**Goal:** Make the app safe to hand out externally.
**Files:** `app.py`, `security.py` (new), `index.html` (login form), `requirements.txt`.
**Ships:**
- bcrypt with SHA-256 fallback (`security.py`, `app.py` login + change-password).
- Remove `password_hint` from login response (`app.py:145,149`).
- Rate limiter + login-attempt logging (`security.py`, `app.py`).
- Show-password toggle (`index.html` login).
- Domain enforcement (`@hdgrading.com`) on `/auth/login`.
- Username-to-email migration SQL (`justin.ledwein` → `justin@hdgrading.com`).
- Set security headers (CSP, Referrer-Policy, Permissions-Policy).
- `requirements.txt`: add `bcrypt==4.2.0`. (`itsdangerous` ships with Flask; `google-api-python-client` already pinned at 2.114.0 so Gmail API ready for Batches 2-3.)

**Verification:**
- Justin logs out → logs in with `justin@hdgrading.com` + existing password.
- Failed login doesn't return a hint.
- Six rapid failed logins → 429.
- DevTools → password hash in DB is now bcrypt.
- CSP header present on all responses.

**Rollback:** single `git revert` of the batch commit.

### Batch 2 — Forgot password + session hardening
**Goal:** Self-service password recovery, session fixation fix, CSRF.
**Requires:** Gmail API creds (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`) on Railway.
**Files:** `app.py`, `auth_email.py` (new), `security.py`, `index.html` (forgot + reset screens, CSRF wrapper), `supabase-migration-2026-04-16.sql`.
**Ships:**
- `hd_password_resets` table.
- `/auth/forgot`, `/auth/reset` routes.
- Gmail sender module (`auth_email.py`).
- Session regeneration on login + password change (Flask implementation: `session.clear()` then re-populate; old signed cookie becomes invalid on next request because session contents differ).
- CSRF double-submit cookie + `@require_csrf` decorator on mutating routes.
- Frontend CSRF fetch wrapper.
- Frontend forgot-password + reset-password screens.

**Verification:**
- Forgot flow: enter email → receive link → click → set new password → log in.
- Old session invalidated after password change.
- POST without CSRF token returns 403.

**Rollback:** revert commit, drop `hd_password_resets` if needed.

### Batch 3 — Email 2FA
**Goal:** Every login requires a 6-digit email code.
**Requires:** Gmail creds from Batch 2 in place.
**Files:** `app.py`, `auth_email.py`, `index.html` (2FA screen), `supabase-migration-2026-04-16.sql`.
**Ships:**
- `hd_2fa_codes` table.
- `/auth/login` returns `pending_2fa` flag instead of full session.
- `/auth/2fa/verify` consumes code and issues session.
- `/auth/2fa/resend` with rate limit.
- Frontend 2FA screen + auto-submit on 6th digit.

**Verification:**
- Justin logs in → receives email → enters code → app boots.
- Wrong code → error, doesn't consume.
- Expired code (wait 10 min) → error.
- Resend button works; 3+ sends in an hour → 429.

**Rollback:** revert; keep table (drop later if needed).

### Batch 4 — Supabase RLS lockdown
**Goal:** Defense-in-depth; if anon key leaks, attacker sees nothing.
**Files:** `supabase-migration-2026-04-16-rls.sql` (separate migration, applied via Supabase MCP).
**Ships:**
- Enable RLS on: `hd_users`, `proposals`, `clients`, `pipeline_stages`, `hd_access_log`, `hd_settings`, `hd_notifications`, `hd_leads`, `hd_reminders`, `hd_tasks`, `hd_time_entries`, `change_orders`, `hd_feedback`.
- Policies:
  - `service_role`: bypass (implicit — Supabase always bypasses RLS for this role).
  - `authenticated`: **none granted** (frontend never calls Supabase directly).
  - `anon`: **none granted** (public data goes through Flask).
- Fix existing "Allow all for service key" policies on `hd_bug_reports`, `hd_roadmap`, `content_digests` — narrow to explicit service_role only.
- Verify via Supabase advisors — all ERROR-level lints cleared.

**Verification:**
- Post-migration advisor run → 0 errors.
- Smoke test every panel: dashboard, projects, clients, pipeline, tasks, schedule, admin, bugs, settings. Each must render + CRUD still works (backend uses service role → unaffected).
- Attempt direct anon call to `hd_users` → 401 or empty.

**Rollback:** Each `alter table X enable row level security` can be reversed with `disable`. Keep rollback SQL ready.

### Batch 5 — UX + A11y triage
**Goal:** Highest-impact polish. Not a full audit.
**Files:** `index.html`, small CSS additions.
**Ships (in priority order, stop when time runs out):**
1. Login page: visible focus ring on all inputs/buttons; remove `lowercase` force on email (it already has `type=email`); ensure error messages are in `aria-live="polite"`.
2. Global focus style: every interactive element gets a 2px red outline with offset when `:focus-visible`.
3. Skip link already exists (`index.html:1380`) — verify it's styled visible on focus.
4. Form labels: audit all `<input>`s lacking `<label>` or `aria-label` in the top-level panels. Add where missing.
5. Modal a11y: verify close buttons have `aria-label`; focus trapped on open; Escape closes.
6. Loading indicators: every `fetch()` path that takes >500ms gets a spinner + `aria-busy`.
7. Toast notifications: add `role="status"` + `aria-live="polite"`.
8. Color contrast: check any text below 4.5:1 (likely the `--dgray` variable) and bump.
9. Keyboard nav on Kanban: verify cards are reachable via Tab; add `role="button"` + `aria-label` where missing.
10. Mobile viewport: ensure no horizontal scroll on 360px width.

**Verification:**
- Keyboard-only walkthrough of login → dashboard → a project.
- Chrome Lighthouse a11y score comparison (pre/post).

**Rollback:** trivial; only CSS + semantic HTML additions.

---

## 5. Error handling & edge cases

- **Gmail API down:** 2FA + reset return 503 "Mail service unavailable. Please try again in a few minutes." User is not logged in, not locked out.
- **User has no email set:** should never happen post-migration (domain check guarantees it), but login blocks with "Account misconfigured, contact admin."
- **Lockout during legitimate use:** admin route to clear lockout (`POST /admin/users/<id>/unlock`).
- **Clock skew on 2FA expiry:** server time is authoritative; 30s grace on expiry comparison.
- **User deletes email before clicking reset link:** token still valid until TTL; on click, reset flow still works.
- **Two people request reset simultaneously:** each token is signed independently; both valid until consumed.
- **SPA reloads mid-2FA:** `pending_2fa` session key persists 10 min; user can continue where they left off.

---

## 6. Supabase RLS policies (draft)

For each of the 13 tables, the policy is identical: deny all by default, `service_role` bypasses (implicit). No grants to `anon` or `authenticated`.

```sql
-- Repeat for each of: hd_users, proposals, clients, pipeline_stages,
-- hd_access_log, hd_settings, hd_notifications, hd_leads, hd_reminders,
-- hd_tasks, hd_time_entries, change_orders, hd_feedback
alter table <TABLE> enable row level security;
revoke all on <TABLE> from anon, authenticated;
-- service_role bypasses RLS natively; no explicit grant needed for it
-- if we later want to surface this data directly, we add targeted policies.
```

For the 3 tables that already have `USING (true)` policies:
```sql
drop policy "Allow all for service key" on hd_bug_reports;
drop policy "Allow all for service key" on hd_roadmap;
drop policy "Allow authenticated access" on content_digests;
revoke all on hd_bug_reports, hd_roadmap, content_digests from anon, authenticated;
```

Public routes (`/proposal/view/*`, `/leads/submit`, `/p/*`) read/write via Flask backend, not direct Supabase — so they continue to work unchanged.

---

## 7. Rollback plan summary

| Batch | Rollback action |
|---|---|
| 1 | `git revert <sha>`; DB migration column adds are idempotent, safe to leave. Username rename SQL is one-liner to reverse. |
| 2 | `git revert <sha>`; leave `hd_password_resets` table in place (empty). |
| 3 | `git revert <sha>`; leave `hd_2fa_codes` table in place. |
| 4 | `alter table <t> disable row level security;` for each table. Rollback SQL is committed alongside migration. |
| 5 | `git revert <sha>`; UX changes are low-risk. |

Full session rollback: revert all commits in reverse order, apply RLS `disable` script.

---

## 8. Open items / dependencies

**Required from user:**
1. Gmail OAuth consent + refresh token for `admin@hdgrading.com`. (5-min guided process using Google Cloud Console → Enable Gmail API → OAuth client → local script to exchange auth code for refresh token.)
2. Railway env vars: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_SENDER_EMAIL=admin@hdgrading.com`.
3. Kyle's full name + email + role — for initial user creation.
4. Confirmation to run username migration (locks in `justin@hdgrading.com` as the login).
5. Current session re-login (to pick up the `dev` role in the UI).

**Confirmed:**
- `SECRET_KEY` set on Railway ✓
- `admin@hdgrading.com` will be created in Google Workspace ✓
- Email-only 2FA for v1; no phone/SMS ✓
- Only `justin.ledwein` (now `justin@hdgrading.com`) user remains; all others deleted ✓

---

## 9. Success criteria

- `justin@hdgrading.com` can log in with password + email code.
- Kyle can log in with password + email code.
- Forgot password works end-to-end.
- Supabase advisors report 0 ERROR-level security lints.
- Lighthouse a11y score on login page ≥90.
- No regressions: all existing panels render, CRUD still works.
- `docs/superpowers/specs/2026-04-16-auth-security-ux-design.md` and implementation plan committed.

---

## 10. Non-goals (stated explicitly to prevent scope creep today)

- Refactoring `index.html` into multiple files.
- Migrating to Supabase Auth.
- TOTP or SMS 2FA.
- Role-based UI redesign.
- Comprehensive WCAG 2.1 AA compliance.
- Any feature work unrelated to security/auth/a11y.
