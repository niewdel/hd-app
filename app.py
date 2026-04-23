import os, tempfile, functools, json, hashlib, time, uuid, re, html
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session, send_file
from werkzeug.utils import secure_filename
from generate_proposal import build
try:
    from googleapiclient.discovery import build as gmail_build
    from google.oauth2.credentials import Credentials
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

import generate_report
import requests as http

from security import (
    hash_password as bcrypt_hash_password,
    verify_password,
    rate_limit_check, rate_limit_record_failure,
    validate_hd_email, mask_email,
)

app = Flask(__name__, static_folder='.', static_url_path='')
_SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not _SECRET_KEY or _SECRET_KEY == 'hd-hauling-dev-key':
    raise RuntimeError('SECRET_KEY env var must be set to a non-default value. Refusing to start.')
app.secret_key = _SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=8)
SUPABASE_URL        = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY        = os.environ.get('SUPABASE_KEY', '')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')

def sb_headers():
    # Backend is trusted; use service_role so RLS-enabled tables stay reachable.
    # Falls back to SUPABASE_KEY if the service key env is missing (preserves prior behavior).
    key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def sb_admin_headers(prefer='return=representation'):
    key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': prefer
    }

@app.after_request
def set_security_headers(response):
    # /lead-form and /applicants-form are intentionally embeddable on external
    # websites (public quote + careers forms). Everything else denies framing.
    is_public_embed = request.path in ('/lead-form', '/applicants-form')
    if not is_public_embed:
        response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(self), camera=(), microphone=(), payment=()'
    # CSP: keeps 'unsafe-inline' because the single-file SPA has many inline scripts/styles.
    # Still a significant improvement over no CSP (blocks external-script injection, frames, form-action).
    frame_ancestors = "*" if is_public_embed else "'none'"
    # Public form pages get Google Maps / Places JS allowed; nowhere else.
    maps_script = " https://maps.googleapis.com https://maps.gstatic.com" if is_public_embed else ""
    maps_connect = " https://maps.googleapis.com" if is_public_embed else ""
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        f"script-src 'self' 'unsafe-inline'{maps_script}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data:; "
        f"connect-src 'self' https://azznfkboiwayifhhcguz.supabase.co https://api.open-meteo.com{maps_connect}; "
        f"frame-ancestors {frame_ancestors}; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    origin = request.headers.get('Origin', '')
    allowed = 'https://hdapp.up.railway.app'
    if origin == allowed:
        response.headers['Access-Control-Allow-Origin'] = allowed
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

def sb_url(table, params=''):
    return f'{SUPABASE_URL}/rest/v1/{table}{params}'

from urllib.parse import quote as _url_quote

def _sb_eq(column, value):
    """Build a safe PostgREST 'column=eq.<value>' filter with proper URL encoding.
    Prevents query-param injection via unescaped & or ? in value."""
    return '{}=eq.{}'.format(column, _url_quote(str(value), safe=''))

# ---------- Public form helpers: validation, honeypot, Google Places key ----------

GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY', '')
HONEYPOT_FIELD = 'website_url'
_EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')

def _normalize_phone(raw):
    """Return normalized US phone '000-000-0000' or None if not 10 digits.
    Accepts any input (spaces, parens, dashes, +1 prefix)."""
    digits = re.sub(r'\D', '', str(raw or ''))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f'{digits[0:3]}-{digits[3:6]}-{digits[6:10]}'

def _valid_email(raw):
    """True if raw looks like a real email with TLD. Bounds length to prevent ReDoS."""
    s = str(raw or '').strip()
    if not s or len(s) > 254:
        return False
    return bool(_EMAIL_RE.match(s))

def _honeypot_tripped(payload):
    """True if the hidden honeypot field was filled (bot indicator).
    payload: dict-like (request.json or request.form)."""
    try:
        return bool(str((payload or {}).get(HONEYPOT_FIELD, '')).strip())
    except Exception:
        return False

@app.route('/forms/config')
def forms_config():
    """Public (no auth). Returns non-secret config the public forms need.
    Only exposes the Google Places browser key (already constrained to HTTP
    referrers via Google Cloud console). Returns empty string if unset so the
    forms fall back to plain text inputs gracefully."""
    try:
        from security import rate_limit_check as _rlc
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
        allowed, _retry = _rlc(f'formscfg:{ip}', max_attempts=60, window_s=60)
        if not allowed:
            return jsonify({'places_key': ''}), 429
    except ImportError:
        pass
    return jsonify({'places_key': GOOGLE_PLACES_API_KEY})

def hash_password(pw):
    """Shim: legacy name kept so existing callers (user-creation routes) still work.
    Now produces a bcrypt hash via security.hash_password."""
    return bcrypt_hash_password(pw)

MAX_AVATAR_DATA_LEN = 2_500_000

def sanitize_avatar_data(value):
    avatar = str(value or '').strip()
    if not avatar:
        return ''
    if not avatar.startswith('data:image/'):
        raise ValueError('Profile photo must be an image.')
    if len(avatar) > MAX_AVATAR_DATA_LEN:
        raise ValueError('Profile photo is too large. Please upload a smaller image.')
    return avatar

def apply_user_session(user):
    session['authenticated'] = True
    session['username'] = user.get('username', '')
    session['full_name'] = user.get('full_name', user.get('username', ''))
    session['role'] = user.get('role', 'user')
    session['email'] = user.get('email', '')
    session['phone'] = user.get('phone', '')
    # avatar_data stored in DB (hd_users.avatar_data), NOT in session — exceeds cookie size limit
    session.permanent = True

def log_access(username, full_name, action='login', success=True):
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        ua = request.headers.get('User-Agent', '')[:200]
        http.post(sb_url('hd_access_log'), headers=sb_headers(), json={
            'username': username, 'full_name': full_name,
            'action': action, 'success': success,
            'ip_address': ip, 'user_agent': ua
        }, timeout=3)
    except Exception:
        pass

def _safe_error(e, context=''):
    """Log exception internally; return a generic client-safe message.
    Use in authed routes where leaking str(e) is undesirable."""
    try:
        app.logger.exception('[%s] %s', context or 'route', e)
    except Exception:
        pass
    return jsonify({'error': 'Internal error. Check logs.'}), 500

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        if session.get('role') not in ('admin', 'dev'):
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

def require_dev(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        if session.get('role') != 'dev':
            return jsonify({'error': 'Dev access required'}), 403
        return f(*args, **kwargs)
    return decorated

def _owns_or_admin(record_created_by):
    """Return True if the current session owns the record or is admin/dev.
    Null-safe — records with null created_by are owned by 'estimates@hdgrading.com'
    after the 2026-04-20 backfill, so null here means not-yet-migrated and
    we fall through to admin/dev check."""
    role = session.get('role', '')
    if role in ('admin', 'dev'):
        return True
    if record_created_by and record_created_by == session.get('username'):
        return True
    return False

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    identifier = str(data.get('username', data.get('email', ''))).strip().lower()
    password = str(data.get('password', data.get('pin', ''))).strip()

    # Allow either @hdgrading.com email or a plain short username.
    is_email = '@' in identifier
    if is_email:
        if not validate_hd_email(identifier):
            return jsonify({'error': 'Please use your @hdgrading.com email'}), 401
        lookup_col = 'email'
    else:
        if not identifier or len(identifier) > 64:
            return jsonify({'error': 'Incorrect email or password'}), 401
        lookup_col = 'username'

    # Rate limit: 5 attempts per IP+identifier per 10 min
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
    rl_key = f'login:{ip}:{identifier}'
    allowed, retry = rate_limit_check(rl_key, max_attempts=5, window_s=600)
    if not allowed:
        return jsonify({'error': f'Too many attempts. Try again in {retry} seconds.'}), 429

    try:
        r = http.get(sb_url('hd_users', '?' + _sb_eq(lookup_col, identifier) + '&' + 'active=eq.true&' + 'limit=1'),
                     headers=sb_headers(), timeout=5)
        if r.status_code != 200:
            return jsonify({'error': 'Database connection error. Please try again.'}), 503
        rows = r.json()
        if not rows:
            # Generic error — no user enumeration
            log_access(identifier, '', 'login', False)
            return jsonify({'error': 'Incorrect email or password'}), 401
        user = rows[0]

        # Account lockout check
        locked_until = user.get('locked_until')
        if locked_until:
            try:
                lu = datetime.fromisoformat(locked_until.replace('Z', '+00:00')).replace(tzinfo=None)
                if lu > datetime.utcnow():
                    return jsonify({'error': 'Account temporarily locked. Contact admin.'}), 423
            except Exception:
                pass

        valid, needs_rehash = verify_password(password, user.get('pin_hash', ''))
        if valid:
            # Seamless migration: legacy SHA-256 hashes get upgraded to bcrypt on successful login
            if needs_rehash:
                try:
                    http.patch(sb_url('hd_users', '?' + _sb_eq('id', user["id"])),
                               headers={**sb_headers(), 'Prefer': 'return=minimal'},
                               json={'pin_hash': bcrypt_hash_password(password),
                                     'password_updated_at': datetime.utcnow().isoformat()},
                               timeout=5)
                except Exception:
                    pass
            # Reset failed-login counter + stamp last_login_at
            try:
                http.patch(sb_url('hd_users', '?' + _sb_eq('id', user["id"])),
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
                            'avatar_data': user.get('avatar_data', ''),
                            'notif_prefs': user.get('notif_prefs') or {},
                            'welcome_seen': bool(user.get('welcome_seen_at'))})
        else:
            # Increment failure counter; lock account at 10 cumulative failures
            try:
                new_count = int(user.get('failed_login_count') or 0) + 1
                update = {'failed_login_count': new_count}
                if new_count >= 10:
                    update['locked_until'] = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
                http.patch(sb_url('hd_users', '?' + _sb_eq('id', user["id"])),
                           headers={**sb_headers(), 'Prefer': 'return=minimal'},
                           json=update, timeout=5)
            except Exception:
                pass
            rate_limit_record_failure(rl_key, window_s=600)
            log_access(identifier, '', 'login', False)
            return jsonify({'error': 'Incorrect email or password'}), 401
    except http.exceptions.ConnectionError:
        return jsonify({'error': 'Cannot reach database. Check your connection.'}), 503
    except Exception as e:
        print(f'[login] {type(e).__name__}: {e}')
        return jsonify({'error': 'Login error. Try again.'}), 500

@app.route('/auth/logout', methods=['POST'])
def logout():
    if session.get('username'):
        log_access(session.get('username',''), session.get('full_name',''), 'logout', True)
    session.clear()
    return jsonify({'ok': True})

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
        r = http.get(sb_url('hd_users', '?' + _sb_eq('username', username) + '&' + 'limit=1'), headers=sb_headers(), timeout=5)
        if r.status_code != 200 or not r.json():
            return jsonify({'ok': False, 'error': 'User not found'}), 404
        user = r.json()[0]
        valid, _ = verify_password(current, user.get('pin_hash', ''))
        if not valid:
            return jsonify({'ok': False, 'error': 'Current password is incorrect'}), 401
        update = {'pin_hash': bcrypt_hash_password(new_pw),
                  'password_updated_at': datetime.utcnow().isoformat()}
        http.patch(sb_url('hd_users', '?' + _sb_eq('username', username)), headers={**sb_headers(), 'Prefer': 'return=minimal'}, json=update, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        print(f'[change-password] {type(e).__name__}: {e}')
        return jsonify({'ok': False, 'error': 'Could not update password. Try again.'}), 500

@app.route('/auth/check')
def auth_check():
    if not session.get('authenticated'):
        return jsonify({'authenticated': False})
    # Refresh session against current DB row in case the user was renamed
    # since this session was created (e.g., admin changed their username).
    # Look up by current session.username first; fall back to email if missing
    # (which happens when username was changed but session still has the old value).
    sess_un = session.get('username', '')
    sess_em = session.get('email', '')
    user = None
    try:
        if sess_un:
            r = http.get(sb_url('hd_users', '?' + _sb_eq('username', sess_un) + '&active=eq.true&limit=1'),
                         headers=sb_headers(), timeout=5)
            if r.status_code == 200 and r.json():
                user = r.json()[0]
        if not user and sess_em:
            r = http.get(sb_url('hd_users', '?' + _sb_eq('email', sess_em) + '&active=eq.true&limit=1'),
                         headers=sb_headers(), timeout=5)
            if r.status_code == 200 and r.json():
                user = r.json()[0]
                # Username drift detected — refresh session to current DB value
                apply_user_session(user)
    except Exception:
        pass  # Network blip — fall back to current session values
    if user:
        return jsonify({'authenticated': True,
                        'role': user.get('role', session.get('role', 'user')),
                        'username': user.get('username', session.get('username', '')),
                        'full_name': user.get('full_name', session.get('full_name', '')),
                        'email': user.get('email', session.get('email', '')),
                        'notif_prefs': user.get('notif_prefs') or {},
                        'welcome_seen': bool(user.get('welcome_seen_at'))})
    return jsonify({'authenticated': True, 'role': session.get('role', 'user'),
                    'username': session.get('username', ''), 'full_name': session.get('full_name', ''),
                    'email': session.get('email', ''), 'notif_prefs': {}, 'welcome_seen': False})

@app.route('/auth/prefs', methods=['GET'])
@require_auth
def auth_get_prefs():
    """Return the current user's notif_prefs JSONB. Used by the frontend on
    load as a fallback if /auth/check didn't hydrate them."""
    username = session.get('username', '')
    try:
        r = http.get(sb_url('hd_users', '?' + _sb_eq('username', username) +
                            '&select=notif_prefs&limit=1'),
                     headers=sb_headers(), timeout=5)
        rows = r.json() if r.status_code == 200 else []
        prefs = (rows[0].get('notif_prefs') if rows else None) or {}
        return jsonify({'ok': True, 'notif_prefs': prefs})
    except Exception as e:
        return _safe_error(e, context='auth/prefs GET')

@app.route('/auth/prefs', methods=['PATCH'])
@require_auth
def auth_patch_prefs():
    """Replace the current user's notif_prefs JSONB. Body: {notif_prefs: {...}}.
    Always scoped to the current user — no way for one user to write another's."""
    data = request.get_json() or {}
    prefs = data.get('notif_prefs')
    if not isinstance(prefs, dict):
        return jsonify({'ok': False, 'error': 'notif_prefs must be an object'}), 400
    username = session.get('username', '')
    try:
        r = http.patch(sb_url('hd_users', '?' + _sb_eq('username', username)),
                       headers={**sb_headers(), 'Prefer': 'return=minimal'},
                       json={'notif_prefs': prefs}, timeout=5)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Save failed'}), 500
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='auth/prefs PATCH')

