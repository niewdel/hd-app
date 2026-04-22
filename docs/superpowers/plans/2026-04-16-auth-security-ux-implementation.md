# Auth / Security / UX Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship email-based login with domain enforcement, bcrypt hashing, email-code 2FA, forgot-password, CSRF + CSP, Supabase RLS lockdown, and top-priority accessibility fixes in one day across 5 verified batches.

**Architecture:** Flask backend hardens auth (bcrypt + rate limit + 2FA + CSRF); frontend gets new login/2FA/reset screens; Supabase gets RLS enabled on all public tables with backend continuing to use service_role; UX sweep hits 10 highest-impact a11y issues. See spec: `docs/superpowers/specs/2026-04-16-auth-security-ux-design.md`.

**Tech Stack:** Python 3.11 + Flask, vanilla JS/HTML, Supabase/PostgREST, Railway (auto-deploy from `main`), Gmail API (OAuth2 refresh token), bcrypt, itsdangerous.

**Verification model:** No automated tests in this codebase. Each task ends with a manual smoke test listing exact steps and expected outcomes against the live Railway URL after push.

**Deployment model:** Every commit to `main` auto-deploys to Railway (~60s). Commit often; verify after each push before proceeding to the next task. If a push breaks prod, `git revert <sha> && git push` is the rollback.

---

## File structure

### New files
- `security.py` — password hashing (bcrypt + SHA-256 legacy), CSRF helpers, rate limiter, signed tokens, 2FA code generator, email masking.
- `auth_email.py` — Gmail API sender for 2FA codes, reset links, optional welcome emails.
- `docs/superpowers/migrations/2026-04-16-auth-columns.sql` — adds columns and tables for lockout, 2FA, reset tokens, login attempts.
- `docs/superpowers/migrations/2026-04-16-rls-lockdown.sql` — enables RLS on all public tables, revokes anon/authenticated grants, drops over-permissive policies.
- `docs/superpowers/migrations/2026-04-16-rls-rollback.sql` — paired rollback script.

### Modified files
- `app.py` — rewrite `/auth/login` to 2-step (password → 2FA), add `/auth/2fa/*`, `/auth/forgot`, `/auth/reset`, `/csrf/token`, extend `require_auth` with `password_updated_at` check, apply `@require_csrf` to mutating routes, add CSP + extended security headers with per-request nonce.
- `index.html` — rewrite login screen (email field, show-password toggle, forgot link), add 2FA/forgot/reset screens, add CSRF fetch wrapper, a11y sweep fixes.
- `requirements.txt` — add `bcrypt==4.2.0`.

### Why this structure
`security.py` and `auth_email.py` isolate the new surface area so `app.py` stays readable. The migrations are versioned SQL files committed alongside the code for reproducibility + rollback. The single-file `index.html` is constrained by CLAUDE.md — we add new screens as new blocks and avoid touching unrelated code.

---

## Execution order & gating

| Batch | Gate before starting |
|---|---|
| 1 | None — all dependencies in place. |
| 2 | `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_SENDER_EMAIL` set in Railway. Batch 1 verified. |
| 3 | Batch 2 verified (Gmail send confirmed working). |
| 4 | Batch 3 verified. Full smoke test of all panels before starting. |
| 5 | Batch 4 verified; advisors clean. |

---

# Batch 1 — Auth core hardening

## Task 1.1: Add bcrypt to requirements and create `security.py`

**Files:**
- Modify: `requirements.txt`
- Create: `security.py`

- [ ] **Step 1: Add bcrypt to requirements**

Append to `requirements.txt`:

```
bcrypt==4.2.0
```

- [ ] **Step 2: Create `security.py` with password helpers**

```python
# security.py
import hashlib
import hmac
import secrets
import time
from typing import Tuple
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

BCRYPT_COST = 12

def _is_legacy_sha256(stored: str) -> bool:
    """Legacy SHA-256 hashes are exactly 64 hex chars."""
    return len(stored) == 64 and all(c in '0123456789abcdef' for c in stored.lower())

def hash_password(pw: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt(rounds=BCRYPT_COST)).decode('utf-8')

def verify_password(pw: str, stored: str) -> Tuple[bool, bool]:
    """Return (is_valid, needs_rehash). needs_rehash=True means stored is legacy SHA-256."""
    if not stored:
        return (False, False)
    if _is_legacy_sha256(stored):
        legacy = hashlib.sha256(pw.encode('utf-8')).hexdigest()
        return (hmac.compare_digest(legacy, stored), True)
    try:
        return (bcrypt.checkpw(pw.encode('utf-8'), stored.encode('utf-8')), False)
    except ValueError:
        return (False, False)

# Rate limiter: in-memory, per-process. Fine for single-gunicorn-worker Railway deployment.
_rate_buckets: dict[str, list[float]] = {}

def rate_limit_check(key: str, max_attempts: int, window_s: int) -> Tuple[bool, int]:
    """Return (allowed, retry_after_seconds). Records the attempt if allowed."""
    now = time.time()
    cutoff = now - window_s
    bucket = _rate_buckets.get(key, [])
    bucket = [t for t in bucket if t > cutoff]
    if len(bucket) >= max_attempts:
        retry = int(bucket[0] + window_s - now) + 1
        _rate_buckets[key] = bucket
        return (False, max(retry, 1))
    bucket.append(now)
    _rate_buckets[key] = bucket
    return (True, 0)

def rate_limit_record_failure(key: str, window_s: int):
    """Record a failure without checking. Used for enforcement on explicit failures."""
    now = time.time()
    bucket = _rate_buckets.get(key, [])
    bucket = [t for t in bucket if t > now - window_s]
    bucket.append(now)
    _rate_buckets[key] = bucket

# 2FA codes
def generate_2fa_code() -> str:
    """Return a 6-digit zero-padded code."""
    return f'{secrets.randbelow(1_000_000):06d}'

def hash_2fa_code(code: str) -> str:
    return hashlib.sha256(code.encode('utf-8')).hexdigest()

# CSRF
def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def verify_csrf(cookie_token: str, header_token: str) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)

# Reset tokens (signed, stateless body; consumption tracked in DB)
def make_reset_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt='hd-reset-v1')

def sign_reset_token(serializer: URLSafeTimedSerializer, user_id: int) -> str:
    return serializer.dumps({'uid': int(user_id)})

def verify_reset_token(serializer: URLSafeTimedSerializer, token: str, max_age_s: int):
    """Return user_id or raise BadSignature/SignatureExpired."""
    data = serializer.loads(token, max_age=max_age_s)
    return int(data['uid'])

# UX helpers
def mask_email(email: str) -> str:
    if '@' not in email:
        return email
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        masked = local[0] + '*'
    else:
        masked = local[0] + '***' + local[-1]
    return f'{masked}@{domain}'

def validate_hd_email(email: str) -> bool:
    email = (email or '').strip().lower()
    return email.endswith('@hdgrading.com') and '@' in email and len(email) > len('@hdgrading.com')
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt security.py
git commit -m "Add security module: bcrypt, rate limit, 2FA, CSRF, reset tokens"
```

- [ ] **Step 4: Manual verify (local)**

Run: `python3 -c "from security import hash_password, verify_password; h=hash_password('test'); print(verify_password('test', h)); print(verify_password('wrong', h))"`

Expected output: `(True, False)` then `(False, False)`.

---

## Task 1.2: Rewrite `/auth/login` to use bcrypt + domain enforcement + rate limit + no hint leak

**Files:**
- Modify: `app.py:121-153` (the existing `login()` route)

- [ ] **Step 1: Update imports at top of app.py**

Near the top of `app.py` (line 1-14), add after `import generate_report`:

```python
from security import (
    hash_password, verify_password,
    rate_limit_check, rate_limit_record_failure,
    validate_hd_email, mask_email,
)
```

- [ ] **Step 2: Keep the legacy `hash_password` function but make it an alias**

In `app.py`, find the existing `def hash_password(pw):` at line 52-53 and **delete it** — we now import `hash_password` from `security.py` which uses bcrypt. (The import in Step 1 shadows it.)

- [ ] **Step 3: Replace `/auth/login` route**

Replace lines 121-153 of `app.py` with:

```python
@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = str(data.get('username', data.get('email', ''))).strip().lower()
    password = str(data.get('password', data.get('pin', ''))).strip()

    # Domain enforcement
    if not validate_hd_email(email):
        return jsonify({'error': 'Please use your @hdgrading.com email'}), 401

    # Rate limit: 5 attempts per IP+email per 10 min
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
    rl_key = f'login:{ip}:{email}'
    allowed, retry = rate_limit_check(rl_key, max_attempts=5, window_s=600)
    if not allowed:
        return jsonify({'error': f'Too many attempts. Try again in {retry}s.'}), 429

    try:
        r = http.get(sb_url('hd_users', f'?username=eq.{email}&active=eq.true&limit=1'),
                     headers=sb_headers(), timeout=5)
        if r.status_code != 200:
            return jsonify({'error': 'Database connection error. Please try again.'}), 503
        rows = r.json()
        if not rows:
            # Generic error — no user enumeration
            log_access(email, '', 'login', False)
            return jsonify({'error': 'Incorrect email or password'}), 401
        user = rows[0]

        # Account lockout check
        locked_until = user.get('locked_until')
        if locked_until:
            try:
                from datetime import datetime as _dt
                lu = _dt.fromisoformat(locked_until.replace('Z', '+00:00'))
                if lu > _dt.utcnow().replace(tzinfo=lu.tzinfo):
                    return jsonify({'error': 'Account temporarily locked. Contact admin.'}), 423
            except Exception:
                pass

        valid, needs_rehash = verify_password(password, user.get('pin_hash', ''))
        if valid:
            # Rehash legacy SHA-256 to bcrypt on successful login
            if needs_rehash:
                try:
                    http.patch(sb_url('hd_users', f'?id=eq.{user["id"]}'),
                               headers={**sb_headers(), 'Prefer': 'return=minimal'},
                               json={'pin_hash': hash_password(password),
                                     'password_updated_at': datetime.utcnow().isoformat()},
                               timeout=5)
                except Exception:
                    pass
            # Reset failed counter on success
            try:
                http.patch(sb_url('hd_users', f'?id=eq.{user["id"]}'),
                           headers={**sb_headers(), 'Prefer': 'return=minimal'},
                           json={'failed_login_count': 0, 'locked_until': None,
                                 'last_login_at': datetime.utcnow().isoformat()},
                           timeout=5)
            except Exception:
                pass

            apply_user_session(user)
            import threading
            threading.Thread(target=log_access, args=(user['username'], user.get('full_name',''), 'login', True), daemon=True).start()
            return jsonify({'ok': True, 'role': session['role'], 'username': session['username'],
                            'full_name': session['full_name'],
                            'email': session['email'], 'phone': session['phone'],
                            'avatar_data': user.get('avatar_data', '')})
        else:
            # Increment failure counter; lock at 10
            try:
                new_count = int(user.get('failed_login_count') or 0) + 1
                update = {'failed_login_count': new_count}
                if new_count >= 10:
                    from datetime import datetime as _dt, timedelta as _td
                    update['locked_until'] = (_dt.utcnow() + _td(minutes=15)).isoformat()
                http.patch(sb_url('hd_users', f'?id=eq.{user["id"]}'),
                           headers={**sb_headers(), 'Prefer': 'return=minimal'},
                           json=update, timeout=5)
            except Exception:
                pass
            rate_limit_record_failure(rl_key, window_s=600)
            log_access(email, '', 'login', False)
            return jsonify({'error': 'Incorrect email or password'}), 401
    except http.exceptions.ConnectionError:
        return jsonify({'error': 'Cannot reach database. Check your connection.'}), 503
    except Exception as e:
        return jsonify({'error': f'Login error: {str(e)}'}), 500
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "Harden /auth/login: bcrypt verify, domain check, rate limit, no hint leak, lockout"
```

- [ ] **Step 5: Verify locally** that imports resolve:

Run: `python3 -c "import app; print(app.app.url_map)"`

Expected: prints route table, no ImportError.

---

## Task 1.3: Update `/auth/change-password` to use bcrypt

**Files:**
- Modify: `app.py:162-187`

- [ ] **Step 1: Replace the route body**

Replace lines 162-187 of `app.py` with:

```python
@app.route('/auth/change-password', methods=['POST'])
@require_auth
def change_password():
    data = request.get_json() or {}
    current = str(data.get('current_password', '')).strip()
    new_pw = str(data.get('new_password', '')).strip()
    if not current or not new_pw:
        return jsonify({'ok': False, 'error': 'Current and new password required'}), 400
    if len(new_pw) < 8:
        return jsonify({'ok': False, 'error': 'Password must be at least 8 characters'}), 400
    username = session.get('username', '')
    try:
        r = http.get(sb_url('hd_users', f'?username=eq.{username}&limit=1'), headers=sb_headers(), timeout=5)
        if r.status_code != 200 or not r.json():
            return jsonify({'ok': False, 'error': 'User not found'}), 404
        user = r.json()[0]
        valid, _ = verify_password(current, user.get('pin_hash', ''))
        if not valid:
            return jsonify({'ok': False, 'error': 'Current password is incorrect'}), 401
        update = {'pin_hash': hash_password(new_pw),
                  'password_updated_at': datetime.utcnow().isoformat()}
        http.patch(sb_url('hd_users', f'?username=eq.{username}'),
                   headers={**sb_headers(), 'Prefer': 'return=minimal'}, json=update, timeout=5)
        # Re-populate session to stamp new login_at; other sessions invalidated by password_updated_at check (added in Batch 2)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "Update /auth/change-password to bcrypt; raise min length to 8"
```

---

## Task 1.4: Add CSP + extended security headers

**Files:**
- Modify: `app.py:40-47` (the `set_security_headers` function)

- [ ] **Step 1: Replace `set_security_headers`**

Replace lines 40-47 of `app.py` with:

```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(self), camera=(), microphone=(), payment=()'
    # CSP: allow inline scripts/styles for now (single-file SPA uses many). Tighten with nonce in a later pass.
    # img-src includes data: for base64 avatars. connect-src includes supabase for direct calls (currently none, but harmless).
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://azznfkboiwayifhhcguz.supabase.co; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "Add CSP, Referrer-Policy, Permissions-Policy headers"
```

**Why `'unsafe-inline'` for script-src:** the single-file SPA has many inline `<script>` blocks and `onclick` handlers. Nonce-based CSP requires rewriting all of them, which would blow the time budget. This is still a meaningful improvement over no CSP and can be tightened in a follow-up pass.

---

## Task 1.5: Apply SQL migration — add user columns

**Files:**
- Create: `docs/superpowers/migrations/2026-04-16-auth-columns.sql`

- [ ] **Step 1: Write migration file**

Content:

```sql
-- 2026-04-16: Auth hardening columns
alter table hd_users add column if not exists failed_login_count int not null default 0;
alter table hd_users add column if not exists locked_until timestamptz;
alter table hd_users add column if not exists last_login_at timestamptz;
alter table hd_users add column if not exists password_updated_at timestamptz;

-- Login attempt log (append-only, for forensics)
create table if not exists hd_login_attempts (
  id bigserial primary key,
  identifier text not null,
  ip_address text,
  success boolean not null,
  attempted_at timestamptz default now()
);
create index if not exists idx_hd_login_attempts_id on hd_login_attempts(identifier, attempted_at desc);

-- 2FA codes
create table if not exists hd_2fa_codes (
  id bigserial primary key,
  user_id bigint not null references hd_users(id) on delete cascade,
  code_hash text not null,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  ip_address text,
  created_at timestamptz default now()
);
create index if not exists idx_hd_2fa_codes_user on hd_2fa_codes(user_id, expires_at desc);

-- Password reset tokens (token body is signed; table tracks consumption)
create table if not exists hd_password_resets (
  id bigserial primary key,
  user_id bigint not null references hd_users(id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  ip_address text,
  created_at timestamptz default now()
);
create index if not exists idx_hd_password_resets_token on hd_password_resets(token_hash);
```

- [ ] **Step 2: Apply via Supabase MCP**

Call `mcp__plugin_supabase_supabase__apply_migration` with:
- `project_id`: `azznfkboiwayifhhcguz`
- `name`: `auth_columns_2026_04_16`
- `query`: (contents of the file above)

- [ ] **Step 3: Verify tables exist**