@app.route('/auth/welcome-seen', methods=['POST'])
@require_auth
def mark_welcome_seen():
    """Mark the current user's welcome modal as seen so it doesn't auto-show on
    subsequent logins from any device. Called by the frontend when the welcome
    modal is dismissed."""
    try:
        username = session.get('username', '')
        if not username:
            return jsonify({'ok': False, 'error': 'No session'}), 401
        from datetime import datetime
        http.patch(sb_url('hd_users', '?' + _sb_eq('username', username)),
                   headers={**sb_headers(), 'Prefer': 'return=minimal'},
                   json={'welcome_seen_at': datetime.utcnow().isoformat()},
                   timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        # If the column doesn't exist yet (SQL migration not run), this 4xx's
        # silently. Frontend still has the localStorage fallback.
        return _safe_error(e, context='auth/welcome-seen')

@app.route('/auth/profile', methods=['PATCH'])
@require_auth
def auth_update_profile():
    data = request.get_json() or {}
    username = session.get('username', '')
    full_name = str(data.get('full_name', session.get('full_name', ''))).strip()
    email = str(data.get('email', session.get('email', ''))).strip()
    phone = str(data.get('phone', session.get('phone', ''))).strip()
    if not full_name:
        return jsonify({'ok': False, 'error': 'Full name is required.'}), 400
    try:
        update = {'full_name': full_name, 'email': email, 'phone': phone}
        if 'avatar_data' in data:
            avatar_data = sanitize_avatar_data(data.get('avatar_data', ''))
            update['avatar_data'] = avatar_data
        r = http.patch(
            sb_url('hd_users', '?' + _sb_eq('username', username)),
            headers={**sb_headers(), 'Prefer': 'return=representation'},
            json=update,
            timeout=5
        )
        if r.status_code not in (200, 201):
            return jsonify({'ok': False, 'error': r.text or 'Failed to update profile.'}), 400
        rows = r.json() if r.text else []
        user = rows[0] if isinstance(rows, list) and rows else update
        user['username'] = user.get('username', username)
        user['role'] = user.get('role', session.get('role', 'user'))
        apply_user_session(user)
        return jsonify({'ok': True, 'profile': {
            'username': session.get('username', ''),
            'full_name': session.get('full_name', ''),
            'email': session.get('email', ''),
            'phone': session.get('phone', ''),
            'role': session.get('role', 'user'),
            'avatar_data': user.get('avatar_data', '')
        }})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return _safe_error(e, context='auth/profile')

# ââ Proposals âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/quotes/save', methods=['POST'])
@require_auth
def quotes_save():
    data = request.get_json() or {}
    try:
        snap = data.get('snap', {})
        payload = {
            'name':   data.get('name', 'Unnamed'),
            'client': data.get('client', ''),
            'date':   data.get('date', ''),
            'total':  float(data.get('total', 0)),
            'snap':   snap if isinstance(snap, dict) else json.loads(snap),
            'created_by': session.get('username', ''),
        }
        if data.get('stage_id'):
            payload['stage_id'] = data['stage_id']
        r = http.post(sb_url('proposals'), headers=sb_headers(), json=payload, timeout=10)
        r.raise_for_status()
        result = r.json()
        log_access(session.get('username',''), session.get('full_name',''), f'created proposal "{data.get("name","")}"')
        return jsonify({'ok': True, 'id': result[0]['id'] if result else None})
    except Exception as e:
        return _safe_error(e, context='quotes/save')

@app.route('/quotes/update/<int:qid>', methods=['PATCH'])
@require_auth
def quotes_update(qid):
    data = request.get_json() or {}
    try:
        snap = data.get('snap', {})
        payload = {
            'name':   data.get('name', 'Unnamed'),
            'client': data.get('client', ''),
            'date':   data.get('date', ''),
            'total':  float(data.get('total', 0)),
            'snap':   snap if isinstance(snap, dict) else json.loads(snap),
            'created_by': session.get('username', ''),
        }
        r = http.patch(sb_url('proposals', '?' + _sb_eq('id', qid)), headers=sb_headers(), json=payload, timeout=10)
        r.raise_for_status()
        log_access(session.get('username',''), session.get('full_name',''), f'updated proposal "{data.get("name","")}"')
        return jsonify({'ok': True, 'id': qid})
    except Exception as e:
        return _safe_error(e, context='quotes/update/<int:qid>')

@app.route('/boot/data')
@require_auth
def boot_data():
    """Single endpoint that returns quotes, pipeline stages, and pipeline proposals in one call."""
    import concurrent.futures
    def _fetch(url):
        r = http.get(url, headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            f_quotes = pool.submit(_fetch, sb_url('proposals', '?select=*&archived=neq.true&order=created_at.desc'))
            f_stages = pool.submit(_fetch, sb_url('pipeline_stages', '?select=*&order=position.asc'))
            f_pipeline = pool.submit(_fetch, sb_url('proposals', '?select=id,name,client,total,stage_id,snap,created_at,pipeline_stages!left(name,color,counts_in_ratio,is_closed)&archived=neq.true&order=created_at.desc'))
        return jsonify({
            'ok': True,
            'quotes': f_quotes.result(),
            'stages': f_stages.result(),
            'proposals': f_pipeline.result()
        })
    except Exception as e:
        return _safe_error(e, context='boot/data')

@app.route('/quotes/list')
@require_auth
def quotes_list():
    try:
        r = http.get(sb_url('proposals', '?select=*&archived=neq.true&order=created_at.desc'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True, 'quotes': r.json()})
    except Exception as e:
        return _safe_error(e, context='quotes/list')

@app.route('/quotes/delete/<int:qid>', methods=['DELETE'])
@require_auth
def quotes_delete(qid):
    try:
        # Ownership check: fetch created_by + name in one call
        name = ''
        lookup = http.get(sb_url('proposals', '?' + _sb_eq('id', qid) + '&select=name,created_by'),
                          headers=sb_admin_headers(), timeout=10)
        rows = lookup.json() if lookup.ok else []
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        if not _owns_or_admin(rows[0].get('created_by')):
            return jsonify({'error': 'Not permitted'}), 403
        name = rows[0].get('name', '') or ''
        r = http.patch(
            sb_url('proposals', '?' + _sb_eq('id', qid)),
            json={'archived': True, 'archived_at': datetime.utcnow().isoformat()},
            headers=sb_headers(), timeout=10
        )
        r.raise_for_status()
        # Cascade delete associated data (change orders, time entries)
        try:
            http.delete(sb_url('change_orders', '?' + _sb_eq('proposal_id', qid)), headers=sb_headers(), timeout=10)
        except Exception:
            pass
        try:
            http.delete(sb_url('hd_time_entries', '?' + _sb_eq('project_id', qid)), headers=sb_headers(), timeout=10)
        except Exception:
            pass
        log_access(session.get('username',''), session.get('full_name',''), f'archived proposal "{name}"')
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='quotes/delete/<int:qid>')

# ââ Pipeline ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/pipeline/stages')
@require_auth
def pipeline_stages():
    try:
        r = http.get(sb_url('pipeline_stages', '?select=*&order=position.asc'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True, 'stages': r.json()})
    except Exception as e:
        return _safe_error(e, context='pipeline/stages')

@app.route('/pipeline/list')
@require_auth
def pipeline_list():
    try:
        r = http.get(
            sb_url('proposals', '?select=id,name,client,total,stage_id,snap,created_at,pipeline_stages!left(name,color,counts_in_ratio,is_closed)&archived=neq.true&order=created_at.desc'),
            headers=sb_headers(), timeout=10
        )
        r.raise_for_status()
        return jsonify({'ok': True, 'proposals': r.json()})
    except Exception as e:
        return _safe_error(e, context='pipeline/list')

@app.route('/pipeline/move/<int:proposal_id>', methods=['PATCH'])
@require_auth
def pipeline_move(proposal_id):
    data = request.get_json() or {}
    try:
        r = http.patch(
            sb_url('proposals', '?' + _sb_eq('id', proposal_id)),
            headers=sb_headers(),
            json={'stage_id': data.get('stage_id')},
            timeout=10
        )
        r.raise_for_status()
        stage_name = data.get('stage_name', '')
        log_access(session.get('username',''), session.get('full_name',''), f'moved project to "{stage_name}"' if stage_name else 'moved project stage')
        # Notify approvers when proposal enters "Waiting for Approval"
        if stage_name == 'Waiting for Approval':
            try:
                ag = http.get(sb_url('hd_settings', '?key=eq.approval_group&select=value'), headers=sb_headers(), timeout=5)
                approvers = ag.json()[0]['value'] if ag.status_code == 200 and ag.json() else []
                proposal_name = data.get('proposal_name', f'Project #{proposal_id}')
                username = session.get('username', '')
                notif_rows = [{'recipient': u, 'type': 'approval', 'title': f'Approval Needed: {proposal_name}',
                              'body': f'{session.get("full_name", username)} submitted "{proposal_name}" for approval',
                              'project_id': proposal_id, 'project_name': proposal_name, 'created_by': username} for u in approvers if u != username]
                if notif_rows:
                    http.post(sb_url('hd_notifications', ''), headers=sb_headers(), json=notif_rows, timeout=10)
                    # Email approvers
                    _send_notif_emails(
                        [u for u in approvers if u != username],
                        username,
                        f'Approval Needed: {proposal_name}',
                        f'{session.get("full_name", username)} submitted "{proposal_name}" for your approval. Please review and approve in the HD app.',
                        proposal_name
                    )
            except Exception:
                pass
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='pipeline/move/<int:proposal_id>')

@app.route('/proposals/approve/<int:proposal_id>', methods=['POST'])
@require_auth
def approve_proposal(proposal_id):
    username = session.get('username', '')
    try:
        ag = http.get(sb_url('hd_settings', '?key=eq.approval_group&select=value'), headers=sb_headers(), timeout=5)
        approvers = ag.json()[0]['value'] if ag.status_code == 200 and ag.json() else []
        if username not in approvers:
            return jsonify({'ok': False, 'error': 'Not authorized to approve'}), 403
        r = http.get(sb_url('proposals', '?' + _sb_eq('id', proposal_id) + '&' + 'select=snap,name'), headers=sb_headers(), timeout=5)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            return jsonify({'ok': False, 'error': 'Not found'}), 404
        snap = rows[0].get('snap', {})
        if isinstance(snap, str):
            snap = json.loads(snap)
        snap['approved'] = True
        snap['approved_by'] = session.get('full_name', username)
        snap['approved_at'] = datetime.utcnow().isoformat()
        snap['locked'] = True
        # Find Approved stage to auto-advance
        stages_r = http.get(sb_url('pipeline_stages', '?name=eq.Approved&select=id'), headers=sb_headers(), timeout=5)
        approved_stage_id = stages_r.json()[0]['id'] if stages_r.status_code == 200 and stages_r.json() else None
        update = {'snap': json.dumps(snap) if isinstance(snap, dict) else snap}
        if approved_stage_id:
            update['stage_id'] = approved_stage_id
        http.patch(sb_url('proposals', '?' + _sb_eq('id', proposal_id)), headers=sb_headers(), json=update, timeout=10)
        # Notify all users
        proposal_name = rows[0].get('name', f'Project #{proposal_id}')
        try:
            all_users_r = http.get(sb_url('hd_users', '?active=eq.true&select=username'), headers=sb_headers(), timeout=5)
            all_users = [u['username'] for u in all_users_r.json()] if all_users_r.status_code == 200 else []
            notif_rows = [{'recipient': u, 'type': 'approval', 'title': f'Approved: {proposal_name}',
                          'body': f'{session.get("full_name", username)} approved "{proposal_name}"',
                          'project_id': proposal_id, 'project_name': proposal_name, 'created_by': username} for u in all_users if u != username]
            if notif_rows:
                http.post(sb_url('hd_notifications', ''), headers=sb_headers(), json=notif_rows, timeout=10)
                # Email all users about approval
                _send_notif_emails(
                    [u for u in all_users if u != username],
                    username,
                    f'Proposal Approved: {proposal_name}',
                    f'{session.get("full_name", username)} approved "{proposal_name}". The proposal is now locked.',
                    proposal_name
                )
        except Exception:
            pass
        log_access(username, session.get('full_name',''), f'approved proposal "{proposal_name}"')
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='proposals/approve/<int:proposal_id>')

@app.route('/proposals/pull-back/<int:proposal_id>', methods=['POST'])
@require_auth
def pull_back_proposal(proposal_id):
    username = session.get('username', '')
    try:
        ag = http.get(sb_url('hd_settings', '?key=eq.approval_group&select=value'), headers=sb_headers(), timeout=5)
        approvers = ag.json()[0]['value'] if ag.status_code == 200 and ag.json() else []
        if username not in approvers:
            return jsonify({'ok': False, 'error': 'Not authorized'}), 403
        r = http.get(sb_url('proposals', '?' + _sb_eq('id', proposal_id) + '&' + 'select=snap,name'), headers=sb_headers(), timeout=5)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            return jsonify({'ok': False, 'error': 'Not found'}), 404
        snap = rows[0].get('snap', {})
        if isinstance(snap, str):
            snap = json.loads(snap)
        snap['approved'] = False
        snap['locked'] = False
        snap.pop('approved_by', None)
        snap.pop('approved_at', None)
        # Move back to "Waiting for Approval" stage
        stages_r = http.get(sb_url('pipeline_stages', '?name=eq.Waiting for Approval&select=id'), headers=sb_headers(), timeout=5)
        wfa_stage_id = stages_r.json()[0]['id'] if stages_r.status_code == 200 and stages_r.json() else None
        update = {'snap': json.dumps(snap) if isinstance(snap, dict) else snap}
        if wfa_stage_id:
            update['stage_id'] = wfa_stage_id
        http.patch(sb_url('proposals', '?' + _sb_eq('id', proposal_id)), headers=sb_headers(), json=update, timeout=10)
        proposal_name = rows[0].get('name', f'Project #{proposal_id}')
        log_access(username, session.get('full_name',''), f'pulled back proposal "{proposal_name}" for edits')
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='proposals/pull-back/<int:proposal_id>')

def _next_project_number():
    """Generate next project number: HD-YYMM-### format."""
    from datetime import datetime
    now = datetime.now()
    prefix = f'HD-{now.strftime("%y%m")}'
    # Get current counter from hd_settings
    try:
        r = http.get(sb_url('hd_settings', '?key=eq.project_counter'), headers=sb_headers(), timeout=5)
        rows = r.json() if r.status_code == 200 else []
        counter_data = rows[0]['value'] if rows else {}
    except Exception:
        counter_data = {}
    current_month = now.strftime('%y%m')
    if counter_data.get('month') == current_month:
        seq = counter_data.get('seq', 0) + 1
    else:
        seq = 1
    # Save updated counter
    new_val = {'month': current_month, 'seq': seq}
    try:
        h = {**sb_headers(), 'Prefer': 'return=representation'}
        if rows:
            http.patch(sb_url('hd_settings', '?key=eq.project_counter'), headers=h,
                      json={'value': new_val}, timeout=5)
        else:
            http.post(sb_url('hd_settings'), headers=h,
                     json={'key': 'project_counter', 'value': new_val}, timeout=5)
    except Exception:
        pass
    return f'{prefix}-{seq:03d}'

@app.route('/projects/create', methods=['POST'])
@require_auth
def project_create():
    data = request.get_json() or {}
    try:
        project_number = _next_project_number()
        snap = {
            'is_project': True,
            'project_number': project_number,
            'address': data.get('address', ''),
            'city_state': data.get('city_state', ''),
            'bid_due_date': data.get('bid_due_date', ''),
            'bid_due_time': data.get('bid_due_time', ''),
            'notes': data.get('notes', ''),
            'linked_proposals': [],
            'activity_log': data.get('activity_log', []),
            'assigned_to': data.get('assigned_to', ''),
            'bidding_clients': data.get('bidding_clients', []),
        }
        if data.get('selectedClient'):
            snap['selectedClient'] = data['selectedClient']
        payload = {
            'name': data.get('name', 'Unnamed Project'),
            'client': data.get('client', ''),
            'date': data.get('date', ''),
            'total': 0,
            'snap': snap,
            'created_by': session.get('username', ''),
        }
        if data.get('stage_id'):
            payload['stage_id'] = data['stage_id']
        r = http.post(sb_url('proposals'), headers=sb_headers(), json=payload, timeout=10)
        r.raise_for_status()
        result = r.json()
        log_access(session.get('username',''), session.get('full_name',''), f'created project "{data.get("name","")}" ({project_number})')
        return jsonify({'ok': True, 'id': result[0]['id'] if result else None, 'project_number': project_number})
    except Exception as e:
        return _safe_error(e, context='projects/create')

@app.route('/projects/update/<int:pid>', methods=['PATCH'])
@require_auth
def project_update(pid):
    data = request.get_json() or {}
    try:
        # Ownership check
        lookup = http.get(sb_url('proposals', '?' + _sb_eq('id', pid) + '&select=created_by'),
                          headers=sb_admin_headers(), timeout=10)
        rows = lookup.json() if lookup.ok else []
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        if not _owns_or_admin(rows[0].get('created_by')):
            return jsonify({'error': 'Not permitted'}), 403
        payload = {}
        if 'name' in data: payload['name'] = data['name']
        if 'client' in data: payload['client'] = data['client']
        if 'snap' in data: payload['snap'] = data['snap']
        if 'total' in data: payload['total'] = float(data['total'])
        r = http.patch(sb_url('proposals', '?' + _sb_eq('id', pid)), headers=sb_headers(), json=payload, timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='projects/update/<int:pid>')

# ââ Clients âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/clients/list')
@require_auth
def clients_list():
    try:
        r = http.get(sb_url('clients', '?select=*&order=name.asc'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True, 'clients': r.json()})
    except Exception as e:
        return _safe_error(e, context='clients/list')

@app.route('/clients/save', methods=['POST'])
@require_auth
def clients_save():
    data = request.get_json() or {}
    try:
        row = {
            'name': data.get('name', ''), 'company': data.get('company', ''),
            'phone': data.get('phone', ''), 'email': data.get('email', ''),
            'address': data.get('address', ''), 'city_state': data.get('city_state', ''),
            'notes': data.get('notes', ''),
        }
        # company_id is optional FK to hd_companies; None = unlinked contact
        if 'company_id' in data:
            row['company_id'] = data.get('company_id') or None
        r = http.post(sb_url('clients'), headers=sb_headers(), json=row, timeout=10)
        r.raise_for_status()
        result = r.json()
        return jsonify({'ok': True, 'id': result[0]['id'] if result else None})
    except Exception as e:
        return _safe_error(e, context='clients/save')

@app.route('/clients/update/<int:client_id>', methods=['PATCH'])
@require_auth
def clients_update(client_id):
    data = request.get_json() or {}
    try:
        row = {
            'name': data.get('name', ''), 'company': data.get('company', ''),
            'phone': data.get('phone', ''), 'email': data.get('email', ''),
            'address': data.get('address', ''), 'city_state': data.get('city_state', ''),
            'notes': data.get('notes', ''),
        }
        if 'company_id' in data:
            row['company_id'] = data.get('company_id') or None
        r = http.patch(sb_url('clients', '?' + _sb_eq('id', client_id)), headers=sb_headers(), json=row, timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='clients/update/<int:client_id>')