Call `mcp__plugin_supabase_supabase__execute_sql`:

```sql
select column_name from information_schema.columns
where table_name='hd_users' and column_name in ('failed_login_count','locked_until','last_login_at','password_updated_at');
select table_name from information_schema.tables where table_name in ('hd_login_attempts','hd_2fa_codes','hd_password_resets');
```

Expected: 4 column rows + 3 table rows.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/migrations/2026-04-16-auth-columns.sql
git commit -m "DB migration: add auth hardening columns (failed_login, lockout, 2FA, resets)"
```

---

## Task 1.6: Username-to-email migration

**Files:**
- Apply SQL via Supabase MCP only (no file). Include the SQL in the commit message.

- [ ] **Step 1: Check current state**

Call `mcp__plugin_supabase_supabase__execute_sql`:

```sql
select id, username, email from hd_users;
```

Expected: one row — `justin.ledwein`, `justin@hdgrading.com`.

- [ ] **Step 2: Update username to match email**

Call `mcp__plugin_supabase_supabase__execute_sql`:

```sql
update hd_users set username = lower(email) where email ilike '%@hdgrading.com' and username <> lower(email);
select id, username, email from hd_users;
```

Expected: `username` is now `justin@hdgrading.com`.

- [ ] **Step 3: No code commit needed** — this is a data-only change. Note applied date in CLAUDE.md in the final session commit.

---

## Task 1.7: Login-screen updates — email field, show-password, remove stale hint UI

**Files:**
- Modify: `index.html:1380-1401` (the `#login-screen` block)
- Modify: `index.html:3795-3830` (the `doLogin()` function)

- [ ] **Step 1: Replace login form markup**

Find `<div id="login-screen">` at line 1383 and replace from that line through line 1401 (`</div><!-- APP -->`) with:

```html
<div id="login-screen">
  <canvas id="login-canvas"></canvas>
  <div class="login-body">
    <div class="login-card" id="login-card-main">
      <div class="login-eyebrow">
        <img src="/hd-no-background.png" alt="HD Hauling &amp; Grading" class="login-logo-img"/>
      </div>
      <div class="login-sub">Internal use only &nbsp;&middot;&nbsp; Authorized access required</div>
      <div class="login-rule"></div>
      <label for="login-username" class="sr-only">Email address</label>
      <input class="pin-input" id="login-username" type="email" placeholder="you@hdgrading.com" autocomplete="username" inputmode="email" spellcheck="false" onkeydown="if(event.key==='Enter')doLogin()"/>
      <div style="position:relative;">
        <label for="pin-inp" class="sr-only">Password</label>
        <input class="pin-input" id="pin-inp" type="password" placeholder="Password" autocomplete="current-password" onkeydown="if(event.key==='Enter')doLogin()" style="padding-right:44px;"/>
        <button type="button" id="pin-toggle" onclick="togglePinVisibility()" aria-label="Show password" aria-pressed="false" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:transparent;border:0;color:rgba(255,255,255,.55);cursor:pointer;padding:6px;">
          <svg id="pin-toggle-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
      </div>
      <button class="pin-btn" onclick="doLogin()">Access Tool</button>
      <div class="pin-err" id="pin-err" role="alert" aria-live="assertive"></div>
      <div style="margin-top:12px;text-align:center;">
        <a href="#" onclick="event.preventDefault();showForgotCard();" style="color:rgba(255,255,255,.65);font-size:12px;text-decoration:underline;">Forgot password?</a>
      </div>
    </div>

    <!-- 2FA CARD (hidden by default) -->
    <div class="login-card" id="login-card-2fa" style="display:none;">
      <div class="login-eyebrow">
        <img src="/hd-no-background.png" alt="HD Hauling &amp; Grading" class="login-logo-img"/>
      </div>
      <div class="login-sub">Verification required</div>
      <div class="login-rule"></div>
      <div id="login-2fa-msg" style="font-size:13px;color:rgba(255,255,255,.75);text-align:center;margin-bottom:10px;">Enter the 6-digit code we emailed you.</div>
      <label for="login-2fa-code" class="sr-only">6-digit code</label>
      <input class="pin-input" id="login-2fa-code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" placeholder="------" style="letter-spacing:6px;text-align:center;font-size:20px;" oninput="on2faInput(this)" onkeydown="if(event.key==='Enter')verify2fa()"/>
      <button class="pin-btn" onclick="verify2fa()">Verify</button>
      <div class="pin-err" id="login-2fa-err" role="alert" aria-live="assertive"></div>
      <div style="margin-top:12px;text-align:center;display:flex;gap:12px;justify-content:center;">
        <a href="#" onclick="event.preventDefault();resend2fa();" id="login-2fa-resend" style="color:rgba(255,255,255,.65);font-size:12px;text-decoration:underline;">Resend code</a>
        <a href="#" onclick="event.preventDefault();backToLogin();" style="color:rgba(255,255,255,.65);font-size:12px;text-decoration:underline;">Back</a>
      </div>
    </div>

    <!-- FORGOT CARD (hidden by default) -->
    <div class="login-card" id="login-card-forgot" style="display:none;">
      <div class="login-eyebrow">
        <img src="/hd-no-background.png" alt="HD Hauling &amp; Grading" class="login-logo-img"/>
      </div>
      <div class="login-sub">Reset your password</div>
      <div class="login-rule"></div>
      <div style="font-size:13px;color:rgba(255,255,255,.75);text-align:center;margin-bottom:10px;">Enter your @hdgrading.com email. We'll send a reset link.</div>
      <label for="login-forgot-email" class="sr-only">Email address</label>
      <input class="pin-input" id="login-forgot-email" type="email" placeholder="you@hdgrading.com" autocomplete="username" onkeydown="if(event.key==='Enter')submitForgot()"/>
      <button class="pin-btn" onclick="submitForgot()">Send reset link</button>
      <div class="pin-err" id="login-forgot-msg" role="status" aria-live="polite" style="color:rgba(255,255,255,.75);"></div>
      <div style="margin-top:12px;text-align:center;">
        <a href="#" onclick="event.preventDefault();backToLogin();" style="color:rgba(255,255,255,.65);font-size:12px;text-decoration:underline;">Back to login</a>
      </div>
    </div>
  </div>
  <div class="login-footer">Confidential &nbsp;&middot;&nbsp; Not for distribution</div>
</div><!-- APP -->
```

- [ ] **Step 2: Add the supporting JS functions**

Find `async function doLogin(){` around line 3795 and replace the entire function through its closing brace (~line 3830) with:

```js
function togglePinVisibility(){
  var inp=document.getElementById('pin-inp');
  var btn=document.getElementById('pin-toggle');
  if(!inp||!btn)return;
  var showing=inp.type==='text';
  inp.type=showing?'password':'text';
  btn.setAttribute('aria-pressed', showing?'false':'true');
  btn.setAttribute('aria-label', showing?'Show password':'Hide password');
}

function _showCard(id){
  ['login-card-main','login-card-2fa','login-card-forgot'].forEach(function(cid){
    var el=document.getElementById(cid);
    if(el)el.style.display=(cid===id?'':'none');
  });
}
function showForgotCard(){ _showCard('login-card-forgot'); setTimeout(function(){var e=document.getElementById('login-forgot-email');if(e)e.focus();},50); }
function backToLogin(){ _showCard('login-card-main'); setTimeout(function(){var e=document.getElementById('login-username');if(e)e.focus();},50); }
function on2faInput(inp){
  inp.value=(inp.value||'').replace(/\D/g,'').slice(0,6);
  if(inp.value.length===6) verify2fa();
}

async function doLogin(){
  var u=document.getElementById('login-username');
  var p=document.getElementById('pin-inp');
  var err=document.getElementById('pin-err');
  var username=(u&&u.value||'').trim().toLowerCase();
  var pin=p&&p.value||'';
  if(err){err.textContent='';err.style.color='';}
  if(!username){if(err)err.textContent='Enter your email.';return;}
  if(!pin){if(err)err.textContent='Enter your password.';return;}
  if(!/@hdgrading\.com$/.test(username)){if(err)err.textContent='Use your @hdgrading.com email.';return;}
  try{
    var r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username,password:pin})});
    var d=await r.json();
    if(r.ok&&d.pending_2fa){
      window._pending2faEmail=username;
      var msg=document.getElementById('login-2fa-msg');
      if(msg)msg.textContent='Code sent to '+(d.email_hint||username)+'.';
      _showCard('login-card-2fa');
      setTimeout(function(){var e=document.getElementById('login-2fa-code');if(e)e.focus();},50);
      return;
    }
    if(r.ok&&d.ok){
      window._userRole=d.role||'user';
      window._userName=d.full_name||'';
      window._userUsername=d.username||'';
      window._userEmail=d.email||'';
      window._userPhone=d.phone||'';
      window._userAvatar=d.avatar_data||'';
      try{ await boot(); }catch(e){ console.error('boot failed',e); }
      try{ showAdminElements(); }catch(e){}
      document.getElementById('login-screen').style.display='none';
      return;
    }
    var errMsg=d.error||'Incorrect email or password.';
    if(err){err.textContent=errMsg;}
  }catch(e){ if(err)err.textContent='Network error. Try again.'; }
}

async function verify2fa(){
  var c=document.getElementById('login-2fa-code');
  var err=document.getElementById('login-2fa-err');
  var code=(c&&c.value||'').trim();
  if(err)err.textContent='';
  if(!/^\d{6}$/.test(code)){if(err)err.textContent='Enter the 6-digit code.';return;}
  try{
    var r=await fetch('/auth/2fa/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:code})});
    var d=await r.json();
    if(r.ok&&d.ok){
      window._userRole=d.role||'user';
      window._userName=d.full_name||'';
      window._userUsername=d.username||'';
      window._userEmail=d.email||'';
      window._userPhone=d.phone||'';
      window._userAvatar=d.avatar_data||'';
      try{ await boot(); }catch(e){ console.error('boot failed',e); }
      try{ showAdminElements(); }catch(e){}
      document.getElementById('login-screen').style.display='none';
      return;
    }
    if(err)err.textContent=d.error||'Incorrect or expired code.';
  }catch(e){ if(err)err.textContent='Network error. Try again.'; }
}

async function resend2fa(){
  var msg=document.getElementById('login-2fa-msg');
  try{
    var r=await fetch('/auth/2fa/resend',{method:'POST',headers:{'Content-Type':'application/json'}});
    var d=await r.json();
    if(r.ok&&d.ok){ if(msg)msg.textContent='New code sent.'; }
    else { if(msg)msg.textContent=d.error||'Could not resend.'; }
  }catch(e){ if(msg)msg.textContent='Network error.'; }
}

async function submitForgot(){
  var e=document.getElementById('login-forgot-email');
  var m=document.getElementById('login-forgot-msg');
  var email=(e&&e.value||'').trim().toLowerCase();
  if(m)m.textContent='';
  if(!/@hdgrading\.com$/.test(email)){if(m)m.textContent='Use your @hdgrading.com email.';return;}
  try{
    var r=await fetch('/auth/forgot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:email})});
    if(m)m.textContent='If an account exists, a reset link has been sent.';
  }catch(err){ if(m)m.textContent='Network error. Try again.'; }
}
```

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "Login: email field, show-password toggle, 2FA/forgot card scaffolding"
```

---

## Task 1.8: Push Batch 1 and smoke-test

- [ ] **Step 1: Push**

```bash
git push origin main
```

- [ ] **Step 2: Wait ~90s for Railway deploy**

- [ ] **Step 3: Smoke test** at `https://hdapp.up.railway.app`

| Action | Expected |
|---|---|
| Load login page | New email field, password field, eye toggle, forgot link all visible |
| Click eye toggle | Password text becomes visible; icon + aria-label flip |
| Try `justin.ledwein` (no domain) | Error "Use your @hdgrading.com email" |
| Try `justin@hdgrading.com` + wrong password | "Incorrect email or password" — no hint leak |
| Try correct password (legacy SHA-256 hash) | Logs in. 2FA not wired yet in Batch 1, so should pass straight through. **Critical:** next successful verify in DB shows bcrypt hash (starts with `$2b$`). |
| DevTools → Network → response headers on any page | `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy` present |
| 6 rapid failed logins | 6th returns 429 "Too many attempts" |

- [ ] **Step 4: If anything fails, rollback**

```bash
git log --oneline -10
git revert <batch-1-sha-range>
git push origin main
```

---

# Batch 2 — Forgot password + session hardening + CSRF

**Gate:** Gmail creds confirmed in Railway env. Batch 1 verified.

## Task 2.1: Create `auth_email.py`

**Files:**
- Create: `auth_email.py`

- [ ] **Step 1: Write the module**

```python
# auth_email.py
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    GMAIL_OK = True
except ImportError:
    GMAIL_OK = False

_SENDER = os.environ.get('GMAIL_SENDER_EMAIL', 'admin@hdgrading.com')
_CLIENT_ID = os.environ.get('GMAIL_CLIENT_ID', '')
_CLIENT_SECRET = os.environ.get('GMAIL_CLIENT_SECRET', '')
_REFRESH_TOKEN = os.environ.get('GMAIL_REFRESH_TOKEN', '')
_TOKEN_URI = 'https://oauth2.googleapis.com/token'
_SCOPES = ['https://www.googleapis.com/auth/gmail.send']

_service = None

def _get_service():
    global _service
    if _service is not None:
        return _service
    if not GMAIL_OK:
        raise RuntimeError('Gmail libraries not installed')
    if not (_CLIENT_ID and _CLIENT_SECRET and _REFRESH_TOKEN):
        raise RuntimeError('Gmail credentials not configured')
    creds = Credentials(
        token=None,
        refresh_token=_REFRESH_TOKEN,
        token_uri=_TOKEN_URI,
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        scopes=_SCOPES,
    )
    _service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    return _service

def _send_raw(to_email: str, subject: str, html_body: str, text_body: str):
    msg = MIMEMultipart('alternative')
    msg['To'] = to_email
    msg['From'] = f'HD Hauling <{_SENDER}>'
    msg['Subject'] = subject
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
    service = _get_service()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()

def send_2fa_code(to_email: str, code: str):
    subject = f'HD Hauling verification code: {code}'
    text = f'Your HD Hauling login code is {code}. It expires in 10 minutes. If you didn\'t request this, ignore this email.'
    html = f'''
    <div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#111;">
      <h2 style="margin:0 0 8px;color:#CC0000;">HD Hauling & Grading</h2>
      <p>Use this code to finish signing in:</p>
      <p style="font-size:32px;letter-spacing:8px;font-weight:700;background:#f5f5f5;padding:16px;text-align:center;border-radius:6px;">{code}</p>
      <p style="color:#666;font-size:13px;">Expires in 10 minutes. If you didn\'t try to log in, you can ignore this email.</p>
    </div>'''
    _send_raw(to_email, subject, html, text)

def send_reset_link(to_email: str, reset_url: str):
    subject = 'Reset your HD Hauling password'
    text = f'Click this link to reset your password: {reset_url}\n\nExpires in 1 hour. If you didn\'t request this, ignore this email.'
    html = f'''
    <div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#111;">
      <h2 style="margin:0 0 8px;color:#CC0000;">HD Hauling & Grading</h2>
      <p>Click the link below to reset your password. Expires in 1 hour.</p>
      <p><a href="{reset_url}" style="display:inline-block;background:#CC0000;color:#fff;padding:12px 20px;text-decoration:none;border-radius:4px;font-weight:600;">Reset password</a></p>
      <p style="color:#666;font-size:13px;">If the button doesn\'t work, paste this into your browser:<br><span style="word-break:break-all;">{reset_url}</span></p>
      <p style="color:#666;font-size:13px;">If you didn\'t request a reset, ignore this email.</p>
    </div>'''
    _send_raw(to_email, subject, html, text)
```

- [ ] **Step 2: Commit**

```bash
git add auth_email.py
git commit -m "Add Gmail API sender module for 2FA + reset emails"
```

---

## Task 2.2: Add `/auth/forgot` and `/auth/reset` routes

**Files:**
- Modify: `app.py` — add imports and routes

- [ ] **Step 1: Update imports**

Add to the `from security import (...)` block at the top:

```python
from security import (
    hash_password, verify_password,
    rate_limit_check, rate_limit_record_failure,
    validate_hd_email, mask_email,
    make_reset_serializer, sign_reset_token, verify_reset_token,
    generate_2fa_code, hash_2fa_code,
    issue_csrf_token, verify_csrf,
)
from itsdangerous import BadSignature, SignatureExpired
import auth_email
```