@app.route('/clients/delete/<int:client_id>', methods=['DELETE'])
@require_auth
def clients_delete(client_id):
    try:
        # Ownership check: clients table has no created_by column in this schema,
        # so only admin/dev may delete.
        if not _owns_or_admin(None):
            return jsonify({'error': 'Not permitted'}), 403
        r = http.delete(sb_url('clients', '?' + _sb_eq('id', client_id)), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='clients/delete/<int:client_id>')

# -- Companies --------------------------------------------------------------
# CRM-level org entities. A company can be a customer, a subcontractor, or
# both. Individual contacts (clients table) link via clients.company_id.

_COMPANY_WRITABLE_FIELDS = (
    'name', 'domain', 'phone', 'email', 'address', 'city_state',
    'is_customer', 'is_subcontractor', 'trade', 'notes', 'logo_url',
)

def _company_row_from_payload(data):
    row = {}
    for k in _COMPANY_WRITABLE_FIELDS:
        if k in data:
            v = data.get(k)
            if isinstance(v, str):
                v = v.strip()
            row[k] = v
    # Normalize domain: strip protocol/path, lowercase
    if 'domain' in row and row['domain']:
        d = str(row['domain']).lower().strip()
        d = re.sub(r'^https?://', '', d)
        d = d.split('/', 1)[0].split('?', 1)[0]
        row['domain'] = d or None
    return row

@app.route('/companies/list')
@require_auth
def companies_list():
    """List companies. Optional filters: role=customer|subcontractor|all, q=<search>."""
    try:
        role = (request.args.get('role') or 'all').lower()
        q = (request.args.get('q') or '').strip()
        params = 'select=*&order=name.asc'
        if role == 'customer':
            params += '&is_customer=eq.true'
        elif role == 'subcontractor':
            params += '&is_subcontractor=eq.true'
        if q:
            from urllib.parse import quote as _qq
            needle = _qq('*' + q + '*')
            params += '&or=(name.ilike.{0},domain.ilike.{0},trade.ilike.{0})'.format(needle)
        r = http.get(sb_url('hd_companies', '?' + params), headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True, 'companies': r.json()})
    except Exception as e:
        return _safe_error(e, context='companies/list')

@app.route('/companies/<int:cid>')
@require_auth
def companies_get(cid):
    """Single company with its linked contacts (clients)."""
    try:
        cr = http.get(sb_url('hd_companies', '?' + _sb_eq('id', cid) + '&select=*'), headers=sb_admin_headers(), timeout=5)
        if cr.status_code != 200 or not cr.json():
            return jsonify({'ok': False, 'error': 'Company not found'}), 404
        company = cr.json()[0]
        lr = http.get(
            sb_url('clients', '?' + _sb_eq('company_id', cid) + '&select=id,name,email,phone,address,city_state,notes&order=name.asc'),
            headers=sb_admin_headers(), timeout=5
        )
        contacts = lr.json() if lr.status_code == 200 else []
        return jsonify({'ok': True, 'company': company, 'contacts': contacts})
    except Exception as e:
        return _safe_error(e, context='companies/<int:cid>')

@app.route('/companies/save', methods=['POST'])
@require_auth
def companies_save():
    """Create a new company. Name required; defaults to is_customer=true if no role flag set."""
    data = request.get_json() or {}
    name = str(data.get('name', '')).strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Company name is required.'}), 400
    try:
        row = _company_row_from_payload(data)
        row['name'] = name
        if not row.get('is_customer') and not row.get('is_subcontractor'):
            row['is_customer'] = True
        r = http.post(sb_url('hd_companies'), headers=sb_admin_headers(), json=row, timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        result = r.json()
        return jsonify({'ok': True, 'id': result[0]['id'] if result else None, 'company': result[0] if result else None})
    except Exception as e:
        return _safe_error(e, context='companies/save')

@app.route('/companies/<int:cid>', methods=['PATCH'])
@require_auth
def companies_update(cid):
    """Partial update — only fields present in payload are modified."""
    data = request.get_json() or {}
    try:
        row = _company_row_from_payload(data)
        if not row:
            return jsonify({'ok': False, 'error': 'Nothing to update'}), 400
        row['updated_at'] = datetime.utcnow().isoformat()
        r = http.patch(sb_url('hd_companies', '?' + _sb_eq('id', cid)), headers=sb_admin_headers(), json=row, timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='companies/<int:cid>')

@app.route('/companies/<int:cid>', methods=['DELETE'])
@require_auth
def companies_delete(cid):
    """Permanently delete a company. Linked clients.company_id becomes NULL
    (FK ON DELETE SET NULL) — contact records stay intact but unlinked."""
    try:
        if not _owns_or_admin(None):
            return jsonify({'ok': False, 'error': 'Not permitted'}), 403
        r = http.delete(sb_url('hd_companies', '?' + _sb_eq('id', cid)), headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='companies/<int:cid> DELETE')

# ââ PDF / DOCX ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ


@app.route('/users/list')
@require_auth
def list_users_basic():
    """Return active users (username, full_name, role) for @mentions and assignment."""
    try:
        r = http.get(sb_url('hd_users', '?active=eq.true&select=id,username,full_name,role&order=full_name.asc'), headers=sb_headers(), timeout=5)
        users = r.json() if r.status_code == 200 else []
        return jsonify({'ok': True, 'users': users})
    except Exception as e:
        return _safe_error(e, context='users/list')


@app.route('/admin/users', methods=['GET'])
@require_dev
def get_users():
    try:
        r = http.get(sb_url('hd_users', '?order=created_at.asc'), headers=sb_headers(), timeout=5)
        users = r.json() if r.status_code == 200 else []
        for u in users:
            u.pop('pin_hash', None)
            u.pop('password_hash', None)
        return jsonify({'ok': True, 'users': users})
    except Exception as e:
        return _safe_error(e, context='admin/users')


@app.route('/admin/users', methods=['POST'])
@require_dev
def create_user():
    data = request.get_json() or {}
    username = str(data.get('username','')).strip().lower()
    pin = str(data.get('password', data.get('pin',''))).strip()
    full_name = str(data.get('full_name','')).strip()
    email = str(data.get('email','')).strip()
    phone = str(data.get('phone','')).strip()
    role = data.get('role','user')
    if not full_name or not username or not pin: return jsonify({'ok':False,'error':'Full name, username, and password are required'}), 400
    if role not in ('admin','user','field','dev'): role = 'user'
    try:
        row = {'username':username,'full_name':full_name,'pin_hash':hash_password(pin),'role':role,'active':True,'created_by':session.get('username','admin')}
        if email: row['email'] = email
        if phone: row['phone'] = phone
        r = http.post(sb_url('hd_users'), headers=sb_headers(), json=row, timeout=5)
        if r.status_code in (200,201):
            user = r.json()[0] if isinstance(r.json(),list) else r.json()
            user.pop('pin_hash',None)
            return jsonify({'ok':True,'user':user})
        return jsonify({'ok':False,'error':r.text}), 400
    except Exception as e:
        return _safe_error(e, context='admin/users.create')

@app.route('/admin/users/<int:uid>', methods=['PATCH'])
@require_dev
def update_user(uid):
    data = request.get_json() or {}
    update = {}
    if 'full_name' in data: update['full_name'] = data['full_name']
    if 'email' in data: update['email'] = str(data['email']).strip()
    if 'phone' in data: update['phone'] = str(data['phone']).strip()
    if 'username' in data and data['username']:
        new_un = str(data['username']).strip().lower()
        if new_un: update['username'] = new_un
    if 'role' in data and data['role'] in ('admin','user','field','dev'): update['role'] = data['role']
    if 'active' in data: update['active'] = bool(data['active'])
    if 'password' in data and data['password']:
        update['pin_hash'] = hash_password(data['password'])
    elif 'pin' in data and data['pin']:
        update['pin_hash'] = hash_password(data['pin'])
    if 'hourly_rate' in data:
        update['hourly_rate'] = float(data['hourly_rate'] or 0)
    if not update: return jsonify({'ok':False,'error':'Nothing to update'}), 400
    try:
        # If username is changing, look up the old one first
        old_username = None
        if 'username' in update:
            try:
                r0 = http.get(sb_url('hd_users', '?' + _sb_eq('id', uid) + '&' + 'select=username'), headers=sb_headers(), timeout=5)
                if r0.status_code == 200 and r0.json():
                    old_username = r0.json()[0]['username']
            except Exception:
                pass

        headers = {**sb_headers(), 'Prefer': 'return=representation'}
        r = http.patch(sb_url('hd_users', '?' + _sb_eq('id', uid)), headers=headers, json=update, timeout=5)
        if r.status_code not in (200, 204):
            return jsonify({'ok': False, 'error': r.text}), 400
        rows = r.json() if r.status_code == 200 else []
        if isinstance(rows, list) and len(rows) == 0:
            return jsonify({'ok': False, 'error': 'User not found'}), 404

        # Cascade username change to notifications and other tables
        if old_username and 'username' in update and update['username'] != old_username:
            new_username = update['username']
            _cascade_username(old_username, new_username)

        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='admin/users.update')


def _cascade_username(old, new):
    """Update username references across tables when a user is renamed."""
    h = sb_headers()
    # Each entry: (table, column)
    targets = [
        ('hd_notifications',  'recipient'),
        ('hd_notifications',  'created_by'),
        ('hd_access_log',     'username'),
        ('proposals',         'created_by'),
        ('projects',          'created_by'),
        ('hd_tasks',          'created_by'),
        ('hd_tasks',          'assigned_to'),
        ('hd_reminders',      'created_by'),
        ('hd_reminders',      'assigned_to'),
        ('hd_bug_reports',    'submitted_by'),
        ('change_orders',     'created_by'),
        ('hd_email_log',      'sender_username'),
    ]
    for table, col in targets:
        try:
            http.patch(sb_url(table, '?' + _sb_eq(col, old)),
                       headers=h, json={col: new}, timeout=5)
        except Exception:
            pass  # Best-effort — don't fail the rename


@app.route('/admin/users/<int:uid>', methods=['DELETE'])
@require_dev
def delete_user(uid):
    """Permanently delete a user and all their related data."""
    try:
        # Look up user first
        r = http.get(sb_url('hd_users', '?' + _sb_eq('id', uid) + '&' + 'select=username'), headers=sb_headers(), timeout=5)
        if r.status_code != 200 or not r.json():
            return jsonify({'ok': False, 'error': 'User not found'}), 404
        username = r.json()[0]['username']

        # Don't allow deleting yourself
        if username == session.get('username'):
            return jsonify({'ok': False, 'error': 'Cannot delete your own account'}), 400

        h = {**sb_headers(), 'Prefer': 'return=minimal'}

        # Delete related data across all tables
        http.delete(sb_url('hd_access_log', '?' + _sb_eq('username', username)), headers=h, timeout=5)
        http.delete(sb_url('hd_notifications', '?' + _sb_eq('recipient', username)), headers=h, timeout=5)
        http.delete(sb_url('hd_reminders', '?' + _sb_eq('assigned_to', username)), headers=h, timeout=5)
        http.delete(sb_url('hd_reminders', '?' + _sb_eq('created_by', username)), headers=h, timeout=5)
        http.delete(sb_url('hd_tasks', '?' + _sb_eq('assigned_to', username)), headers=h, timeout=5)
        http.delete(sb_url('hd_tasks', '?' + _sb_eq('created_by', username)), headers=h, timeout=5)
        http.delete(sb_url('hd_time_entries', '?' + _sb_eq('username', username)), headers=h, timeout=5)
        http.delete(sb_url('hd_bug_reports', '?' + _sb_eq('submitted_by', username)), headers=h, timeout=5)

        # Delete the user record
        r2 = http.delete(sb_url('hd_users', '?' + _sb_eq('id', uid)), headers=h, timeout=5)
        if r2.status_code not in (200, 204):
            return jsonify({'ok': False, 'error': r2.text}), 400

        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='admin/users/<int:uid>')


@app.route('/admin/logs', methods=['GET'])
@require_dev
def get_logs():
    try:
        limit = int(request.args.get('limit',100))
        uf = request.args.get('username','')
        params = '?' + 'order=logged_at.desc&' + f'limit={limit}'
        if uf: params += '&' + _sb_eq('username', uf)
        r = http.get(sb_url('hd_access_log', params), headers=sb_headers(), timeout=5)
        return jsonify({'ok':True,'logs':r.json() if r.status_code==200 else []})
    except Exception as e:
        return _safe_error(e, context='admin/logs')

@app.route('/admin/archived')
@require_dev
def admin_archived():
    try:
        r = http.get(
            sb_url('proposals', '?archived=is.true&select=id,name,client,total,archived_at,snap&order=archived_at.desc&limit=50'),
            headers=sb_headers(), timeout=10
        )
        r.raise_for_status()
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return _safe_error(e, context='admin/archived')

@app.route('/admin/restore/<int:qid>', methods=['POST'])
@require_dev
def admin_restore(qid):
    try:
        r = http.patch(
            sb_url('proposals', '?' + _sb_eq('id', qid)),
            json={'archived': False, 'archived_at': None},
            headers=sb_headers(), timeout=10
        )
        r.raise_for_status()
        log_access(session.get('username',''), session.get('full_name',''), f'restored archived proposal id={qid}')
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='admin/restore/<int:qid>')

@app.route('/generate-pdf', methods=['POST'])
@require_auth
def generate_pdf():
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        build(data, out)
        return send_file(out, mimetype='application/pdf', as_attachment=False, download_name='HD_Proposal.pdf')
    except Exception as e:
        return _safe_error(e, context='generate-pdf')


@app.route('/generate-co-pdf', methods=['POST'])
@require_auth
def generate_co_pdf():
    from generate_change_order import build as co_build
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        co_build(data, out)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name='HD_ChangeOrder.pdf')
    except Exception as e:
        return _safe_error(e, context='generate-co-pdf')

@app.route('/generate-jc-pdf', methods=['POST'])
@require_auth
def generate_jc_pdf():
    from generate_job_cost import build as jc_build
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        jc_build(data, out)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name='HD_JobCost.pdf')
    except Exception as e:
        return _safe_error(e, context='generate-jc-pdf')


@app.route('/generate-pricing-breakdown', methods=['POST'])
@require_auth
def generate_pricing_breakdown():
    from generate_pricing_breakdown import build as pb_build
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        pb_build(data, out)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name='HD_Pricing_Breakdown.pdf')
    except Exception as e:
        return _safe_error(e, context='generate-pricing-breakdown')

@app.route('/generate-wo-pdf', methods=['POST'])
@require_auth
def generate_wo_pdf():
    from generate_work_order import build as wo_build
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        wo_build(data, out)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name='HD_WorkOrder.pdf')
    except Exception as e:
        return _safe_error(e, context='generate-wo-pdf')

@app.route('/generate-daily-report', methods=['POST'])
@require_auth
def generate_daily_report():
    from generate_daily_report import build as dr_build
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        dr_build(data, out)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name='HD_Daily_Report.pdf')
    except Exception as e:
        return _safe_error(e, context='generate-daily-report')

@app.route('/generate-report-pdf', methods=['POST'])
@require_auth
def generate_report_pdf():
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        generate_report.build(data, out)
        name = data.get('report_name', 'Report').replace(' ', '_')
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name=f'HD_{name}.pdf')
    except Exception as e:
        return _safe_error(e, context='generate-report-pdf')

@app.route('/change-orders/save', methods=['POST'])
@require_auth
def co_save():
    data = request.get_json() or {}
    try:
        snap = {
            'line_items': data.get('line_items', []),
            'orig_contract_amount': data.get('orig_contract_amount', 0),
            'description': data.get('description', ''),
            'project_number': data.get('project_number', ''),
        }
        payload = {
            'co_number': data.get('co_number', 1),
            'project_name': data.get('project_name', ''),
            'client_name': data.get('client_name', ''),
            'date': data.get('date', ''),
            'description': data.get('description', ''),
            'snap': snap,
            'add_total': float(data.get('add_total', 0)),
            'deduct_total': float(data.get('deduct_total', 0)),
            'revised_total': float(data.get('revised_total', 0)),
            'created_by': session.get('username', ''),
        }
        if data.get('proposal_id'):
            payload['proposal_id'] = data['proposal_id']
        r = http.post(sb_url('change_orders'), headers=sb_headers(), json=payload, timeout=10)
        if r.status_code in (200, 201):
            result = r.json()
            return jsonify({'ok': True, 'id': result[0]['id'] if result else None})
        return jsonify({'ok': False, 'error': 'Supabase error: ' + str(r.status_code)}), 400
    except Exception as e:
        return _safe_error(e, context='change-orders/save')