- [ ] **Step 2: Add forgot/reset routes after `/auth/change-password`**

Append after the existing `/auth/change-password` function (~line 190):

```python
@app.route('/auth/forgot', methods=['POST'])
def auth_forgot():
    data = request.get_json() or {}
    email = str(data.get('email', '')).strip().lower()
    # Always return same response to prevent enumeration
    generic_ok = jsonify({'ok': True, 'message': 'If an account exists, a reset link has been sent.'})
    if not validate_hd_email(email):
        return generic_ok
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
    allowed, _ = rate_limit_check(f'forgot:{ip}:{email}', max_attempts=3, window_s=3600)
    if not allowed:
        return generic_ok
    try:
        r = http.get(sb_url('hd_users', f'?username=eq.{email}&active=eq.true&limit=1'), headers=sb_headers(), timeout=5)
        users = r.json() if r.status_code == 200 else []
        if not users:
            return generic_ok
        user = users[0]
        serializer = make_reset_serializer(app.secret_key)
        token = sign_reset_token(serializer, user['id'])
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        http.post(sb_url('hd_password_resets'), headers={**sb_headers(), 'Prefer': 'return=minimal'},
                  json={'user_id': user['id'], 'token_hash': token_hash,
                        'expires_at': expires_at, 'ip_address': ip}, timeout=5)
        base = request.host_url.rstrip('/')
        reset_url = f'{base}/reset?token={token}'
        try:
            auth_email.send_reset_link(email, reset_url)
        except Exception as e:
            print(f'[reset] email send failed: {e}')
        return generic_ok
    except Exception:
        return generic_ok

@app.route('/reset')
def reset_page():
    # Serves the SPA — it reads ?token from URL and shows the reset screen
    return app.send_static_file('index.html')

@app.route('/auth/reset', methods=['POST'])
def auth_reset():
    data = request.get_json() or {}
    token = str(data.get('token', '')).strip()
    new_pw = str(data.get('new_password', '')).strip()
    if not token or not new_pw:
        return jsonify({'ok': False, 'error': 'Missing token or password'}), 400
    if len(new_pw) < 8:
        return jsonify({'ok': False, 'error': 'Password must be at least 8 characters'}), 400
    try:
        serializer = make_reset_serializer(app.secret_key)
        user_id = verify_reset_token(serializer, token, max_age_s=3600)
    except SignatureExpired:
        return jsonify({'ok': False, 'error': 'Reset link expired. Request a new one.'}), 400
    except BadSignature:
        return jsonify({'ok': False, 'error': 'Invalid reset link.'}), 400
    try:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        # Check not consumed
        r = http.get(sb_url('hd_password_resets', f'?token_hash=eq.{token_hash}&limit=1'), headers=sb_headers(), timeout=5)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            return jsonify({'ok': False, 'error': 'Invalid reset link.'}), 400
        row = rows[0]
        if row.get('consumed_at'):
            return jsonify({'ok': False, 'error': 'Reset link already used.'}), 400
        # Update password + bump password_updated_at + consume token
        http.patch(sb_url('hd_users', f'?id=eq.{user_id}'),
                   headers={**sb_headers(), 'Prefer': 'return=minimal'},
                   json={'pin_hash': hash_password(new_pw),
                         'password_updated_at': datetime.utcnow().isoformat(),
                         'failed_login_count': 0, 'locked_until': None}, timeout=5)
        http.patch(sb_url('hd_password_resets', f'?id=eq.{row["id"]}'),
                   headers={**sb_headers(), 'Prefer': 'return=minimal'},
                   json={'consumed_at': datetime.utcnow().isoformat()}, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Reset error: {str(e)}'}), 500
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Add /auth/forgot and /auth/reset routes with signed tokens"
```

---

## Task 2.3: Add CSRF double-submit and `/csrf/token` endpoint

**Files:**
- Modify: `app.py`
- Modify: `index.html` — add CSRF fetch wrapper

- [ ] **Step 1: Add CSRF decorator and token endpoint to app.py**

Add after the `require_dev` function (around line 115):

```python
CSRF_EXEMPT_PATHS = {
    '/auth/login', '/auth/forgot', '/auth/reset', '/auth/2fa/verify', '/auth/2fa/resend',
    '/leads/submit', '/proposal/approve',  # prefix match below
    '/csrf/token',
}

def _is_csrf_exempt(path: str) -> bool:
    if path in CSRF_EXEMPT_PATHS:
        return True
    if path.startswith('/proposal/approve/'):
        return True
    return False

def require_csrf(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return f(*args, **kwargs)
        if _is_csrf_exempt(request.path):
            return f(*args, **kwargs)
        cookie = request.cookies.get('hd_csrf', '')
        header = request.headers.get('X-CSRF-Token', '')
        if not verify_csrf(cookie, header):
            return jsonify({'error': 'CSRF token invalid'}), 403
        return f(*args, **kwargs)
    return decorated

@app.route('/csrf/token')
def csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = issue_csrf_token()
        session['csrf_token'] = token
    resp = jsonify({'token': token})
    # Set cookie (not HttpOnly so JS can read for header)
    resp.set_cookie('hd_csrf', token, secure=True, httponly=False, samesite='Lax', max_age=8*3600)
    return resp
```

- [ ] **Step 2: Apply `@require_csrf` globally via before_request**

Add in `app.py` right after `set_security_headers`:

```python
@app.before_request
def csrf_guard():
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if _is_csrf_exempt(request.path):
        return
    # Only require CSRF for authenticated routes (public POSTs are exempted above)
    if not session.get('authenticated'):
        return
    cookie = request.cookies.get('hd_csrf', '')
    header = request.headers.get('X-CSRF-Token', '')
    if not verify_csrf(cookie, header):
        return jsonify({'error': 'CSRF token invalid'}), 403
```

This replaces the per-route decorator approach — simpler and catches everything.

- [ ] **Step 3: Add CSRF fetch wrapper at the top of index.html script section**

Find the first `<script>` block in `index.html` that defines app code. Near the very top of that block (before any fetch calls), add:

```js
// CSRF double-submit cookie: fetch token on boot and include in all mutating requests
(function(){
  var _origFetch = window.fetch.bind(window);
  function getCsrfFromCookie(){
    var m = document.cookie.match(/(?:^|; )hd_csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }
  window.fetch = function(url, opts){
    opts = opts || {};
    var method = (opts.method || 'GET').toUpperCase();
    if(method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS'){
      var token = getCsrfFromCookie();
      if(token){
        opts.headers = opts.headers || {};
        // Don't overwrite if caller already set it
        if(!opts.headers['X-CSRF-Token'] && !opts.headers['x-csrf-token']){
          opts.headers['X-CSRF-Token'] = token;
        }
      }
    }
    return _origFetch(url, opts);
  };
  // Fetch CSRF token early (best-effort; login flow doesn't need it)
  try{ fetch('/csrf/token', {credentials:'same-origin'}); }catch(e){}
})();
```

- [ ] **Step 4: Commit and push**

```bash
git add app.py index.html
git commit -m "Add CSRF double-submit: /csrf/token, before_request guard, fetch wrapper"
git push origin main
```

- [ ] **Step 5: Smoke test**

| Action | Expected |
|---|---|
| Load site | `hd_csrf` cookie set |
| Log in | Still works (login is exempt) |
| Save a proposal | Works (fetch wrapper includes header) |
| Manually POST to /quotes/save without header (via curl) | 403 "CSRF token invalid" |

---

## Task 2.4: Extend `require_auth` with `password_updated_at` check

**Files:**
- Modify: `app.py` — update `require_auth` decorator and `apply_user_session`

- [ ] **Step 1: Stamp login time in session**

Find `apply_user_session` (around line 67) and replace:

```python
def apply_user_session(user):
    session.clear()  # session regeneration: invalidates any pre-existing cookie contents
    session['authenticated'] = True
    session['username'] = user.get('username', '')
    session['full_name'] = user.get('full_name', user.get('username', ''))
    session['role'] = user.get('role', 'user')
    session['email'] = user.get('email', '')
    session['phone'] = user.get('phone', '')
    session['login_at'] = datetime.utcnow().isoformat()
    session.permanent = True
```