@app.route('/change-orders/list')
@require_auth
def co_list():
    try:
        proposal_id = request.args.get('proposal_id', '')
        params = '?select=*&order=created_at.desc'
        if proposal_id:
            params += '&' + _sb_eq('proposal_id', proposal_id)
        r = http.get(sb_url('change_orders', params), headers=sb_headers(), timeout=10)
        if r.status_code == 200:
            return jsonify({'ok': True, 'change_orders': r.json()})
        return jsonify({'ok': True, 'change_orders': []})
    except Exception as e:
        return _safe_error(e, context='change-orders/list')

# ââ Email âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/change-orders/delete/<int:coid>', methods=['DELETE'])
@require_auth
def co_delete(coid):
    try:
        # Ownership check
        lookup = http.get(sb_url('change_orders', '?' + _sb_eq('id', coid) + '&select=created_by'),
                          headers=sb_admin_headers(), timeout=10)
        rows = lookup.json() if lookup.ok else []
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        if not _owns_or_admin(rows[0].get('created_by')):
            return jsonify({'error': 'Not permitted'}), 403
        r = http.delete(sb_url('change_orders', '?' + _sb_eq('id', coid)), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        log_access(session.get('username',''), session.get('full_name',''), f'deleted change order #{coid}')
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='change-orders/delete/<int:coid>')

@app.route('/send-email', methods=['POST'])
@require_auth
def send_email():
    if not GMAIL_AVAILABLE:
        return jsonify({'ok': False, 'error': 'Gmail not configured'}), 500
    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    data = request.get_json() or {}
    sender = session.get('username', '')
    send_succeeded = False
    send_error_str = None

    # Rate limit: 20 sends per rolling 24h per user (audited via hd_email_log)
    try:
        since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        count_url = sb_url('hd_email_log',
            '?select=id&' + _sb_eq('sender_username', sender) +
            '&sent_at=gte.' + _url_quote(since, safe=''))
        count_resp = http.get(count_url, headers=sb_admin_headers(prefer='count=exact'), timeout=10)
        if count_resp.ok:
            count_header = count_resp.headers.get('Content-Range', '')
            sent_count = 0
            if '/' in count_header:
                try: sent_count = int(count_header.split('/')[-1])
                except ValueError: pass
            if sent_count >= 20:
                return jsonify({'ok': False, 'error': 'Daily email limit reached (20 per 24h).'}), 429
    except Exception:
        # Rate-limit table missing or unreachable — fail open so sends aren't blocked
        # by infra issues. Audit log call below will also no-op.
        pass

    try:
        token_json = os.environ.get('GMAIL_TOKEN_JSON', '')
        if not token_json:
            return jsonify({'ok': False, 'error': 'Gmail token not configured'}), 500
        creds = Credentials.from_authorized_user_info(json.loads(token_json))
        service = gmail_build('gmail', 'v1', credentials=creds)
        msg = MIMEMultipart()
        msg['to'] = data.get('to', '')
        msg['subject'] = data.get('subject', '')
        msg.attach(MIMEText(data.get('body', ''), 'plain'))
        if data.get('pdf_b64'):
            part = MIMEBase('application', 'pdf')
            part.set_payload(base64.b64decode(data['pdf_b64']))
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{data.get("pdf_filename","HD_Proposal.pdf")}"')
            msg.attach(part)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        send_succeeded = True
        return jsonify({'ok': True})
    except Exception as e:
        send_error_str = str(e)
        return _safe_error(e, context='send-email')
    finally:
        # Audit log every send attempt (best-effort)
        try:
            http.post(sb_url('hd_email_log'),
                      headers=sb_admin_headers(),
                      json={
                          'sender_username': sender,
                          'recipient_to': (data.get('to') or '')[:500],
                          'subject': (data.get('subject') or '')[:500],
                          'attachment_name': (data.get('pdf_filename') or '')[:500],
                          'success': send_succeeded,
                          'error': None if send_succeeded else (send_error_str or '')[:500]
                      }, timeout=10)
        except Exception:
            pass

# ── File Upload (Supabase Storage) ───────────────────────────────────────────

STORAGE_BUCKET = 'site-plans'
_bucket_ensured = False

def ensure_storage_bucket():
    """Create the storage bucket if it doesn't exist."""
    global _bucket_ensured
    if _bucket_ensured:
        return
    svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    try:
        r = http.post(
            f'{SUPABASE_URL}/storage/v1/bucket',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
            json={'id': STORAGE_BUCKET, 'name': STORAGE_BUCKET, 'public': True},
            timeout=10
        )
        # 200 = created, 409 = already exists — both fine
        if r.status_code in (200, 201, 409):
            _bucket_ensured = True
    except Exception:
        pass

@app.route('/upload/site-plan/<int:project_id>', methods=['POST'])
@require_auth
def upload_site_plan(project_id):
    """Upload a site plan to Supabase Storage, save URL in project snap."""
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'ok': False, 'error': 'Empty filename'}), 400

    # Check file size (50MB limit)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 50_000_000:
        return jsonify({'ok': False, 'error': 'File too large. Maximum 50MB.'}), 400

    # Determine content type
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'webp'}
    if ext not in allowed:
        return jsonify({'ok': False, 'error': f'File type .{ext} not supported. Use PNG, JPG, PDF, or WebP.'}), 400
    content_types = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'pdf': 'application/pdf', 'webp': 'image/webp'}
    ct = content_types.get(ext, 'application/octet-stream')

    # Ensure bucket exists
    ensure_storage_bucket()

    # Upload to Supabase Storage
    svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    file_path = f'project-{project_id}/site-plan.{ext}'
    try:
        file_data = file.read()
        # Upload (upsert)
        r = http.post(
            f'{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{file_path}',
            headers={
                'apikey': svc_key,
                'Authorization': f'Bearer {svc_key}',
                'Content-Type': ct,
                'x-upsert': 'true'
            },
            data=file_data,
            timeout=30
        )
        if r.status_code not in (200, 201):
            err_detail = r.text[:200] if r.text else 'Unknown error'
            return jsonify({'ok': False, 'error': f'Storage upload failed ({r.status_code}): {err_detail}'}), 500

        # Build public URL
        public_url = f'{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{file_path}'

        # Update project snap with site_plan_url
        proj_r = http.get(sb_url('proposals', '?' + _sb_eq('id', project_id) + '&' + 'select=snap'), headers=sb_headers(), timeout=5)
        rows = proj_r.json()
        if rows:
            snap = rows[0].get('snap') or {}
            if isinstance(snap, str):
                snap = json.loads(snap)
            snap['site_plan_url'] = public_url
            http.patch(
                sb_url('proposals', '?' + _sb_eq('id', project_id)),
                headers=sb_headers(),
                json={'snap': snap},
                timeout=5
            )

        return jsonify({'ok': True, 'url': public_url})
    except Exception as e:
        return _safe_error(e, context='upload/site-plan/<int:project_id>')

# ── Project File Attachments (Supabase Storage) ──────────────────────────────

FILES_BUCKET = 'project-files'
_files_bucket_ensured = False

def ensure_files_bucket():
    """Create the project-files storage bucket if it doesn't exist."""
    global _files_bucket_ensured
    if _files_bucket_ensured:
        return
    svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    try:
        r = http.post(
            f'{SUPABASE_URL}/storage/v1/bucket',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
            json={'id': FILES_BUCKET, 'name': FILES_BUCKET, 'public': True, 'file_size_limit': 10485760},
            timeout=10
        )
        if r.status_code in (200, 201, 409):
            _files_bucket_ensured = True
    except Exception:
        pass

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

@app.route('/upload/project-file/<int:project_id>', methods=['POST'])
@require_auth
def upload_project_file(project_id):
    """Upload a file attachment to a project. Max 10MB."""
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'ok': False, 'error': 'Empty filename'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt'}
    if ext not in allowed:
        return jsonify({'ok': False, 'error': f'File type .{ext} not supported.'}), 400

    content_types = {
        'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
        'gif': 'image/gif', 'webp': 'image/webp', 'pdf': 'application/pdf',
        'doc': 'application/msword', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'xls': 'application/vnd.ms-excel', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'csv': 'text/csv', 'txt': 'text/plain'
    }
    ct = content_types.get(ext, 'application/octet-stream')

    ensure_files_bucket()

    svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    file_data = file.read()
    if len(file_data) > MAX_FILE_SIZE:
        return jsonify({'ok': False, 'error': 'File exceeds 10 MB limit.'}), 400

    ts = int(time.time() * 1000)
    safe_name = secure_filename(file.filename) or 'upload'
    storage_path = f'project-{project_id}/files/{ts}-{safe_name}'

    try:
        r = http.post(
            f'{SUPABASE_URL}/storage/v1/object/{FILES_BUCKET}/{storage_path}',
            headers={
                'apikey': svc_key,
                'Authorization': f'Bearer {svc_key}',
                'Content-Type': ct,
                'x-upsert': 'true'
            },
            data=file_data,
            timeout=30
        )
        if r.status_code not in (200, 201):
            err_detail = r.text[:200] if r.text else 'Unknown error'
            return jsonify({'ok': False, 'error': f'Upload failed ({r.status_code}): {err_detail}'}), 500

        public_url = f'{SUPABASE_URL}/storage/v1/object/public/{FILES_BUCKET}/{storage_path}'

        # Append file metadata to project snap.files[]
        proj_r = http.get(sb_url('proposals', '?' + _sb_eq('id', project_id) + '&' + 'select=snap'), headers=sb_headers(), timeout=5)
        rows = proj_r.json()
        if rows:
            snap = rows[0].get('snap') or {}
            if isinstance(snap, str):
                snap = json.loads(snap)
            if 'files' not in snap:
                snap['files'] = []
            snap['files'].append({
                'name': file.filename,
                'url': public_url,
                'path': storage_path,
                'size': len(file_data),
                'type': ext,
                'uploaded_by': session.get('username', ''),
                'uploaded_at': datetime.now().isoformat()
            })
            http.patch(
                sb_url('proposals', '?' + _sb_eq('id', project_id)),
                headers=sb_headers(),
                json={'snap': snap},
                timeout=5
            )

        return jsonify({'ok': True, 'url': public_url, 'name': file.filename, 'path': storage_path, 'size': len(file_data), 'type': ext})
    except Exception as e:
        return _safe_error(e, context='upload/project-file/<int:project_id>')


@app.route('/upload/project-file/<int:project_id>/delete', methods=['POST'])
@require_auth
def delete_project_file(project_id):
    """Delete a file attachment from a project."""
    data = request.get_json() or {}
    storage_path = data.get('path', '')
    if not storage_path:
        return jsonify({'ok': False, 'error': 'No path provided'}), 400
    # Verify the path belongs to this project
    if not storage_path.startswith(f'project-{project_id}/'):
        return jsonify({'ok': False, 'error': 'Access denied'}), 403

    svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    try:
        # Delete from Supabase Storage
        http.delete(
            f'{SUPABASE_URL}/storage/v1/object/{FILES_BUCKET}/{storage_path}',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}'},
            timeout=10
        )

        # Remove from project snap.files[]
        proj_r = http.get(sb_url('proposals', '?' + _sb_eq('id', project_id) + '&' + 'select=snap'), headers=sb_headers(), timeout=5)
        rows = proj_r.json()
        if rows:
            snap = rows[0].get('snap') or {}
            if isinstance(snap, str):
                snap = json.loads(snap)
            snap['files'] = [f for f in (snap.get('files') or []) if f.get('path') != storage_path]
            http.patch(
                sb_url('proposals', '?' + _sb_eq('id', project_id)),
                headers=sb_headers(),
                json={'snap': snap},
                timeout=5
            )

        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='upload/project-file/<int:project_id>/delete')


# ── Setup: create hd_settings table if needed ───────────────────────────────

@app.route('/setup/settings-table', methods=['POST'])
@require_dev
def setup_settings_table():
    """Create hd_settings table via Supabase SQL. Run once."""
    sql = """
    CREATE TABLE IF NOT EXISTS hd_settings (
        key TEXT PRIMARY KEY,
        value JSONB,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    ALTER TABLE hd_settings DISABLE ROW LEVEL SECURITY;
    """
    try:
        svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
        r = http.post(
            f'{SUPABASE_URL}/rest/v1/rpc/exec_sql',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
            json={'query': sql}, timeout=10
        )
        # If rpc doesn't exist, try the SQL endpoint
        if r.status_code != 200:
            r2 = http.post(
                f'{SUPABASE_URL}/pg/query',
                headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
                json={'query': sql}, timeout=10
            )
            if r2.status_code == 200:
                return jsonify({'ok': True, 'method': 'pg/query'})
            return jsonify({'ok': False, 'error': 'Could not create table automatically. Please run the SQL manually in Supabase dashboard.', 'sql': sql.strip()})
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/setup/user-fields', methods=['POST'])
@require_dev
def setup_user_fields():
    """Add profile fields and update role constraint to include 'field'."""
    sql = """
    ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS email TEXT DEFAULT '';
    ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT '';
    ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS avatar_data TEXT DEFAULT '';
    ALTER TABLE hd_users DROP CONSTRAINT IF EXISTS hd_users_role_check;
    ALTER TABLE hd_users ADD CONSTRAINT hd_users_role_check CHECK (role IN ('admin', 'user', 'field', 'dev'));
    """
    try:
        svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
        r = http.post(
            f'{SUPABASE_URL}/rest/v1/rpc/exec_sql',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
            json={'query': sql}, timeout=10
        )
        if r.status_code != 200:
            r2 = http.post(
                f'{SUPABASE_URL}/pg/query',
                headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
                json={'query': sql}, timeout=10
            )
            if r2.status_code == 200:
                return jsonify({'ok': True, 'method': 'pg/query'})
            return jsonify({'ok': False, 'error': 'Run this SQL manually in Supabase: ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS email TEXT DEFAULT \'\'; ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT \'\'; ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS avatar_data TEXT DEFAULT \'\';'})
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

# ── Notifications ─────────────────────────────────────────────────────────────

_notif_table_ensured = False
_NOTIF_SQL = """
CREATE TABLE IF NOT EXISTS hd_notifications (
    id SERIAL PRIMARY KEY,
    recipient TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    project_id INT,
    project_name TEXT DEFAULT '',
    link TEXT DEFAULT '',
    read BOOLEAN DEFAULT FALSE,
    dismissed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT DEFAULT ''
);
ALTER TABLE hd_notifications DISABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_notif_recipient ON hd_notifications(recipient, dismissed, created_at DESC);
"""

def ensure_notif_table():
    """Auto-create hd_notifications table if it doesn't exist."""
    global _notif_table_ensured
    if _notif_table_ensured:
        return True
    svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    # Quick check: try to query the table
    try:
        r = http.get(sb_url('hd_notifications', '?select=id&limit=1'), headers=sb_headers(), timeout=5)
        if r.status_code == 200:
            _notif_table_ensured = True
            return True
    except Exception:
        pass
    # Table doesn't exist — try to create it
    try:
        r = http.post(f'{SUPABASE_URL}/rest/v1/rpc/exec_sql',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
            json={'query': _NOTIF_SQL}, timeout=10)
        if r.status_code == 200:
            _notif_table_ensured = True
            return True
        r2 = http.post(f'{SUPABASE_URL}/pg/query',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
            json={'query': _NOTIF_SQL}, timeout=10)
        if r2.status_code == 200:
            _notif_table_ensured = True
            return True
    except Exception:
        pass
    return False

@app.route('/setup/notifications-table', methods=['POST'])
@require_dev
def setup_notifications_table():
    """Create hd_notifications table. Run once."""
    if ensure_notif_table():
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Run this SQL manually in Supabase dashboard.', 'sql': _NOTIF_SQL.strip()})