- [ ] **Step 2: Update `require_auth` to check password_updated_at**

Replace `require_auth` (around line 89):

```python
def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        # Invalidate sessions older than the user's last password change
        login_at = session.get('login_at')
        username = session.get('username', '')
        if login_at and username:
            try:
                r = http.get(sb_url('hd_users', f'?username=eq.{username}&select=password_updated_at&limit=1'),
                             headers=sb_headers(), timeout=2)
                if r.status_code == 200 and r.json():
                    pwd_at = r.json()[0].get('password_updated_at')
                    if pwd_at and pwd_at > login_at:
                        session.clear()
                        return jsonify({'error': 'Session invalidated. Please sign in again.'}), 401
            except Exception:
                pass  # fail open on network error — don't lock users out on a blip
        return f(*args, **kwargs)
    return decorated
```

- [ ] **Step 3: Commit and push**

```bash
git add app.py
git commit -m "Session hardening: regenerate on login, invalidate on password change"
git push origin main
```

- [ ] **Step 4: Smoke test**

| Action | Expected |
|---|---|
| Log in in Browser A | Works |
| From Browser B, change password | Works |
| Browser A: make any authenticated request | 401 "Session invalidated" |

---

## Task 2.5: Reset-password SPA screen

**Files:**
- Modify: `index.html` — add reset-password card to login-body, and logic to show it when `?token=` is in URL

- [ ] **Step 1: Add reset card HTML**

Inside `<div class="login-body">`, after the forgot card, add:

```html
<!-- RESET CARD -->
<div class="login-card" id="login-card-reset" style="display:none;">
  <div class="login-eyebrow">
    <img src="/hd-no-background.png" alt="HD Hauling &amp; Grading" class="login-logo-img"/>
  </div>
  <div class="login-sub">Choose a new password</div>
  <div class="login-rule"></div>
  <label for="reset-pw1" class="sr-only">New password</label>
  <input class="pin-input" id="reset-pw1" type="password" placeholder="New password (min 8)" autocomplete="new-password"/>
  <label for="reset-pw2" class="sr-only">Confirm password</label>
  <input class="pin-input" id="reset-pw2" type="password" placeholder="Confirm new password" autocomplete="new-password" onkeydown="if(event.key==='Enter')submitReset()"/>
  <button class="pin-btn" onclick="submitReset()">Set new password</button>
  <div class="pin-err" id="reset-err" role="alert" aria-live="assertive"></div>
</div>
```

- [ ] **Step 2: Add reset logic near the other login functions**

```js
async function submitReset(){
  var t = new URLSearchParams(location.search).get('token') || '';
  var a = document.getElementById('reset-pw1');
  var b = document.getElementById('reset-pw2');
  var err = document.getElementById('reset-err');
  if(err)err.textContent='';
  var pw1 = a && a.value || '';
  var pw2 = b && b.value || '';
  if(pw1.length < 8){if(err)err.textContent='Password must be at least 8 characters.';return;}
  if(pw1 !== pw2){if(err)err.textContent='Passwords don\'t match.';return;}
  try{
    var r = await fetch('/auth/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:t, new_password:pw1})});
    var d = await r.json();
    if(r.ok && d.ok){
      if(err){err.textContent='Password updated. You can now sign in.';err.style.color='rgba(200,230,200,.9)';}
      setTimeout(function(){ location.href='/'; }, 1400);
      return;
    }
    if(err)err.textContent = d.error || 'Could not reset password.';
  }catch(e){ if(err)err.textContent='Network error. Try again.'; }
}

// Show reset card if arriving with ?token=
(function(){
  var t = new URLSearchParams(location.search).get('token');
  if(t){
    // Wait for DOM ready
    document.addEventListener('DOMContentLoaded', function(){
      _showCard('login-card-reset');
      var e=document.getElementById('reset-pw1'); if(e) e.focus();
    });
  }
})();
```

- [ ] **Step 3: Commit and push**

```bash
git add index.html
git commit -m "Reset-password screen: /reset?token= flow end-to-end"
git push origin main
```

- [ ] **Step 4: End-to-end smoke test**

| Action | Expected |
|---|---|
| Click "Forgot password?" on login | Forgot card shows |
| Enter `justin@hdgrading.com` | Generic success message |
| Check inbox at admin@hdgrading.com's SMTP logs (or recipient's inbox) | Email with reset link arrives within 30s |
| Click link | App loads with reset card |
| Set password < 8 chars | Error |
| Set password 8+ chars mismatched | Error |
| Set matching 8+ chars | Success, auto-redirect to login |
| Log in with new password | Works |
| Click link a second time | "Reset link already used" |

---

# Batch 3 — Email 2FA

## Task 3.1: Add 2FA routes

**Files:**
- Modify: `app.py` — update `/auth/login` to emit `pending_2fa`, add `/auth/2fa/verify` and `/auth/2fa/resend`

- [ ] **Step 1: Modify `/auth/login` success path**

In the success branch of `/auth/login` (inside `if valid:`), **replace** the `apply_user_session(user)` + return-with-session block with this pending-2FA flow. Find the block that looks like:

```python
apply_user_session(user)
import threading
threading.Thread(target=log_access, ...).start()
return jsonify({'ok': True, 'role': session['role'], ...})
```

Replace with:

```python
# Generate 2FA code, store hashed, send via email
code = generate_2fa_code()
code_hash = hash_2fa_code(code)
expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
try:
    http.post(sb_url('hd_2fa_codes'), headers={**sb_headers(), 'Prefer': 'return=minimal'},
              json={'user_id': user['id'], 'code_hash': code_hash,
                    'expires_at': expires_at, 'ip_address': ip}, timeout=5)
    auth_email.send_2fa_code(email, code)
except Exception as e:
    return jsonify({'error': f'Could not send verification code: {str(e)}'}), 503

# Stash pending state in signed session (not authenticated yet)
session.clear()
session['pending_2fa_user_id'] = int(user['id'])
session['pending_2fa_email'] = email
session['pending_2fa_issued_at'] = datetime.utcnow().isoformat()
session.permanent = True
# (success log written after 2FA completes)
return jsonify({'ok': True, 'pending_2fa': True, 'email_hint': mask_email(email)})
```

- [ ] **Step 2: Add 2FA verify + resend routes after `/auth/reset`**

```python
@app.route('/auth/2fa/verify', methods=['POST'])
def auth_2fa_verify():
    data = request.get_json() or {}
    code = str(data.get('code', '')).strip()
    user_id = session.get('pending_2fa_user_id')
    issued_at = session.get('pending_2fa_issued_at')
    if not user_id or not issued_at:
        return jsonify({'error': 'No pending verification. Start over.'}), 400
    # Pending state must be <10 min old
    try:
        ia = datetime.fromisoformat(issued_at)
        if datetime.utcnow() - ia > timedelta(minutes=10):
            session.clear()
            return jsonify({'error': 'Verification window expired. Sign in again.'}), 400
    except Exception:
        session.clear()
        return jsonify({'error': 'Invalid session. Sign in again.'}), 400
    if not code or not code.isdigit() or len(code) != 6:
        return jsonify({'error': 'Enter the 6-digit code.'}), 400
    try:
        ch = hash_2fa_code(code)
        r = http.get(sb_url('hd_2fa_codes',
                     f'?user_id=eq.{user_id}&code_hash=eq.{ch}&consumed_at=is.null&order=created_at.desc&limit=1'),
                     headers=sb_headers(), timeout=5)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            return jsonify({'error': 'Incorrect or expired code.'}), 401
        row = rows[0]
        expires_at = row.get('expires_at', '')
        try:
            ea = datetime.fromisoformat(expires_at.replace('Z', '+00:00')).replace(tzinfo=None)
            if datetime.utcnow() > ea:
                return jsonify({'error': 'Code expired. Resend a new one.'}), 401
        except Exception:
            return jsonify({'error': 'Code validation error.'}), 500
        # Mark consumed
        http.patch(sb_url('hd_2fa_codes', f'?id=eq.{row["id"]}'),
                   headers={**sb_headers(), 'Prefer': 'return=minimal'},
                   json={'consumed_at': datetime.utcnow().isoformat()}, timeout=5)
        # Fetch full user and apply session
        ur = http.get(sb_url('hd_users', f'?id=eq.{user_id}&limit=1'), headers=sb_headers(), timeout=5)
        users = ur.json() if ur.status_code == 200 else []
        if not users:
            session.clear()
            return jsonify({'error': 'Account not found.'}), 404
        user = users[0]
        apply_user_session(user)
        import threading
        threading.Thread(target=log_access, args=(user['username'], user.get('full_name',''), 'login', True), daemon=True).start()
        return jsonify({'ok': True, 'role': session['role'], 'username': session['username'],
                        'full_name': session['full_name'], 'email': session['email'],
                        'phone': session['phone'], 'avatar_data': user.get('avatar_data', '')})
    except Exception as e:
        return jsonify({'error': f'2FA error: {str(e)}'}), 500

@app.route('/auth/2fa/resend', methods=['POST'])
def auth_2fa_resend():
    user_id = session.get('pending_2fa_user_id')
    email = session.get('pending_2fa_email', '')
    if not user_id or not email:
        return jsonify({'error': 'No pending verification.'}), 400
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
    allowed, retry = rate_limit_check(f'2fa-resend:{user_id}', max_attempts=3, window_s=3600)
    if not allowed:
        return jsonify({'error': f'Too many resends. Try again in {retry}s.'}), 429
    code = generate_2fa_code()
    try:
        http.post(sb_url('hd_2fa_codes'), headers={**sb_headers(), 'Prefer': 'return=minimal'},
                  json={'user_id': user_id, 'code_hash': hash_2fa_code(code),
                        'expires_at': (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
                        'ip_address': ip}, timeout=5)
        auth_email.send_2fa_code(email, code)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': f'Could not send code: {str(e)}'}), 503
```