@app.route('/setup/migrate-roles', methods=['POST'])
@require_dev
def setup_migrate_roles():
    """Update role constraint, set justin.ledwein to dev, create new tables, add pipeline stage."""
    sql = """
    ALTER TABLE hd_users DROP CONSTRAINT IF EXISTS hd_users_role_check;
    ALTER TABLE hd_users ADD CONSTRAINT hd_users_role_check CHECK (role IN ('admin', 'user', 'field', 'dev'));
    UPDATE hd_users SET role = 'dev' WHERE username = 'justin.ledwein';
    CREATE TABLE IF NOT EXISTS hd_feedback (
        id BIGSERIAL PRIMARY KEY,
        message TEXT NOT NULL,
        submitted_by TEXT NOT NULL,
        submitted_at TIMESTAMPTZ DEFAULT NOW()
    );
    ALTER TABLE hd_feedback DISABLE ROW LEVEL SECURITY;
    UPDATE pipeline_stages SET position = position + 1 WHERE position >= 4;
    INSERT INTO pipeline_stages (name, color, position, counts_in_ratio, is_closed)
    SELECT 'Waiting for Approval', '#FF8C00', 4, false, false
    WHERE NOT EXISTS (SELECT 1 FROM pipeline_stages WHERE name = 'Waiting for Approval');
    """
    try:
        svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
        r = http.post(
            f'{SUPABASE_URL}/rest/v1/rpc/exec_sql',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}', 'Content-Type': 'application/json'},
            json={'query': sql}, timeout=10
        )
        if r.status_code == 200:
            return jsonify({'ok': True, 'method': 'exec_sql'})
        return jsonify({'ok': False, 'error': 'exec_sql RPC not available. Run this SQL manually in Supabase dashboard.', 'sql': sql.strip()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/notifications/list')
@require_auth
def notifications_list():
    """Get notifications for the current user."""
    username = session.get('username', '')
    try:
        r = http.get(
            sb_url('hd_notifications', '?' + _sb_eq('recipient', username) + '&' + 'dismissed=eq.false&' + 'order=created_at.desc&' + 'limit=50'),
            headers=sb_headers(), timeout=5)
        if r.status_code == 200:
            return jsonify({'ok': True, 'notifications': r.json()})
        # Table probably doesn't exist
        return jsonify({'ok': True, 'notifications': [], 'needs_setup': True,
                       'setup_sql': _NOTIF_SQL.strip()})
    except Exception as e:
        return jsonify({'ok': True, 'notifications': [], 'needs_setup': True,
                       'setup_sql': _NOTIF_SQL.strip(), 'error': str(e)})


@app.route('/notifications/debug')
@require_auth
def notifications_debug():
    """Debug endpoint to check notification table status."""
    username = session.get('username', '')
    results = {'username': username}
    try:
        url = sb_url('hd_notifications', '?select=*&limit=5')
        results['query_url'] = url
        r = http.get(url, headers=sb_headers(), timeout=5)
        results['status_code'] = r.status_code
        results['response_body'] = r.text[:500]
        results['response_headers'] = dict(r.headers)
    except Exception as e:
        results['error'] = str(e)
    return jsonify(results)

@app.route('/notifications/unread-count')
@require_auth
def notifications_unread_count():
    username = session.get('username', '')
    try:
        r = http.get(
            sb_url('hd_notifications', '?' + _sb_eq('recipient', username) + '&' + 'dismissed=eq.false&' + 'read=eq.false&' + 'select=id'),
            headers=sb_headers(), timeout=5)
        count = len(r.json()) if r.status_code == 200 else 0
        return jsonify({'ok': True, 'count': count})
    except Exception as e:
        return jsonify({'ok': True, 'count': 0})


@app.route('/notifications/read/<int:nid>', methods=['POST'])
@require_auth
def notifications_read(nid):
    try:
        http.patch(sb_url('hd_notifications', '?' + _sb_eq('id', nid)), headers=sb_headers(), json={'read': True}, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='notifications/read/<int:nid>')


@app.route('/notifications/read-all', methods=['POST'])
@require_auth
def notifications_read_all():
    username = session.get('username', '')
    try:
        http.patch(sb_url('hd_notifications', '?' + _sb_eq('recipient', username) + '&' + 'read=eq.false'),
            headers=sb_headers(), json={'read': True}, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='notifications/read-all')


@app.route('/notifications/dismiss/<int:nid>', methods=['POST'])
@require_auth
def notifications_dismiss(nid):
    try:
        http.patch(sb_url('hd_notifications', '?' + _sb_eq('id', nid)), headers=sb_headers(), json={'dismissed': True}, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='notifications/dismiss/<int:nid>')


@app.route('/notifications/send', methods=['POST'])
@require_auth
def notifications_send():
    """Create notifications — used for @mentions, assignments, stage changes, etc."""
    data = request.get_json() or {}
    recipients = data.get('recipients', [])
    ntype = data.get('type', 'info')
    title = data.get('title', '')
    body = data.get('body', '')
    project_id = data.get('project_id')
    project_name = data.get('project_name', '')
    email_notify = data.get('email_notify', False)
    created_by = session.get('username', '')
    if not recipients or not title:
        return jsonify({'ok': False, 'error': 'recipients and title required'}), 400
    try:
        # If '_all' is in recipients, expand to all active users
        if '_all' in recipients:
            r = http.get(sb_url('hd_users', '?active=eq.true&select=username'), headers=sb_headers(), timeout=5)
            all_users = r.json() if r.status_code == 200 else []
            recipients = [u['username'] for u in all_users]

        rows = [{'recipient': r, 'type': ntype, 'title': title, 'body': body,
                 'project_id': project_id, 'project_name': project_name,
                 'created_by': created_by} for r in recipients if r != created_by]
        if rows:
            http.post(sb_url('hd_notifications', ''), headers=sb_headers(), json=rows, timeout=10)

        # Send email notifications if requested
        if email_notify and GMAIL_AVAILABLE:
            _send_notif_emails(recipients, created_by, title, body, project_name)

        return jsonify({'ok': True, 'sent': len(rows)})
    except Exception as e:
        return _safe_error(e, context='notifications/send')


def _send_notif_emails(recipients, created_by, title, body, project_name):
    """Send email alerts for notifications to recipients who have emails on file."""
    try:
        import base64
        from email.mime.text import MIMEText
        token_json = os.environ.get('GMAIL_TOKEN_JSON', '')
        if not token_json:
            return
        creds = Credentials.from_authorized_user_info(json.loads(token_json))
        service = gmail_build('gmail', 'v1', credentials=creds)
        # Look up emails for recipients
        for username in recipients:
            if username == created_by:
                continue
            r = http.get(sb_url('hd_users', '?' + _sb_eq('username', username) + '&' + 'select=email,full_name'), headers=sb_headers(), timeout=5)
            users = r.json() if r.status_code == 200 else []
            if not users or not users[0].get('email'):
                continue
            email_addr = users[0]['email']
            full_name = users[0].get('full_name', username)
            subject = f'HD Hauling — {title}'
            email_body = f'Hi {full_name},\n\n{title}\n'
            if body:
                email_body += f'\n{body}\n'
            if project_name:
                email_body += f'\nProject: {project_name}\n'
            email_body += '\n— HD Hauling & Grading'
            msg = MIMEText(email_body, 'plain')
            msg['to'] = email_addr
            msg['subject'] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
    except Exception as e:
        app.logger.error(f'Email notification error: {e}')


# ── Settings (shared key/value store in hd_settings table) ──────────────────

@app.route('/settings/get/<key>')
@require_auth
def settings_get(key):
    try:
        r = http.get(sb_url('hd_settings', '?' + _sb_eq('key', key) + '&' + 'select=value'), headers=sb_headers(), timeout=5)
        rows = r.json()
        if rows and len(rows) > 0:
            return jsonify({'ok': True, 'value': rows[0]['value']})
        return jsonify({'ok': True, 'value': None})
    except Exception as e:
        return _safe_error(e, context='settings/get/<key>')

@app.route('/settings/bulk', methods=['POST'])
@require_auth
def settings_bulk_get():
    """Get multiple settings keys at once."""
    data = request.get_json() or {}
    keys = data.get('keys', [])
    if not keys:
        return jsonify({'ok': True, 'values': {}})
    try:
        key_filter = ','.join(keys)
        r = http.get(sb_url('hd_settings', '?' + f'key=in.({key_filter})' + '&' + 'select=key,value'), headers=sb_headers(), timeout=5)
        rows = r.json()
        values = {row['key']: row['value'] for row in rows}
        return jsonify({'ok': True, 'values': values})
    except Exception as e:
        return _safe_error(e, context='settings/bulk')

@app.route('/settings/save', methods=['POST'])
@require_auth
def settings_save():
    data = request.get_json() or {}
    key = data.get('key')
    value = data.get('value')
    if not key:
        return jsonify({'ok': False, 'error': 'Missing key'}), 400
    # Personal settings any user can save
    personal_keys = {'hd_notif_prefs', 'hd_sender', 'hd_dark_mode', 'hd_auto_logout', 'hd_sb_pinned', 'hd_subcontractors'}
    # Client notes are dynamic keys (hd_client_notes_*)
    is_personal = key in personal_keys or key.startswith('hd_client_notes_')
    # Shared business settings require admin role
    if not is_personal and session.get('role') not in ('admin', 'dev'):
        return jsonify({'ok': False, 'error': 'Admin access required to change app settings'}), 403
    try:
        # Upsert: try to update, if not found insert
        h = sb_headers()
        h['Prefer'] = 'return=representation,resolution=merge-duplicates'
        r = http.post(sb_url('hd_settings'), headers=h, json={'key': key, 'value': value}, timeout=5)
        if r.status_code in (200, 201):
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': f'Supabase returned {r.status_code}: {r.text}'}), 500
    except Exception as e:
        return _safe_error(e, context='settings/save')

@app.route('/settings/approval-group', methods=['GET'])
@require_auth
def get_approval_group():
    try:
        r = http.get(sb_url('hd_settings', '?key=eq.approval_group&select=value'), headers=sb_headers(), timeout=5)
        rows = r.json() if r.status_code == 200 else []
        return jsonify({'ok': True, 'approvers': rows[0]['value'] if rows else []})
    except Exception as e:
        return _safe_error(e, context='settings/approval-group')

@app.route('/settings/approval-group', methods=['POST'])
@require_dev
def save_approval_group():
    data = request.get_json() or {}
    approvers = data.get('approvers', [])
    try:
        h = sb_headers()
        h['Prefer'] = 'return=representation,resolution=merge-duplicates'
        r = http.post(sb_url('hd_settings'), headers=h, json={'key': 'approval_group', 'value': approvers}, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='settings/approval-group')

@app.route('/schedule/feed-token')
@require_auth
def schedule_feed_token():
    token = hashlib.sha256(app.secret_key.encode()).hexdigest()[:16]
    return jsonify({'token': token})

@app.route('/schedule/feed.ics')
def schedule_ics_feed():
    """Live ICS feed of all scheduled work orders. Google Calendar can subscribe to this URL."""
    token = request.args.get('token', '')
    expected = hashlib.sha256(app.secret_key.encode()).hexdigest()[:16]
    if token != expected:
        return 'Unauthorized', 401
    try:
        r = http.get(
            sb_url('proposals', '?select=id,name,client,snap&order=created_at.desc'),
            headers=sb_headers(), timeout=15
        )
        r.raise_for_status()
        proposals = r.json()
    except Exception:
        proposals = []

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//HD Hauling & Grading//Work Orders//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:HD Work Orders',
        'X-WR-TIMEZONE:America/New_York',
    ]
    for p in proposals:
        snap = p.get('snap') or {}
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except Exception:
                snap = {}
        if not snap.get('is_project'):
            continue
        for wo in snap.get('work_orders', []):
            if not wo.get('scheduled_date'):
                continue
            d = wo['scheduled_date'].replace('-', '')
            uid = f"wo-{wo.get('id', '')}-{p['id']}@hdhauling"
            lines.append('BEGIN:VEVENT')
            lines.append(f'UID:{uid}')
            if wo.get('scheduled_time'):
                t = wo['scheduled_time'].replace(':', '') + '00'
                lines.append(f'DTSTART;TZID=America/New_York:{d}T{t}')
                lines.append(f'DTEND;TZID=America/New_York:{d}T{t}')
            else:
                lines.append(f'DTSTART;VALUE=DATE:{d}')
                lines.append(f'DTEND;VALUE=DATE:{d}')
            summary = f"{p.get('name', 'Project')} — {wo.get('name', 'Work Order')}"
            lines.append(f'SUMMARY:{summary}')
            desc_parts = []
            if wo.get('assigned_to'):
                desc_parts.append(f"Crew: {wo['assigned_to']}")
            if wo.get('onsite_contact'):
                contact = wo['onsite_contact']
                if wo.get('onsite_phone'):
                    contact += f" ({wo['onsite_phone']})"
                desc_parts.append(f"Contact: {contact}")
            if wo.get('description'):
                desc_parts.append(wo['description'])
            if desc_parts:
                lines.append('DESCRIPTION:' + '\\n'.join(desc_parts).replace('\n', '\\n'))
            addr = snap.get('address', '')
            if snap.get('city_state'):
                addr += (', ' if addr else '') + snap['city_state']
            if addr:
                lines.append(f'LOCATION:{addr}')
            status_map = {'active': 'CONFIRMED', 'complete': 'COMPLETED', 'pending': 'TENTATIVE'}
            lines.append(f'STATUS:{status_map.get(wo.get("status", ""), "TENTATIVE")}')
            lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')

    from flask import Response
    return Response(
        '\r\n'.join(lines),
        mimetype='text/calendar',
        headers={'Content-Disposition': 'inline; filename="hd_schedule.ics"'}
    )

# ── Bug Reports ──────────────────────────────────────────
@app.route('/bugs/submit', methods=['POST'])
@require_auth
def submit_bug():
    try:
        d = request.json or {}
        row = {
            'title': d.get('title', '').strip(),
            'description': d.get('description', '').strip(),
            'severity': d.get('severity', 'Minor'),
            'panel': d.get('panel', ''),
            'status': 'Open',
            'submitted_by': session.get('username', 'unknown'),
            'browser_info': d.get('browser_info', ''),
            'screen_info': d.get('screen_info', '')
        }
        if not row['title']:
            return jsonify({'ok': False, 'error': 'Title is required'}), 400
        r = http.post(f"{SUPABASE_URL}/rest/v1/hd_bug_reports", json=row, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to save bug report', 'details': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='bugs/submit')

@app.route('/bugs/list')
@require_dev
def list_bugs():
    try:
        r = http.get(sb_url('hd_bug_reports', "?" + "select=*&" + "order=submitted_at.desc"), headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': 'Failed to load bug reports', 'details': r.text[:500]}), r.status_code
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return _safe_error(e, context='bugs/list')

@app.route('/bugs/<int:bug_id>', methods=['PATCH'])
@require_dev
def update_bug(bug_id):
    try:
        d = request.json or {}
        updates = {}
        if 'status' in d:
            updates['status'] = d['status']
            if d['status'] in ('Fixed', 'Closed'):
                updates['resolved_at'] = datetime.utcnow().isoformat()
            else:
                updates['resolved_at'] = None
        if 'admin_notes' in d:
            updates['admin_notes'] = d['admin_notes']
        r = http.patch(sb_url('hd_bug_reports', "?" + _sb_eq('id', bug_id)), json=updates, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to update bug report', 'details': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='bugs/<int:bug_id>')

# ── Feedback ─────────────────────────────────────────────
@app.route('/feedback/submit', methods=['POST'])
@require_auth
def submit_feedback():
    d = request.get_json() or {}
    message = d.get('message', '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'Message required'}), 400
    row = {'message': message, 'submitted_by': session.get('username', '')}
    try:
        r = http.post(sb_url('hd_feedback', ''), headers=sb_headers(), json=row, timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to save feedback'}), 500
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='feedback/submit')

@app.route('/feedback/list')
@require_auth
def list_feedback():
    username = session.get('username', '')
    role = session.get('role', 'user')
    try:
        if role == 'dev':
            r = http.get(sb_url('hd_feedback', '?select=*&order=submitted_at.desc&limit=200'), headers=sb_headers(), timeout=10)
        else:
            r = http.get(sb_url('hd_feedback', '?' + _sb_eq('submitted_by', username) + '&' + 'select=*&' + 'order=submitted_at.desc&' + 'limit=200'), headers=sb_headers(), timeout=10)
        return jsonify({'ok': True, 'items': r.json() if r.status_code == 200 else []})
    except Exception as e:
        return _safe_error(e, context='feedback/list')

# ── Roadmap ──────────────────────────────────────────────
@app.route('/roadmap/list')
@require_dev
def list_roadmap():
    try:
        r = http.get(sb_url('hd_roadmap', "?" + "select=*&" + "order=sort_order.asc,created_at.desc"), headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': 'Failed to load roadmap items', 'details': r.text[:500]}), r.status_code
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return _safe_error(e, context='roadmap/list')

@app.route('/roadmap/save', methods=['POST'])
@require_dev
def save_roadmap():
    try:
        d = request.json or {}
        row = {
            'title': d.get('title', '').strip(),
            'description': d.get('description', '').strip(),
            'category': d.get('category', 'Feature'),
            'priority': d.get('priority', 'Medium'),
            'effort': d.get('effort', 'Medium'),
            'status': d.get('status', 'Planned'),
            'target_version': d.get('target_version', ''),
            'sort_order': d.get('sort_order', 0)
        }
        if not row['title']:
            return jsonify({'ok': False, 'error': 'Title is required'}), 400
        r = http.post(f"{SUPABASE_URL}/rest/v1/hd_roadmap", json=row, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to save roadmap item', 'details': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='roadmap/save')

@app.route('/roadmap/<int:item_id>', methods=['PATCH'])
@require_dev
def update_roadmap(item_id):
    try:
        d = request.json or {}
        updates = {}
        for k in ('title', 'description', 'category', 'priority', 'effort', 'status', 'target_version', 'sort_order'):
            if k in d:
                updates[k] = d[k]
        updates['updated_at'] = datetime.utcnow().isoformat()
        r = http.patch(sb_url('hd_roadmap', "?" + _sb_eq('id', item_id)), json=updates, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to update roadmap item', 'details': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='roadmap/<int:item_id>')

@app.route('/roadmap/<int:item_id>', methods=['DELETE'])
@require_dev
def delete_roadmap(item_id):
    try:
        r = http.delete(sb_url('hd_roadmap', "?" + _sb_eq('id', item_id)), headers=sb_admin_headers(prefer='return=minimal'), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to delete roadmap item', 'details': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='roadmap/<int:item_id>')

# ── Public Proposal Sharing & Approval ────────────────────
@app.route('/proposal/share/<int:pid>', methods=['POST'])
@require_auth
def share_proposal(pid):
    """Generate a share token for a proposal."""
    try:
        token = uuid.uuid4().hex
        r = http.patch(
            sb_url('proposals', '?' + _sb_eq('id', pid)),
            headers=sb_headers(),
            json={'share_token': token},
            timeout=10
        )
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True, 'token': token})
    except Exception as e:
        return _safe_error(e, context='proposal/share/<int:pid>')

@app.route('/proposal/view/<token>')
def public_proposal_view(token):
    """Public route — no auth. Returns proposal data for shared link.
    Whitelists the fields we expose so internal metadata (stage_id, created_by,
    archived flags, share_token itself) never leaks to the client-view."""
    # Token is uuid hex — reject anything that isn't 32 hex chars early
    if not token or len(token) < 16 or not all(c in '0123456789abcdef' for c in token.lower()):
        return jsonify({'ok': False, 'error': 'Proposal not found'}), 404
    try:
        r = http.get(
            sb_url('proposals', '?' + _sb_eq('share_token', token) + '&' + 'select=id,name,client,date,total,snap,project_number'),
            headers=sb_admin_headers(), timeout=10
        )
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': 'Proposal not found'}), 404
        items = r.json()
        if not items:
            return jsonify({'ok': False, 'error': 'Proposal not found'}), 404
        prop = items[0]
        # Also sanitize the nested snap: strip internal activity_log + cost breakdown fields
        snap = prop.get('snap') or {}
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except Exception:
                snap = {}
        # Drop internal fields — leave only what the client view needs
        for internal_key in ('activity_log', 'internal_notes', 'crew_assignments'):
            snap.pop(internal_key, None)
        prop['snap'] = snap
        return jsonify({'ok': True, 'proposal': prop})
    except Exception:
        return jsonify({'ok': False, 'error': 'Proposal not found'}), 404

@app.route('/proposal/approve/<token>', methods=['POST'])
def public_proposal_approve(token):
    """Public route — no auth. Client approves a shared proposal.
    Rejects if already approved, so a leaked link can't be replayed to pollute
    the activity log or spam the project owner with notifications."""
    # Token format sanity-check
    if not token or len(token) < 16 or not all(c in '0123456789abcdef' for c in token.lower()):
        return jsonify({'ok': False, 'error': 'Proposal not found'}), 404
    # Rate limit by IP to prevent approval spam even from a valid token
    try:
        from security import rate_limit_check
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
        allowed, retry = rate_limit_check(f'approve:{ip}', max_attempts=10, window_s=600)
        if not allowed:
            return jsonify({'ok': False, 'error': f'Too many requests. Try again in {retry}s.'}), 429
    except ImportError:
        pass  # security.py not yet deployed; skip limiter
    try:
        d = request.json or {}
        approver_name = str(d.get('name', '')).strip()[:120]
        comment = str(d.get('comment', '')).strip()[:2000]
        if not approver_name:
            return jsonify({'ok': False, 'error': 'Your name is required to approve'}), 400
        # Find the proposal
        r = http.get(
            sb_url('proposals', '?' + _sb_eq('share_token', token) + '&' + 'select=id,snap,stage_id,created_by,name'),
            headers=sb_admin_headers(), timeout=10
        )
        items = r.json() if r.status_code == 200 else []
        if not items:
            return jsonify({'ok': False, 'error': 'Proposal not found'}), 404
        prop = items[0]
        pid = prop['id']
        owner = prop.get('created_by', '')
        proj_name = prop.get('name', '')
        snap = json.loads(prop['snap']) if isinstance(prop.get('snap'), str) else (prop.get('snap') or {})
        # Reject double-approval — once approved, the link is spent
        if snap.get('approved_by') or snap.get('approved_at'):
            return jsonify({'ok': False, 'error': 'This proposal has already been approved.'}), 409
        # Record approval in snap
        snap['approved_by'] = approver_name
        snap['approved_at'] = datetime.utcnow().isoformat()
        if comment:
            snap['approval_comment'] = comment
        # Add activity log entry
        if 'activity_log' not in snap:
            snap['activity_log'] = []
        snap['activity_log'].append({
            'type': 'approval',
            'text': f'Client "{approver_name}" approved the proposal' + (f': "{comment}"' if comment else ''),
            'date': datetime.utcnow().isoformat(),
            'user': 'client'
        })
        # Find "Won" stage
        sr = http.get(
            sb_url('pipeline_stages', '?name=eq.Won&select=id'),
            headers=sb_headers(), timeout=5
        )
        stage_update = {}
        if sr.status_code == 200 and sr.json():
            stage_update['stage_id'] = sr.json()[0]['id']
        # Update proposal
        update = {'snap': json.dumps(snap)}
        update.update(stage_update)
        r2 = http.patch(
            sb_url('proposals', '?' + _sb_eq('id', pid)),
            headers=sb_admin_headers(),
            json=update, timeout=10
        )
        if r2.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to save approval'}), 400
        # Send notification to project owner
        if owner:
            notif_title = f'Proposal approved by {approver_name}'
            notif_body = f'{proj_name or "A proposal"} was approved by the client.'
            if comment:
                notif_body += f' Comment: "{comment}"'
            notif_row = {
                'recipient': owner,
                'type': 'success',
                'title': notif_title,
                'body': notif_body,
                'project_id': pid,
                'project_name': proj_name,
                'created_by': 'system'
            }
            http.post(sb_url('hd_notifications', ''), headers=sb_headers(), json=notif_row, timeout=5)
        return jsonify({'ok': True, 'message': 'Proposal approved'})
    except Exception as e:
        # Don't leak stack/DB details to an unauthenticated caller
        print(f'[public_proposal_approve] {type(e).__name__}: {e}')
        return jsonify({'ok': False, 'error': 'Could not record approval. Try again.'}), 500

@app.route('/p/<token>')
def public_proposal_page(token):
    """Serve the public proposal viewer page."""
    return send_file('proposal_view.html')

# ── Lead Intake ───────────────────────────────────────────
@app.route('/lead-form')
def lead_form_page():
    """Serve the public lead intake form."""
    return send_file('lead_form.html')

@app.route('/leads/submit', methods=['POST'])
def submit_lead():
    """Public route — no auth. Accept lead from public form.
    Rate-limited by IP and hard-capped on field lengths to prevent spam / abuse."""
    # Rate limit per IP (10 / 10 min)
    try:
        from security import rate_limit_check
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
        allowed, retry = rate_limit_check(f'lead:{ip}', max_attempts=10, window_s=600)
        if not allowed:
            return jsonify({'ok': False, 'error': f'Too many submissions. Try again in {retry}s.'}), 429
    except ImportError:
        pass  # security.py not yet deployed; skip limiter
    try:
        d = request.json or {}
        # Honeypot: bots fill hidden fields. Return success so they don't retry,
        # but skip all DB writes and notifications.
        if _honeypot_tripped(d):
            ip_for_log = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
            app.logger.info('[honeypot] /leads/submit rejected submission from %s', ip_for_log)
            return jsonify({'ok': True})
        # Cap all text fields to prevent DB/DoS abuse
        name = str(d.get('name', '')).strip()[:200]
        email = str(d.get('email', '')).strip()[:200]
        phone_raw = str(d.get('phone', '')).strip()[:40]
        if not name:
            return jsonify({'ok': False, 'error': 'Name is required.'}), 400
        if not _valid_email(email):
            return jsonify({'ok': False, 'error': 'Please enter a valid email address.'}), 400
        phone = _normalize_phone(phone_raw)
        if not phone:
            return jsonify({'ok': False, 'error': 'Please enter a valid 10-digit phone number.'}), 400
        # Try to match existing client by email or phone
        matched_client_id = None
        if email:
            cr = http.get(sb_url('clients', '?' + _sb_eq('email', email) + '&' + 'select=id,name&' + 'limit=1'), headers=sb_admin_headers(), timeout=5)
            if cr.status_code == 200 and cr.json():
                matched_client_id = cr.json()[0]['id']
        if not matched_client_id and phone:
            cr = http.get(sb_url('clients', '?' + _sb_eq('phone', phone) + '&' + 'select=id,name&' + 'limit=1'), headers=sb_admin_headers(), timeout=5)
            if cr.status_code == 200 and cr.json():
                matched_client_id = cr.json()[0]['id']
        row = {
            'name': name,
            'company': str(d.get('company', '')).strip()[:200],
            'email': email,
            'phone': phone,
            'address': str(d.get('address', '')).strip()[:500],
            'description': str(d.get('description', '')).strip()[:4000],
            'source': str(d.get('source', '')).strip()[:100],
            'status': 'new',
            'matched_client_id': matched_client_id
        }
        r = http.post(f"{SUPABASE_URL}/rest/v1/hd_leads", json=row, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to save lead'}), 400
        # Notify all admins and standard users
        try:
            ur = http.get(sb_url('hd_users', '?active=eq.true&role=neq.field&select=username'), headers=sb_admin_headers(), timeout=5)
            if ur.status_code == 200 and ur.json():
                company = str(d.get('company', '')).strip()
                notif_title = f'New lead: {name}' + (f' ({company})' if company else '')
                notif_body = str(d.get('description', '')).strip()[:200] or 'New quote request from the website'
                notif_rows = [{'recipient': u['username'], 'type': 'info', 'title': notif_title, 'body': notif_body, 'created_by': 'system'} for u in ur.json()]
                if notif_rows:
                    http.post(sb_url('hd_notifications', ''), headers=sb_headers(), json=notif_rows, timeout=5)
        except Exception:
            pass  # Don't fail the lead submission if notification fails
        # Email notification to admin@hdgrading.com (best-effort)
        try:
            _send_lead_email(row)
        except Exception:
            pass
        return jsonify({'ok': True})
    except Exception as e:
        print(f'[submit_lead] {type(e).__name__}: {e}')
        return jsonify({'ok': False, 'error': 'Could not save lead. Please try again.'}), 500

LEAD_EMAIL_FROM = 'HD Hauling & Grading <admin@hdgrading.com>'
# Always-on recipient for new lead notifications. Goes on every lead email
# regardless of any user's opt-in prefs (shared inbox for estimating team).
LEAD_ALWAYS_TO = 'estimates@hdgrading.com'
def _users_opted_in(email_pref_key, default=False):
    """Return a list of (email, full_name) tuples for active office users
    (role in admin/user/dev) whose notif_prefs.email[pref_key] is True, OR is
    unset and `default` is True (used for opt-in-by-default keys like
    'new_applicants')."""
    try:
        r = http.get(sb_url('hd_users',
            '?active=eq.true&role=in.(admin,user,dev)'
            '&select=email,full_name,notif_prefs'),
            headers=sb_admin_headers(), timeout=5)
        if r.status_code != 200:
            return []
        out = []
        for u in r.json():
            em = (u.get('email') or '').strip()
            if not em:
                continue
            prefs = u.get('notif_prefs') or {}
            email_prefs = prefs.get('email') or {}
            pref_val = email_prefs.get(email_pref_key)
            if pref_val is True or (pref_val is None and default):
                out.append((em, u.get('full_name') or em))
        return out
    except Exception as e:
        print(f'[_users_opted_in] {type(e).__name__}: {e}')
        return []

def _render_form_email_html(*, title, name, subtitle, rows, badges=None,
                             free_text_label=None, free_text=None,
                             cta_label, cta_url):
    """Return inline-CSS HTML for a branded form-submission email.

    - title: red-bar header title ('New Quote Request' / 'New Job Application')
    - name: big headline (the submitter's name)
    - subtitle: below name (company for leads, position for applicants)
    - rows: list of (label, value) tuples; value=None/empty renders as em-dash
    - badges: optional list of (label, True/False) for eligibility pills
    - free_text_label/free_text: optional blockquote section (desc/note)
    - cta_label/cta_url: red action button
    """
    esc = html.escape
    row_cells = []
    for i, (label, value) in enumerate(rows):
        bg = '#f9fafb' if (i % 2) else '#ffffff'
        display = esc(str(value)) if value not in (None, '', '—') else '<span style="color:#9ca3af;">—</span>'
        row_cells.append(
            f'<tr style="background:{bg};">'
            f'<td style="padding:10px 14px;color:#6b7280;font-size:11px;'
            f'text-transform:uppercase;letter-spacing:0.4px;font-weight:700;'
            f'width:38%;vertical-align:top;border-top:1px solid #e5e7eb;">{esc(label)}</td>'
            f'<td style="padding:10px 14px;color:#111827;font-size:14px;'
            f'vertical-align:top;border-top:1px solid #e5e7eb;">{display}</td>'
            f'</tr>'
        )
    rows_block = ''.join(row_cells)

    badges_block = ''
    if badges:
        pills = []
        for label, is_true in badges:
            bg = '#065f46' if is_true else '#9ca3af'
            mark = '&#10003; ' if is_true else '&#10007; '
            pills.append(
                f'<span style="display:inline-block;background:{bg};color:#ffffff;'
                f'font-size:11px;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.4px;padding:5px 11px;border-radius:999px;'
                f'margin:0 6px 6px 0;">{mark}{esc(label)}</span>'
            )
        badges_block = (
            f'<tr><td style="padding:16px 22px 0;">{"".join(pills)}</td></tr>'
        )

    free_text_block = ''
    if free_text and str(free_text).strip():
        free_text_block = (
            '<tr><td style="padding:18px 22px 0;">'
            f'<div style="font-size:11px;color:#6b7280;text-transform:uppercase;'
            f'letter-spacing:0.4px;font-weight:700;margin-bottom:8px;">'
            f'{esc(free_text_label or "Note")}</div>'
            '<div style="background:#f9fafb;border-left:3px solid #CC0000;'
            'padding:12px 14px;color:#111827;font-size:14px;line-height:1.55;'
            'white-space:pre-wrap;border-radius:0 6px 6px 0;">'
            f'{esc(str(free_text))}</div></td></tr>'
        )

    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f4f4f5;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,'
        'Helvetica,Arial,sans-serif;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="background:#f4f4f5;padding:24px 12px;">'
        '<tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="max-width:560px;background:#ffffff;border-radius:12px;'
        'overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
        '<tr><td style="background:#CC0000;padding:18px 22px;">'
        '<div style="color:#ffffff;font-size:11px;font-weight:700;letter-spacing:1.4px;'
        'text-transform:uppercase;opacity:0.85;">HD Hauling &amp; Grading</div>'
        f'<div style="color:#ffffff;font-size:19px;font-weight:700;'
        f'letter-spacing:-0.01em;margin-top:3px;">{esc(title)}</div>'
        '</td></tr>'
        '<tr><td style="padding:22px 22px 4px;">'
        f'<div style="color:#111827;font-size:22px;font-weight:700;'
        f'letter-spacing:-0.01em;line-height:1.25;">{esc(name)}</div>'
        f'<div style="color:#6b7280;font-size:14px;margin-top:4px;">{esc(subtitle)}</div>'
        '</td></tr>'
        f'{badges_block}'
        '<tr><td style="padding:16px 8px 0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="border-bottom:1px solid #e5e7eb;">{rows_block}</table>'
        '</td></tr>'
        f'{free_text_block}'
        '<tr><td align="center" style="padding:26px 22px 12px;">'
        f'<a href="{esc(cta_url)}" style="display:inline-block;background:#CC0000;'
        f'color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;'
        f'letter-spacing:0.3px;padding:12px 26px;border-radius:6px;">'
        f'{esc(cta_label)} &rarr;</a>'
        '</td></tr>'
        '<tr><td style="padding:8px 22px 24px;text-align:center;">'
        '<div style="color:#6b7280;font-size:12px;line-height:1.5;">'
        '<strong style="color:#111827;">HD Hauling &amp; Grading</strong><br>'
        'You received this because you\'re subscribed to form notifications.<br>'
        'Change in app &rarr; Settings &rarr; Notifications.'
        '</div></td></tr>'
        '</table></td></tr></table></body></html>'
    )

def _send_lead_email(lead):
    """Email each office user who opted in to New Leads notifications PLUS
    the always-on estimates@hdgrading.com shared inbox.

    Opted-in users: all active admin/user/dev accounts unless they've explicitly
    set notif_prefs.email.new_leads = false. Field users are always excluded
    (they're not in the role filter inside _users_opted_in).

    Sent from admin@hdgrading.com (requires admin@hdgrading.com to be the
    OAuthed Gmail account or a verified Send-As alias on that account).
    Silently no-ops if Gmail isn't configured."""
    if not GMAIL_AVAILABLE:
        return
    token_json = os.environ.get('GMAIL_TOKEN_JSON', '')
    if not token_json:
        return
    recipients = list(_users_opted_in('new_leads', default=True))
    # Always include the estimates inbox, deduped against opted-in user emails.
    _seen = {em.lower() for (em, _nm) in recipients}
    if LEAD_ALWAYS_TO.lower() not in _seen:
        recipients.append((LEAD_ALWAYS_TO, 'HD Estimates'))
    if not recipients:
        return
    import base64
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    try:
        creds = Credentials.from_authorized_user_info(json.loads(token_json))
        service = gmail_build('gmail', 'v1', credentials=creds)
        name = lead.get('name') or 'Unknown'
        company = lead.get('company') or ''
        subject_bits = ['New lead', name]
        if company:
            subject_bits.append(f'({company})')
        subject = 'HD Hauling — ' + ' '.join(subject_bits)
        plain_lines = [
            'A new quote request came in from the website.',
            '',
            f'Name:        {name}',
            f'Company:     {company or "—"}',
            f'Phone:       {lead.get("phone") or "—"}',
            f'Email:       {lead.get("email") or "—"}',
            f'Address:     {lead.get("address") or "—"}',
            f'Source:      {lead.get("source") or "—"}',
            '',
            'Description:',
            lead.get('description') or '—',
            '',
            'Open in the app: https://hdapp.up.railway.app/#leads',
            '',
            '— HD Hauling & Grading'
        ]
        plain_body = '\n'.join(plain_lines)
        html_body = _render_form_email_html(
            title='New Quote Request',
            name=name,
            subtitle=company or 'Individual',
            rows=[
                ('Phone', lead.get('phone')),
                ('Email', lead.get('email')),
                ('Address', lead.get('address')),
                ('Source', lead.get('source')),
            ],
            free_text_label='Project description',
            free_text=lead.get('description'),
            cta_label='Open in HD App',
            cta_url='https://hdapp.up.railway.app/#leads',
        )
        for email_addr, _full_name in recipients:
            try:
                msg = MIMEMultipart('alternative')
                msg['to'] = email_addr
                msg['from'] = LEAD_EMAIL_FROM
                msg['subject'] = subject
                msg.attach(MIMEText(plain_body, 'plain'))
                msg.attach(MIMEText(html_body, 'html'))
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                service.users().messages().send(userId='me', body={'raw': raw}).execute()
            except Exception as inner:
                print(f'[_send_lead_email recipient={email_addr}] {type(inner).__name__}: {inner}')
    except Exception as e:
        print(f'[_send_lead_email] {type(e).__name__}: {e}')

@app.route('/leads/list')
@require_auth
def list_leads():
    try:
        status = request.args.get('status', 'new')
        q = sb_url('hd_leads', "?" + "select=*&" + "order=submitted_at.desc")
        if status != 'all':
            q += '&' + _sb_eq('status', status)
        r = http.get(q, headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': r.text[:500]}), r.status_code
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return _safe_error(e, context='leads/list')

@app.route('/leads/<int:lid>', methods=['PATCH'])
@require_auth
def update_lead(lid):
    try:
        d = request.json or {}
        updates = {}
        if 'status' in d: updates['status'] = d['status']
        if not updates:
            return jsonify({'ok': False, 'error': 'Nothing to update'}), 400
        r = http.patch(sb_url('hd_leads', "?" + _sb_eq('id', lid)), json=updates, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='leads/<int:lid>')

@app.route('/leads/<int:lid>', methods=['DELETE'])
@require_auth
def delete_lead(lid):
    """Permanently delete a lead. Used to clean out test submissions or leads
    that office staff no longer want to track. Hard delete — no undo."""
    try:
        r = http.delete(sb_url('hd_leads', '?' + _sb_eq('id', lid)), headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='leads/<int:lid> DELETE')

@app.route('/leads/<int:lid>/convert', methods=['POST'])
@require_auth
def convert_lead(lid):
    """Convert a lead into a pipeline project and optionally a client."""
    try:
        # Get the lead
        lr = http.get(sb_url('hd_leads', "?" + _sb_eq('id', lid) + "&" + "select=*"), headers=sb_admin_headers(), timeout=10)
        if lr.status_code != 200 or not lr.json():
            return jsonify({'ok': False, 'error': 'Lead not found'}), 404
        lead = lr.json()[0]
        # Create client if no match
        client_id = lead.get('matched_client_id')
        if not client_id:
            client_row = {
                'name': lead['name'],
                'company': lead.get('company', ''),
                'email': lead.get('email', ''),
                'phone': lead.get('phone', ''),
                'address': lead.get('address', ''),
                'notes': 'Converted from lead intake form'
            }
            cr = http.post(sb_url('clients'), json=client_row, headers=sb_admin_headers(), timeout=10)
            if cr.status_code in (200, 201) and cr.json():
                client_id = cr.json()[0]['id'] if isinstance(cr.json(), list) else cr.json().get('id')
        # Find first pipeline stage ("Lead")
        sr = http.get(sb_url('pipeline_stages', '?select=id&order=position.asc&limit=1'), headers=sb_admin_headers(), timeout=5)
        stage_id = sr.json()[0]['id'] if sr.status_code == 200 and sr.json() else None
        # Generate project number
        proj_num = _next_project_number()
        # Create proposal/project
        snap = {
            # is_project=true is required for the row to appear in the Pipeline,
            # Projects list, and reports — it's the actual filter the frontend
            # uses to distinguish "live items" from miscellaneous proposal rows.
            'is_project': True,
            'project_name': lead.get('company') or lead['name'],
            'client': lead['name'],
            'address': lead.get('address', ''),
            'project_number': proj_num,
            'notes': lead.get('description', ''),
            'date': datetime.utcnow().strftime('%Y-%m-%d'),
            'sections': [], 'concItems': [], 'extraItems': [],
            'lead_source': lead.get('source', ''),
            'activity_log': [{'type': 'created', 'text': 'Converted from lead form', 'date': datetime.utcnow().isoformat(), 'user': session.get('username', '')}]
        }
        prop_row = {
            'name': lead.get('company') or lead['name'],
            'client': lead['name'],
            'total': 0,
            'stage_id': stage_id,
            # snap is JSONB — pass the dict directly; json.dumps would store a
            # JSON-encoded string inside the JSONB column, which the frontend
            # then has to JSON.parse a second time.
            'snap': snap,
            'created_by': session.get('username', 'system'),
            # project_number lives inside snap (line above) — proposals table has no top-level column for it.
        }
        # RLS is enabled on `proposals` — must use service-role headers to insert.
        pr = http.post(sb_url('proposals'), json=prop_row, headers=sb_admin_headers(), timeout=10)
        proposal_id = None
        if pr.status_code in (200, 201) and pr.json():
            pdata = pr.json()[0] if isinstance(pr.json(), list) else pr.json()
            proposal_id = pdata.get('id')
        # If the proposal insert failed, surface the error and leave the lead alone
        # so the user can retry instead of marking it accepted with no project behind it.
        if not proposal_id:
            app.logger.error('convert_lead: proposal insert failed (%s) %s', pr.status_code, pr.text[:300])
            return jsonify({'ok': False, 'error': 'Could not create project from lead. Try again or contact support.'}), 500
        # Mark lead as accepted
        http.patch(sb_url('hd_leads', "?" + _sb_eq('id', lid)),
                   json={'status': 'accepted', 'created_proposal_id': proposal_id},
                   headers=sb_admin_headers(), timeout=10)
        return jsonify({'ok': True, 'proposal_id': proposal_id, 'client_id': client_id})
    except Exception as e:
        return _safe_error(e, context='leads/<int:lid>/convert')

# ── Applicant Intake (job applications) ───────────────────
APPLICANT_EMAIL_FROM = 'HD Hauling & Grading <admin@hdgrading.com>'
RESUME_BUCKET = 'resumes'
RESUME_MAX_BYTES = 5 * 1024 * 1024  # mirrors Storage bucket cap
RESUME_ALLOWED_MIME = {
    'application/pdf': 'pdf',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
}

def _safe_resume_filename(name):
    """Strip path separators + non-printable chars; cap length."""
    base = (name or 'resume').rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    cleaned = ''.join(c for c in base if c.isalnum() or c in '._- ').strip().replace(' ', '_')
    return (cleaned or 'resume')[:120]

def _storage_url(bucket, path=''):
    return f'{SUPABASE_URL}/storage/v1/object/{bucket}/{path}'

def _storage_admin_headers(content_type=None):
    h = {
        'apikey': SUPABASE_SERVICE_KEY,
        'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
    }
    if content_type:
        h['Content-Type'] = content_type
    return h

@app.route('/applicants-form')
def applicants_form_page():
    """Serve the public job application form."""
    return send_file('applicants_form.html')

@app.route('/applicants/submit', methods=['POST'])
def submit_applicant():
    """Public route — no auth. Accept multipart job application from public form.
    Uploads resume (optional) to Supabase Storage 'resumes' bucket, writes a row
    to hd_applicants, notifies office users (in-app + email gated by pref)."""
    # Rate limit per IP (5 / 30 min — applications shouldn't be high-volume)
    try:
        from security import rate_limit_check
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
        allowed, retry = rate_limit_check(f'applicant:{ip}', max_attempts=5, window_s=1800)
        if not allowed:
            return jsonify({'ok': False, 'error': f'Too many submissions. Try again in {retry}s.'}), 429
    except ImportError:
        pass

    try:
        f = request.form
        # Honeypot: short-circuit bots without saving. Return success.
        if _honeypot_tripped(f):
            ip_for_log = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip() or 'unknown'
            app.logger.info('[honeypot] /applicants/submit rejected submission from %s', ip_for_log)
            return jsonify({'ok': True})
        name = f.get('name', '').strip()[:200]
        if not name:
            return jsonify({'ok': False, 'error': 'Name is required.'}), 400

        email = f.get('email', '').strip()[:200]
        if not _valid_email(email):
            return jsonify({'ok': False, 'error': 'Please enter a valid email address.'}), 400
        phone = _normalize_phone(f.get('phone', '').strip()[:40])
        if not phone:
            return jsonify({'ok': False, 'error': 'Please enter a valid 10-digit phone number.'}), 400

        def yes(v): return str(v).strip().lower() in ('yes', 'true', '1', 'y')

        row = {
            'name': name,
            'email': email,
            'phone': phone,
            'city_state': f.get('city_state', '').strip()[:200],
            'position': f.get('position', '').strip()[:200],
            'role_type': f.get('role_type', '').strip()[:20],
            'years_exp': f.get('years_exp', '').strip()[:10],
            'work_eligible': yes(f.get('work_eligible', '')),
            'age_18_plus': yes(f.get('age_18_plus', '')),
            'has_license': yes(f.get('has_license', '')),
            'cdl_class': f.get('cdl_class', 'None').strip()[:20],
            'note': f.get('note', '').strip()[:4000],
            'source': f.get('source', '').strip()[:100],
            'status': 'new',
        }

        resume = request.files.get('resume')
        resume_path = None
        resume_filename = None
        resume_mime = None
        if resume and resume.filename:
            mime = (resume.mimetype or '').lower()
            if mime not in RESUME_ALLOWED_MIME:
                return jsonify({'ok': False, 'error': 'Resume must be PDF, DOC, or DOCX.'}), 400
            data = resume.read()
            if len(data) > RESUME_MAX_BYTES:
                return jsonify({'ok': False, 'error': 'Resume exceeds 5 MB limit.'}), 400
            ext = RESUME_ALLOWED_MIME[mime]
            safe_name = _safe_resume_filename(resume.filename)
            object_path = f'{uuid.uuid4()}_{safe_name}'
            if not object_path.lower().endswith('.' + ext):
                object_path += '.' + ext
            up = http.post(
                _storage_url(RESUME_BUCKET, object_path),
                headers=_storage_admin_headers(content_type=mime),
                data=data,
                timeout=30,
            )
            if up.status_code >= 300:
                app.logger.error('Storage upload failed: %s %s', up.status_code, up.text[:200])
                return jsonify({'ok': False, 'error': 'Could not upload resume. Try again.'}), 500
            resume_path = object_path
            resume_filename = safe_name
            resume_mime = mime

        row['resume_path'] = resume_path
        row['resume_filename'] = resume_filename
        row['resume_mime'] = resume_mime

        r = http.post(f"{SUPABASE_URL}/rest/v1/hd_applicants", json=row, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            # Best-effort cleanup of orphan upload
            if resume_path:
                try:
                    http.delete(_storage_url(RESUME_BUCKET, resume_path), headers=_storage_admin_headers(), timeout=10)
                except Exception:
                    pass
            return jsonify({'ok': False, 'error': 'Could not save application. Try again.'}), 500

        # In-app notification fan-out to office users
        try:
            ur = http.get(sb_url('hd_users', '?active=eq.true&role=neq.field&select=username'), headers=sb_admin_headers(), timeout=5)
            if ur.status_code == 200 and ur.json():
                pos = row['position'] or 'Unspecified role'
                title = f'New applicant: {name}'
                body = f'{pos} — {row["years_exp"] or "—"} yrs exp, {row["role_type"] or "Role TBD"}'
                rows = [{'recipient': u['username'], 'type': 'info', 'title': title, 'body': body, 'created_by': 'system'} for u in ur.json()]
                http.post(sb_url('hd_notifications', ''), headers=sb_headers(), json=rows, timeout=5)
        except Exception:
            pass

        # Email fan-out (best-effort, opt-in via notif_prefs.email.new_applicants)
        try:
            _send_applicant_email(row)
        except Exception:
            pass

        return jsonify({'ok': True})
    except Exception as e:
        app.logger.exception('submit_applicant')
        return jsonify({'ok': False, 'error': 'Could not save application. Please try again.'}), 500

def _send_applicant_email(applicant):
    """Email each office user opted in to New Applicants notifications.
    Silently no-ops if Gmail isn't configured or nobody's opted in."""
    if not GMAIL_AVAILABLE:
        return
    token_json = os.environ.get('GMAIL_TOKEN_JSON', '')
    if not token_json:
        return
    recipients = _users_opted_in('new_applicants', default=True)
    if not recipients:
        return
    import base64
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    try:
        creds = Credentials.from_authorized_user_info(json.loads(token_json))
        service = gmail_build('gmail', 'v1', credentials=creds)
        name = applicant.get('name') or 'Unknown'
        position = applicant.get('position') or 'Unspecified role'
        subject = f'HD Hauling — New applicant: {name} ({position})'
        plain_lines = [
            'A new job application came in from the careers form.',
            '',
            f'Name:           {name}',
            f'Position:       {position}',
            f'Experience:     {applicant.get("years_exp") or "—"}',
            f'Email:          {applicant.get("email") or "—"}',
            f'Phone:          {applicant.get("phone") or "—"}',
            f'Location:       {applicant.get("city_state") or "—"}',
            f'Eligible to work: {"Yes" if applicant.get("work_eligible") else "No"}',
            f'18 or older:    {"Yes" if applicant.get("age_18_plus") else "No"}',
            f"Driver's license: {'Yes' if applicant.get('has_license') else 'No'}",
            f'CDL:            {applicant.get("cdl_class") or "None"}',
            f'Resume:         {"attached in app" if applicant.get("resume_path") else "not provided"}',
            f'Source:         {applicant.get("source") or "—"}',
            '',
            'Note from applicant:',
            applicant.get('note') or '—',
            '',
            'Open in the app: https://hdapp.up.railway.app/#dashboard',
            '',
            '— HD Hauling & Grading',
        ]
        plain_body = '\n'.join(plain_lines)
        cdl = applicant.get('cdl_class') or 'None'
        html_body = _render_form_email_html(
            title='New Job Application',
            name=name,
            subtitle=position,
            rows=[
                ('Experience', applicant.get('years_exp')),
                ('Phone', applicant.get('phone')),
                ('Email', applicant.get('email')),
                ('Location', applicant.get('city_state')),
                ('CDL', cdl if cdl and cdl != 'None' else 'No CDL'),
                ('Resume', 'Attached (open in app to view)' if applicant.get('resume_path') else 'Not provided'),
                ('Source', applicant.get('source')),
            ],
            badges=[
                ('Eligible to work', bool(applicant.get('work_eligible'))),
                ('18 or older', bool(applicant.get('age_18_plus'))),
                ("Driver's license", bool(applicant.get('has_license'))),
            ],
            free_text_label='Note from applicant',
            free_text=applicant.get('note'),
            cta_label='Open in HD App',
            cta_url='https://hdapp.up.railway.app/#dashboard',
        )
        for email_addr, _full_name in recipients:
            try:
                msg = MIMEMultipart('alternative')
                msg['to'] = email_addr
                msg['from'] = APPLICANT_EMAIL_FROM
                msg['subject'] = subject
                msg.attach(MIMEText(plain_body, 'plain'))
                msg.attach(MIMEText(html_body, 'html'))
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                service.users().messages().send(userId='me', body={'raw': raw}).execute()
            except Exception as inner:
                app.logger.error('[_send_applicant_email recipient=%s] %s', email_addr, inner)
    except Exception as e:
        app.logger.exception('_send_applicant_email')

@app.route('/applicants/list')
@require_auth
def list_applicants():
    """List applicants. ?status=new (default) | all"""
    try:
        status = request.args.get('status', 'new')
        q = sb_url('hd_applicants', '?select=*&order=submitted_at.desc')
        if status != 'all':
            q += '&' + _sb_eq('status', status)
        r = http.get(q, headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': r.text[:500]}), r.status_code
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return _safe_error(e, context='applicants/list')

@app.route('/applicants/<int:aid>', methods=['PATCH'])
@require_auth
def update_applicant(aid):
    try:
        d = request.json or {}
        updates = {}
        for key in ('status', 'admin_notes'):
            if key in d:
                updates[key] = d[key]
        if 'status' in updates and updates['status'] in ('reviewed', 'contacted', 'rejected', 'hired'):
            updates['reviewed_by'] = session.get('username', '')
            updates['reviewed_at'] = datetime.utcnow().isoformat()
        if not updates:
            return jsonify({'ok': False, 'error': 'Nothing to update'}), 400
        r = http.patch(sb_url('hd_applicants', '?' + _sb_eq('id', aid)), json=updates, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='applicants/<int:aid>')

@app.route('/applicants/<int:aid>', methods=['DELETE'])
@require_auth
def delete_applicant(aid):
    """Permanently delete an applicant + their resume file from Storage.
    Hard delete — no undo. Resume cleanup is best-effort: DB row always wins,
    so orphaned files are logged but don't block the delete."""
    try:
        # Look up the resume path before deleting so we know what to clean up.
        lookup = http.get(
            sb_url('hd_applicants', '?' + _sb_eq('id', aid) + '&select=resume_path'),
            headers=sb_admin_headers(), timeout=5
        )
        resume_path = None
        if lookup.status_code == 200 and lookup.json():
            resume_path = lookup.json()[0].get('resume_path')
        # Delete the DB row first.
        r = http.delete(sb_url('hd_applicants', '?' + _sb_eq('id', aid)), headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        # Clean up the resume file (best-effort — row is already gone).
        if resume_path:
            try:
                http.delete(_storage_url(RESUME_BUCKET, resume_path), headers=_storage_admin_headers(), timeout=10)
            except Exception as storage_err:
                app.logger.warning('Applicant %s deleted but resume cleanup failed: %s', aid, storage_err)
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='applicants/<int:aid> DELETE')

@app.route('/applicants/<int:aid>/resume')
@require_auth
def applicant_resume(aid):
    """Server-side proxy: fetch the resume from the private Storage bucket
    using the service-role key and stream it to the authenticated office user.
    Resumes never leave server-side auth context."""
    try:
        r = http.get(sb_url('hd_applicants', '?' + _sb_eq('id', aid) + '&select=resume_path,resume_filename,resume_mime,name'),
                     headers=sb_admin_headers(), timeout=5)
        if r.status_code != 200 or not r.json():
            return jsonify({'ok': False, 'error': 'Applicant not found'}), 404
        ap = r.json()[0]
        path = ap.get('resume_path')
        if not path:
            return jsonify({'ok': False, 'error': 'No resume on file'}), 404
        sr = http.get(_storage_url(RESUME_BUCKET, path), headers=_storage_admin_headers(), timeout=20, stream=True)
        if sr.status_code != 200:
            return jsonify({'ok': False, 'error': 'Could not fetch resume'}), 502
        from flask import Response
        mime = ap.get('resume_mime') or 'application/octet-stream'
        # Suggest a download filename based on the applicant's name + original ext
        ext = (ap.get('resume_filename') or '').rsplit('.', 1)
        ext = ext[-1] if len(ext) == 2 else 'bin'
        safe_name = ''.join(c for c in (ap.get('name') or 'applicant') if c.isalnum() or c in '_- ').strip().replace(' ', '_') or 'applicant'
        download_name = f'{safe_name}_resume.{ext}'
        return Response(
            sr.iter_content(chunk_size=64 * 1024),
            mimetype=mime,
            headers={
                'Content-Disposition': f'inline; filename="{download_name}"',
                'Cache-Control': 'private, max-age=0',
            },
        )
    except Exception as e:
        return _safe_error(e, context='applicants/resume')

# ── Time Tracking (GPS Clock-In/Out) ──────────────────────
@app.route('/time/clock-in', methods=['POST'])
@require_auth
def time_clock_in():
    if session.get('role') != 'field':
        return jsonify({'ok': False, 'error': 'Only field users can clock in'}), 403
    try:
        d = request.json or {}
        username = session.get('username')
        # Check for existing active clock-in
        r = http.get(sb_url('hd_time_entries', "?" + _sb_eq('username', username) + "&" + "clock_out=is.null&" + "select=id"),
                     headers=sb_admin_headers(), timeout=5)
        if r.status_code == 200 and r.json():
            return jsonify({'ok': False, 'error': 'Already clocked in. Clock out first.'}), 400
        row = {
            'username': username,
            'work_order_id': str(d.get('work_order_id', '')),
            'project_id': d.get('project_id'),
            'clock_in': datetime.utcnow().isoformat(),
            'clock_in_lat': d.get('lat'),
            'clock_in_lng': d.get('lng')
        }
        r = http.post(f"{SUPABASE_URL}/rest/v1/hd_time_entries", json=row, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        entry = r.json()[0] if isinstance(r.json(), list) else r.json()
        return jsonify({'ok': True, 'entry': entry})
    except Exception as e:
        return _safe_error(e, context='time/clock-in')

@app.route('/time/clock-out', methods=['POST'])
@require_auth
def time_clock_out():
    if session.get('role') != 'field':
        return jsonify({'ok': False, 'error': 'Only field users can clock out'}), 403
    try:
        d = request.json or {}
        username = session.get('username')
        # Find active entry
        r = http.get(sb_url('hd_time_entries', "?" + _sb_eq('username', username) + "&" + "clock_out=is.null&" + "select=*&" + "limit=1"),
                     headers=sb_admin_headers(), timeout=5)
        if r.status_code != 200 or not r.json():
            return jsonify({'ok': False, 'error': 'No active clock-in found'}), 400
        entry = r.json()[0]
        eid = entry['id']
        clock_in = datetime.fromisoformat(entry['clock_in'].replace('Z', '+00:00').replace('+00:00', ''))
        clock_out = datetime.utcnow()
        hours = round((clock_out - clock_in).total_seconds() / 3600, 2)
        # Look up hourly rate
        ur = http.get(sb_url('hd_users', '?' + _sb_eq('username', username) + '&' + 'select=hourly_rate'), headers=sb_admin_headers(), timeout=5)
        rate = 0
        if ur.status_code == 200 and ur.json():
            rate = float(ur.json()[0].get('hourly_rate') or 0)
        cost = round(hours * rate, 2)
        update = {
            'clock_out': clock_out.isoformat(),
            'clock_out_lat': d.get('lat'),
            'clock_out_lng': d.get('lng'),
            'hours_worked': hours,
            'hourly_rate': rate,
            'labor_cost': cost
        }
        r2 = http.patch(sb_url('hd_time_entries', "?" + _sb_eq('id', eid)), json=update, headers=sb_admin_headers(), timeout=10)
        if r2.status_code >= 300:
            return jsonify({'ok': False, 'error': r2.text[:500]}), 400
        return jsonify({'ok': True, 'hours': hours, 'cost': cost})
    except Exception as e:
        return _safe_error(e, context='time/clock-out')

@app.route('/time/active')
@require_auth
def time_active():
    try:
        username = session.get('username')
        r = http.get(sb_url('hd_time_entries', "?" + _sb_eq('username', username) + "&" + "clock_out=is.null&" + "select=*&" + "limit=1"),
                     headers=sb_admin_headers(), timeout=5)
        if r.status_code == 200 and r.json():
            return jsonify({'ok': True, 'active': r.json()[0]})
        return jsonify({'ok': True, 'active': None})
    except Exception as e:
        return _safe_error(e, context='time/active')

@app.route('/time/entries')
@require_auth
def time_entries():
    try:
        project_id = request.args.get('project_id')
        wo_id = request.args.get('work_order_id')
        q = sb_url('hd_time_entries', "?" + "select=*&" + "order=clock_in.desc")
        if project_id:
            q += '&' + _sb_eq('project_id', project_id)
        if wo_id:
            q += '&' + _sb_eq('work_order_id', wo_id)
        r = http.get(q, headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': r.text[:500]}), r.status_code
        entries = r.json()
        # Strip cost data for non-admin users
        if session.get('role') not in ('admin', 'dev'):
            for e in entries:
                e.pop('hourly_rate', None)
                e.pop('labor_cost', None)
        return jsonify({'ok': True, 'entries': entries})
    except Exception as e:
        return _safe_error(e, context='time/entries')

@app.route('/time/<int:tid>', methods=['DELETE'])
@require_admin
def delete_time_entry(tid):
    try:
        r = http.delete(sb_url('hd_time_entries', "?" + _sb_eq('id', tid)), headers=sb_admin_headers(prefer='return=minimal'), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='time/<int:tid>')

# ── Tasks ──────────────────────────────────────────────────
@app.route('/tasks/list')
@require_auth
def list_tasks():
    try:
        q = sb_url('hd_tasks', "?" + "select=*&" + "order=due_date.asc.nullslast,created_at.desc")
        filt = request.args.get('filter', 'open')
        username = session.get('username')
        if filt == 'completed':
            q += '&completed=eq.true'
        else:
            q += '&completed=eq.false'
        # Visibility: show public tasks + private tasks owned by or assigned to current user
        # username is URL-encoded for defense-in-depth (session-set, but contains @ which needs encoding)
        _enc_user = _url_quote(str(username or ''), safe='')
        q += f'&or=(visibility.eq.public,created_by.eq.{_enc_user},assigned_to.eq.{_enc_user})'
        r = http.get(q, headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': r.text[:500]}), r.status_code
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return _safe_error(e, context='tasks/list')

@app.route('/tasks/save', methods=['POST'])
@require_auth
def save_task():
    try:
        d = request.json or {}
        title = str(d.get('title', '')).strip()
        if not title:
            return jsonify({'ok': False, 'error': 'Title is required'}), 400
        row = {
            'title': title,
            'description': str(d.get('description', '')).strip(),
            'priority': d.get('priority', 'medium'),
            'visibility': d.get('visibility', 'public'),
            'assigned_to': str(d.get('assigned_to', '')).strip() or session.get('username'),
            'created_by': session.get('username', 'unknown'),
            'due_date': d.get('due_date') or None,
            'ref_type': d.get('ref_type') or None,
            'ref_id': d.get('ref_id') or None,
            'ref_name': str(d.get('ref_name', '')).strip() or None,
            'completed': False
        }
        r = http.post(f"{SUPABASE_URL}/rest/v1/hd_tasks", json=row, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True, 'item': r.json()[0] if isinstance(r.json(), list) else r.json()})
    except Exception as e:
        return _safe_error(e, context='tasks/save')

@app.route('/tasks/<int:tid>', methods=['PATCH'])
@require_auth
def update_task(tid):
    try:
        # Ownership check
        lookup = http.get(sb_url('hd_tasks', '?' + _sb_eq('id', tid) + '&select=created_by'),
                          headers=sb_admin_headers(), timeout=10)
        rows = lookup.json() if lookup.ok else []
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        if not _owns_or_admin(rows[0].get('created_by')):
            return jsonify({'error': 'Not permitted'}), 403
        d = request.json or {}
        updates = {}
        for field in ('title', 'description', 'priority', 'status', 'visibility', 'assigned_to', 'due_date', 'ref_type', 'ref_id', 'ref_name'):
            if field in d:
                updates[field] = d[field]
        if 'completed' in d:
            updates['completed'] = bool(d['completed'])
            if d['completed']:
                updates['completed_at'] = datetime.utcnow().isoformat()
            else:
                updates['completed_at'] = None
        if not updates:
            return jsonify({'ok': False, 'error': 'Nothing to update'}), 400
        updates['updated_at'] = datetime.utcnow().isoformat()
        r = http.patch(sb_url('hd_tasks', "?" + _sb_eq('id', tid)), json=updates, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='tasks/<int:tid>')

@app.route('/tasks/<int:tid>', methods=['DELETE'])
@require_auth
def delete_task(tid):
    try:
        # Ownership check
        lookup = http.get(sb_url('hd_tasks', '?' + _sb_eq('id', tid) + '&select=created_by'),
                          headers=sb_admin_headers(), timeout=10)
        rows = lookup.json() if lookup.ok else []
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        if not _owns_or_admin(rows[0].get('created_by')):
            return jsonify({'error': 'Not permitted'}), 403
        r = http.delete(sb_url('hd_tasks', "?" + _sb_eq('id', tid)), headers=sb_admin_headers(prefer='return=minimal'), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='tasks/<int:tid>')

# ── Reminders ─────────────────────────────────────────────
@app.route('/reminders/list')
@require_auth
def list_reminders():
    try:
        q = sb_url('hd_reminders', "?" + "select=*&" + "order=due_date.asc")
        filt = request.args.get('filter')
        if filt == 'due':
            today = datetime.utcnow().strftime('%Y-%m-%d')
            q += f"&completed=eq.false&due_date=lte.{today}"
        elif filt == 'upcoming':
            q += '&completed=eq.false'
        elif filt == 'completed':
            q += '&completed=eq.true'
        else:
            q += '&completed=eq.false'
        r = http.get(q, headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': r.text[:500]}), r.status_code
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return _safe_error(e, context='reminders/list')

@app.route('/reminders/save', methods=['POST'])
@require_auth
def save_reminder():
    try:
        d = request.json or {}
        note = str(d.get('note', '')).strip()
        due_date = str(d.get('due_date', '')).strip()
        if not note or not due_date:
            return jsonify({'ok': False, 'error': 'Note and due date are required'}), 400
        row = {
            'type': d.get('type', 'project'),
            'ref_id': d.get('ref_id'),
            'ref_name': str(d.get('ref_name', '')).strip(),
            'note': note,
            'due_date': due_date,
            'assigned_to': str(d.get('assigned_to', '')).strip() or session.get('username'),
            'created_by': session.get('username', 'unknown'),
            'completed': False
        }
        r = http.post(f"{SUPABASE_URL}/rest/v1/hd_reminders", json=row, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True, 'item': r.json()[0] if isinstance(r.json(), list) else r.json()})
    except Exception as e:
        return _safe_error(e, context='reminders/save')

@app.route('/reminders/<int:rid>', methods=['PATCH'])
@require_auth
def update_reminder(rid):
    try:
        # Ownership check
        lookup = http.get(sb_url('hd_reminders', '?' + _sb_eq('id', rid) + '&select=created_by'),
                          headers=sb_admin_headers(), timeout=10)
        rows = lookup.json() if lookup.ok else []
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        if not _owns_or_admin(rows[0].get('created_by')):
            return jsonify({'error': 'Not permitted'}), 403
        d = request.json or {}
        updates = {}
        if 'completed' in d:
            updates['completed'] = bool(d['completed'])
            if d['completed']:
                updates['completed_at'] = datetime.utcnow().isoformat()
            else:
                updates['completed_at'] = None
        if 'note' in d: updates['note'] = str(d['note']).strip()
        if 'due_date' in d: updates['due_date'] = str(d['due_date']).strip()
        if 'assigned_to' in d: updates['assigned_to'] = str(d['assigned_to']).strip()
        if not updates:
            return jsonify({'ok': False, 'error': 'Nothing to update'}), 400
        r = http.patch(sb_url('hd_reminders', "?" + _sb_eq('id', rid)), json=updates, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='reminders/<int:rid>')

@app.route('/reminders/<int:rid>', methods=['DELETE'])
@require_auth
def delete_reminder(rid):
    try:
        # Ownership check
        lookup = http.get(sb_url('hd_reminders', '?' + _sb_eq('id', rid) + '&select=created_by'),
                          headers=sb_admin_headers(), timeout=10)
        rows = lookup.json() if lookup.ok else []
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        if not _owns_or_admin(rows[0].get('created_by')):
            return jsonify({'error': 'Not permitted'}), 403
        r = http.delete(sb_url('hd_reminders', "?" + _sb_eq('id', rid)), headers=sb_admin_headers(prefer='return=minimal'), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return _safe_error(e, context='reminders/<int:rid>')

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_ENV') != 'production', port=5000)