- [ ] **Step 3: Commit and push**

```bash
git add app.py
git commit -m "Email 2FA: /auth/login emits pending_2fa, /auth/2fa/verify + /resend"
git push origin main
```

- [ ] **Step 4: Smoke test**

| Action | Expected |
|---|---|
| Log in with correct password | No full session yet; 2FA screen shows with masked email |
| Check inbox | 6-digit code arrives within 30s |
| Enter code | App boots fully |
| Try same code again (log out, re-login, reuse old) | "Incorrect or expired code" |
| Resend button | New code arrives |
| 4 resends in a row | 4th returns 429 |

Frontend already wired in Task 1.7 — no index.html changes needed.

---

# Batch 4 — Supabase RLS lockdown

## Task 4.1: Write the RLS migration

**Files:**
- Create: `docs/superpowers/migrations/2026-04-16-rls-lockdown.sql`
- Create: `docs/superpowers/migrations/2026-04-16-rls-rollback.sql`

- [ ] **Step 1: Write lockdown SQL**

```sql
-- 2026-04-16: Enable RLS on all public tables and revoke anon/authenticated grants.
-- Backend uses service_role which bypasses RLS natively — no policies needed.
-- Defense-in-depth: if anon key leaks, attackers see nothing.

-- Drop existing over-permissive policies
drop policy if exists "Allow all for service key" on hd_bug_reports;
drop policy if exists "Allow all for service key" on hd_roadmap;
drop policy if exists "Allow authenticated access" on content_digests;

-- Enable RLS on all public tables
alter table hd_users enable row level security;
alter table proposals enable row level security;
alter table clients enable row level security;
alter table pipeline_stages enable row level security;
alter table hd_access_log enable row level security;
alter table hd_settings enable row level security;
alter table hd_notifications enable row level security;
alter table hd_leads enable row level security;
alter table hd_reminders enable row level security;
alter table hd_tasks enable row level security;
alter table hd_time_entries enable row level security;
alter table change_orders enable row level security;
alter table hd_feedback enable row level security;
alter table hd_bug_reports enable row level security;
alter table hd_roadmap enable row level security;
alter table hd_login_attempts enable row level security;
alter table hd_2fa_codes enable row level security;
alter table hd_password_resets enable row level security;

-- Revoke all direct grants from anon/authenticated — backend only
revoke all on hd_users from anon, authenticated;
revoke all on proposals from anon, authenticated;
revoke all on clients from anon, authenticated;
revoke all on pipeline_stages from anon, authenticated;
revoke all on hd_access_log from anon, authenticated;
revoke all on hd_settings from anon, authenticated;
revoke all on hd_notifications from anon, authenticated;
revoke all on hd_leads from anon, authenticated;
revoke all on hd_reminders from anon, authenticated;
revoke all on hd_tasks from anon, authenticated;
revoke all on hd_time_entries from anon, authenticated;
revoke all on change_orders from anon, authenticated;
revoke all on hd_feedback from anon, authenticated;
revoke all on hd_bug_reports from anon, authenticated;
revoke all on hd_roadmap from anon, authenticated;
revoke all on hd_login_attempts from anon, authenticated;
revoke all on hd_2fa_codes from anon, authenticated;
revoke all on hd_password_resets from anon, authenticated;
```

- [ ] **Step 2: Write rollback SQL**

```sql
-- Rollback of 2026-04-16 RLS lockdown
alter table hd_users disable row level security;
alter table proposals disable row level security;
alter table clients disable row level security;
alter table pipeline_stages disable row level security;
alter table hd_access_log disable row level security;
alter table hd_settings disable row level security;
alter table hd_notifications disable row level security;
alter table hd_leads disable row level security;
alter table hd_reminders disable row level security;
alter table hd_tasks disable row level security;
alter table hd_time_entries disable row level security;
alter table change_orders disable row level security;
alter table hd_feedback disable row level security;
alter table hd_bug_reports disable row level security;
alter table hd_roadmap disable row level security;
alter table hd_login_attempts disable row level security;
alter table hd_2fa_codes disable row level security;
alter table hd_password_resets disable row level security;

-- Restore default grants (Supabase's standard)
grant all on hd_users, proposals, clients, pipeline_stages, hd_access_log,
  hd_settings, hd_notifications, hd_leads, hd_reminders, hd_tasks,
  hd_time_entries, change_orders, hd_feedback, hd_bug_reports, hd_roadmap,
  hd_login_attempts, hd_2fa_codes, hd_password_resets to anon, authenticated;
```

- [ ] **Step 3: Commit the migration files** (not yet applied)

```bash
git add docs/superpowers/migrations/2026-04-16-rls-lockdown.sql docs/superpowers/migrations/2026-04-16-rls-rollback.sql
git commit -m "RLS migration files: lockdown + rollback"
```

---

## Task 4.2: Apply RLS migration

- [ ] **Step 1: Snapshot advisor count**

Call `mcp__plugin_supabase_supabase__get_advisors` with `type: security`. Save list of ERROR-level `rls_disabled_in_public` items — should be 13.

- [ ] **Step 2: Apply migration**

Call `mcp__plugin_supabase_supabase__apply_migration`:
- `project_id`: `azznfkboiwayifhhcguz`
- `name`: `rls_lockdown_2026_04_16`
- `query`: (contents of lockdown SQL)

- [ ] **Step 3: Verify advisors are clean**

Call `mcp__plugin_supabase_supabase__get_advisors` again. Expected: 0 `rls_disabled_in_public` errors.

- [ ] **Step 4: Verify tables show RLS enabled**

Call `mcp__plugin_supabase_supabase__list_tables` with `schemas: ["public"]`. Every table should have `rls_enabled: true`.

---

## Task 4.3: Full regression smoke test

- [ ] **Step 1: Log in to live site** as `justin@hdgrading.com`.

- [ ] **Step 2: Walk every panel** and verify CRUD works:

| Panel | Test |
|---|---|
| Dashboard | Loads without errors, KPIs render |
| Build Proposal | Create a test proposal, save it, list shows it |
| Projects list | Renders, pipeline shows cards |
| Project detail | Opens, edits save |
| Clients | List, add, edit, delete |
| Schedule | Calendar loads |
| Tasks | Create, complete, delete a task |
| Change Orders | Create one |
| Reports | Render |
| Settings | All tabs load, can edit materials |
| Admin → Users | List shows you; can create + delete |
| Admin → Activity | Access log renders |
| Bug Reports | List shows bugs; can mark fixed |
| Roadmap | Items render |

If any panel throws — rollback immediately:

Call `mcp__plugin_supabase_supabase__apply_migration` with the rollback SQL.

- [ ] **Step 3: If all pass, delete your test proposal** and move on.

---

# Batch 5 — UX / A11y top-10 sweep

## Task 5.1: Add a visible focus ring globally

**Files:**
- Modify: `index.html` — global CSS block

- [ ] **Step 1: Add focus style to the main CSS**

Find the first `<style>` block and add near the top:

```css
*:focus-visible {
  outline: 2px solid #CC0000;
  outline-offset: 2px;
  border-radius: 2px;
}
.skip-link {
  position: absolute; left: -9999px; top: 0;
  background: #111; color: #fff; padding: 12px 16px; z-index: 9999;
  text-decoration: none;
}
.skip-link:focus { left: 8px; top: 8px; }
```

- [ ] **Step 2: Commit + push**

```bash
git add index.html
git commit -m "A11y: visible focus ring + skip-link focus style"
git push origin main
```

- [ ] **Step 3: Verify** — Tab through login page. Every input/button shows red outline when focused. Press Tab once on page load → "Skip to main content" appears top-left.

---

## Task 5.2: Live region for toasts and error messages

**Files:**
- Modify: `index.html` — find the toast container

- [ ] **Step 1: Add `aria-live` to the toast container**

Find `id="toast-container"` (or equivalent — grep for it). Ensure the container has:

```html
<div id="toast-container" role="status" aria-live="polite" aria-atomic="false"></div>
```

If a `#toast-container` doesn't exist, locate the function that injects toasts and add `role="status"` + `aria-live="polite"` to the created toast element.

- [ ] **Step 2: Verify + commit**

```bash
git add index.html
git commit -m "A11y: aria-live polite on toast container"
git push origin main
```

---

## Task 5.3: Form labels audit — login, profile, admin edit-user

**Files:**
- Modify: `index.html`

- [ ] **Step 1: For each input listed below, verify `<label for>` or `aria-label` exists**

Use Grep to find inputs lacking labels:

```
grep -nE '<input[^>]*>' index.html | head -60
```

Key spots:
- Login inputs — already labeled via `sr-only`.
- Admin → edit user modal: check `edit-pin`, `edit-email`, `edit-phone`, `edit-full-name` all have labels.
- Password-change modal.
- Profile modal.

- [ ] **Step 2: For any missing, add** `aria-label="..."` inline.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "A11y: ensure all inputs have labels or aria-label"
```

---

## Task 5.4: Loading + aria-busy on long fetches

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Add aria-busy helper**

Near the top of the script block:

```js
function setAriaBusy(el, busy){
  if(!el) return;
  if(busy) el.setAttribute('aria-busy','true');
  else el.removeAttribute('aria-busy');
}
```

- [ ] **Step 2: Wrap the three slowest fetch paths** (`/boot/data`, `/generate-pdf`, `/clients/list`) with `setAriaBusy` around their button or panel root.

Example for the boot panel:

```js
// inside boot()
var root=document.getElementById('panel-dashboard');
setAriaBusy(root, true);
try{ /* existing */ } finally { setAriaBusy(root, false); }
```

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "A11y: aria-busy on long-running operations"
```

---

## Task 5.5: Contrast + keyboard-nav pass

**Files:**
- Modify: `index.html` — CSS tweaks

- [ ] **Step 1: Grep for `--dgray` usage**

Use Grep to list all uses of `var(--dgray)`. Anywhere it's used on a light background for small text, it will fail 4.5:1 contrast. For those spots, replace with `#6b6b6b` (a darker shade) or use `--text-sub` variable.

- [ ] **Step 2: Add keyboard-reachable affordances**

Find any `<div onclick=...>` that lacks `tabindex="0"` and `role="button"`. Add those attributes + `onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click();}"`.

Priority spots:
- Kanban cards (pipeline)
- Dashboard tiles
- Settings card headers if they toggle

- [ ] **Step 3: Commit + push**

```bash
git add index.html
git commit -m "A11y: contrast fix and keyboard reach on click-handlers"
git push origin main
```

---

## Task 5.6: Final Lighthouse + smoke

- [ ] **Step 1: Run Lighthouse accessibility audit on login page** (DevTools → Lighthouse → Accessibility only → Mobile).

Expected: score ≥ 90.

- [ ] **Step 2: Run Lighthouse on dashboard** (after login).

Expected: score ≥ 85. Record baseline for future improvement.

- [ ] **Step 3: Keyboard-only walkthrough**

Close mouse input. Use Tab/Enter/Escape only. Walk: login → dashboard → project → save → settings. Must be fully operable.

- [ ] **Step 4: Record results in CLAUDE.md session note.**

---

# End-of-session

## Task E.1: Update CLAUDE.md

- [ ] **Step 1: Add end-of-session summary** to `CLAUDE.md` under a new section "Session 2026-04-16":

```markdown
### Session 2026-04-16 — Auth, 2FA, RLS, UX hardening

**Shipped:**
- Email-based login (@hdgrading.com enforced); show-password toggle
- bcrypt password hashing with auto-migration from SHA-256 on next login
- Rate limiting (5/10min per IP+email) + account lockout at 10 failures
- Email 2FA: 6-digit code, 10-min expiry, 3 resends/hour
- Forgot-password flow via Gmail API + signed reset tokens
- Session regeneration on login; old sessions invalidated on password change
- CSRF double-submit cookie on all authenticated mutating routes
- CSP + Referrer-Policy + Permissions-Policy headers
- RLS enabled on all 17 public tables; anon/authenticated grants revoked
- A11y sweep: focus ring, aria-live toasts, labels, aria-busy, contrast, kbd nav

**New routes:**
- POST /auth/2fa/verify
- POST /auth/2fa/resend
- POST /auth/forgot
- GET  /reset
- POST /auth/reset
- GET  /csrf/token

**New tables:** hd_login_attempts, hd_2fa_codes, hd_password_resets
**New hd_users columns:** failed_login_count, locked_until, last_login_at, password_updated_at
**New files:** security.py, auth_email.py
**New env vars:** GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_SENDER_EMAIL
```

- [ ] **Step 2: Mark related bug reports as Fixed**

Call Supabase MCP to list Open bugs, identify any that are now resolved by this session's work (account enumeration, weak hashing, missing 2FA, etc.), and PATCH them to Fixed with admin_notes pointing at this session.

- [ ] **Step 3: Final commit + push**

```bash
git add CLAUDE.md
git commit -m "Session 2026-04-16: auth/2FA/RLS/UX hardening shipped"
git push origin main
```

---

## Self-review checklist

**Spec coverage:**
- [x] Domain enforcement → Task 1.2
- [x] Username-as-email migration → Task 1.6
- [x] bcrypt + SHA-256 fallback → Task 1.1-1.3
- [x] Show-password toggle → Task 1.7
- [x] Remove password_hint leak → Task 1.2
- [x] Rate limiting → Task 1.1, 1.2
- [x] Lockout → Task 1.2
- [x] Email 2FA (required) → Tasks 3.1
- [x] Forgot password → Tasks 2.1, 2.2, 2.5
- [x] Session regeneration + invalidation → Task 2.4
- [x] CSRF double-submit → Task 2.3
- [x] CSP + security headers → Task 1.4
- [x] RLS on all 13+ tables → Tasks 4.1, 4.2
- [x] Revoke anon/auth grants → Task 4.1
- [x] Drop over-permissive policies → Task 4.1
- [x] Top-10 a11y sweep → Tasks 5.1-5.6

**Placeholder scan:** None. All code blocks have real content.

**Type/name consistency:**
- `hash_password`, `verify_password`, `generate_2fa_code`, `hash_2fa_code`, `validate_hd_email`, `mask_email`, `make_reset_serializer`, `sign_reset_token`, `verify_reset_token`, `rate_limit_check`, `rate_limit_record_failure`, `issue_csrf_token`, `verify_csrf` — all named identically everywhere they appear.
- DB columns: `failed_login_count`, `locked_until`, `last_login_at`, `password_updated_at`, `token_hash`, `code_hash`, `consumed_at`, `expires_at` — consistent.
- JS globals: `_userRole`, `_userName`, `_userUsername`, `_userEmail`, `_userPhone`, `_userAvatar` — match what exists in the codebase already (see `index.html:3806`).

Plan complete.
