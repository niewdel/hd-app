import os, tempfile, functools, json, hashlib, time
from datetime import datetime
from flask import Flask, request, jsonify, session, send_file
from generate_proposal import build
try:
    from googleapiclient.discovery import build as gmail_build
    from google.oauth2.credentials import Credentials
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
import generate_docx
import generate_report
import requests as http

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'hd-hauling-dev-key')

APP_PIN             = os.environ.get('APP_PIN', '2025')
SUPABASE_URL        = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY        = os.environ.get('SUPABASE_KEY', '')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')

def sb_headers():
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
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

def sb_url(table, params=''):
    return f'{SUPABASE_URL}/rest/v1/{table}{params}'

def hash_pin(pin):
    return hashlib.sha256(str(pin).encode()).hexdigest()

def hash_password(pw):
    return hashlib.sha256(str(pw).encode()).hexdigest()

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
    session['avatar_data'] = user.get('avatar_data', '')
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
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = str(data.get('username', '')).strip().lower()
    password = str(data.get('password', data.get('pin', ''))).strip()
    try:
        r = http.get(sb_url('hd_users', f'?username=eq.{username}&active=eq.true&limit=1'),
                     headers=sb_headers(), timeout=5)
        if r.status_code != 200:
            return jsonify({'error': 'Database connection error. Please try again.'}), 503
        rows = r.json()
        if not rows:
            return jsonify({'error': 'Incorrect username or password'}), 401
        user = rows[0]
        pw_hash = hash_password(password)
        if user.get('pin_hash') == pw_hash:
            apply_user_session(user)
            log_access(user['username'], user.get('full_name',''), 'login', True)
            # Get last login from access log
            last_login = None
            try:
                lr = http.get(sb_url('hd_access_log', f'?username=eq.{user["username"]}&action=eq.login&success=eq.true&order=logged_at.desc&limit=2'),
                              headers=sb_headers(), timeout=3)
                if lr.status_code == 200:
                    logs = lr.json()
                    if len(logs) > 1: last_login = logs[1].get('logged_at')
            except Exception:
                pass
            return jsonify({'ok': True, 'role': session['role'], 'username': session['username'],
                            'full_name': session['full_name'],
                            'email': session['email'], 'phone': session['phone'],
                            'avatar_data': session.get('avatar_data', ''),
                            'password_hint': user.get('password_hint', ''),
                            'last_login': last_login})
        else:
            log_access(username, '', 'login', False)
            hint = user.get('password_hint', '')
            return jsonify({'error': 'Incorrect username or password', 'hint': hint}), 401
    except http.exceptions.ConnectionError:
        return jsonify({'error': 'Cannot reach database. Check your connection.'}), 503
    except Exception as e:
        return jsonify({'error': f'Login error: {str(e)}'}), 500

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
    hint = str(data.get('hint', '')).strip()
    if not current or not new_pw:
        return jsonify({'ok': False, 'error': 'Current and new password required'}), 400
    if len(new_pw) < 6:
        return jsonify({'ok': False, 'error': 'Password must be at least 6 characters'}), 400
    username = session.get('username', '')
    try:
        r = http.get(sb_url('hd_users', f'?username=eq.{username}&limit=1'), headers=sb_headers(), timeout=5)
        if r.status_code != 200 or not r.json():
            return jsonify({'ok': False, 'error': 'User not found'}), 404
        user = r.json()[0]
        pw_ok = (user.get('password_hash') == hash_password(current) or user.get('pin_hash') == hash_pin(current))
        if not pw_ok:
            return jsonify({'ok': False, 'error': 'Current password is incorrect'}), 401
        update = {'password_hash': hash_password(new_pw), 'pin_hash': hash_pin(new_pw)}
        if hint: update['password_hint'] = hint
        http.patch(sb_url('hd_users', f'?username=eq.{username}'), headers={**sb_headers(), 'Prefer': 'return=minimal'}, json=update, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/auth/check')
def auth_check():
    return jsonify({'authenticated': bool(session.get('authenticated')), 'role': session.get('role','user'),
                    'username': session.get('username',''), 'full_name': session.get('full_name',''),
                    'email': session.get('email',''), 'phone': session.get('phone',''),
                    'avatar_data': session.get('avatar_data', '')})

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
        avatar_data = sanitize_avatar_data(data.get('avatar_data', session.get('avatar_data', '')))
        update = {'full_name': full_name, 'email': email, 'phone': phone}
        # avatar_data stored in session only (column doesn't exist in hd_users)
        r = http.patch(
            sb_url('hd_users', f'?username=eq.{username}'),
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
        user['avatar_data'] = avatar_data
        apply_user_session(user)
        return jsonify({'ok': True, 'profile': {
            'username': session.get('username', ''),
            'full_name': session.get('full_name', ''),
            'email': session.get('email', ''),
            'phone': session.get('phone', ''),
            'role': session.get('role', 'user'),
            'avatar_data': session.get('avatar_data', '')
        }})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        r = http.patch(sb_url('proposals', f'?id=eq.{qid}'), headers=sb_headers(), json=payload, timeout=10)
        r.raise_for_status()
        log_access(session.get('username',''), session.get('full_name',''), f'updated proposal "{data.get("name","")}"')
        return jsonify({'ok': True, 'id': qid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/quotes/list')
@require_auth
def quotes_list():
    try:
        r = http.get(sb_url('proposals', '?select=*&archived=neq.true&order=created_at.desc'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True, 'quotes': r.json()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/quotes/delete/<int:qid>', methods=['DELETE'])
@require_auth
def quotes_delete(qid):
    try:
        # Get name before deleting for the log
        name = ''
        try:
            gr = http.get(sb_url('proposals', f'?id=eq.{qid}&select=name'), headers=sb_headers(), timeout=5)
            if gr.status_code == 200 and gr.json():
                name = gr.json()[0].get('name', '')
        except Exception:
            pass
        r = http.patch(
            sb_url('proposals', f'?id=eq.{qid}'),
            json={'archived': True, 'archived_at': datetime.utcnow().isoformat()},
            headers=sb_headers(), timeout=10
        )
        r.raise_for_status()
        log_access(session.get('username',''), session.get('full_name',''), f'archived proposal "{name}"')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ââ Pipeline ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/pipeline/stages')
@require_auth
def pipeline_stages():
    try:
        r = http.get(sb_url('pipeline_stages', '?select=*&order=position.asc'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True, 'stages': r.json()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/pipeline/move/<int:proposal_id>', methods=['PATCH'])
@require_auth
def pipeline_move(proposal_id):
    data = request.get_json() or {}
    try:
        r = http.patch(
            sb_url('proposals', f'?id=eq.{proposal_id}'),
            headers=sb_headers(),
            json={'stage_id': data.get('stage_id')},
            timeout=10
        )
        r.raise_for_status()
        stage_name = data.get('stage_name', '')
        log_access(session.get('username',''), session.get('full_name',''), f'moved project to "{stage_name}"' if stage_name else 'moved project stage')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        }
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
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/projects/update/<int:pid>', methods=['PATCH'])
@require_auth
def project_update(pid):
    data = request.get_json() or {}
    try:
        payload = {}
        if 'name' in data: payload['name'] = data['name']
        if 'client' in data: payload['client'] = data['client']
        if 'snap' in data: payload['snap'] = data['snap']
        if 'total' in data: payload['total'] = float(data['total'])
        r = http.patch(sb_url('proposals', f'?id=eq.{pid}'), headers=sb_headers(), json=payload, timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ââ Clients âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/clients/list')
@require_auth
def clients_list():
    try:
        r = http.get(sb_url('clients', '?select=*&order=name.asc'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True, 'clients': r.json()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/clients/save', methods=['POST'])
@require_auth
def clients_save():
    data = request.get_json() or {}
    try:
        r = http.post(sb_url('clients'), headers=sb_headers(), json={
            'name': data.get('name', ''), 'company': data.get('company', ''),
            'phone': data.get('phone', ''), 'email': data.get('email', ''),
            'address': data.get('address', ''), 'city_state': data.get('city_state', ''),
            'notes': data.get('notes', ''),
        }, timeout=10)
        r.raise_for_status()
        result = r.json()
        return jsonify({'ok': True, 'id': result[0]['id'] if result else None})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/clients/update/<int:client_id>', methods=['PATCH'])
@require_auth
def clients_update(client_id):
    data = request.get_json() or {}
    try:
        r = http.patch(sb_url('clients', f'?id=eq.{client_id}'), headers=sb_headers(), json={
            'name': data.get('name', ''), 'company': data.get('company', ''),
            'phone': data.get('phone', ''), 'email': data.get('email', ''),
            'address': data.get('address', ''), 'city_state': data.get('city_state', ''),
            'notes': data.get('notes', ''),
        }, timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/clients/delete/<int:client_id>', methods=['DELETE'])
@require_auth
def clients_delete(client_id):
    try:
        r = http.delete(sb_url('clients', f'?id=eq.{client_id}'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/admin/users', methods=['GET'])
@require_admin
def get_users():
    try:
        r = http.get(sb_url('hd_users', '?order=created_at.asc'), headers=sb_headers(), timeout=5)
        users = r.json() if r.status_code == 200 else []
        for u in users:
            u.pop('pin_hash', None)
            u.pop('password_hash', None)
        return jsonify({'ok': True, 'users': users})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/admin/users', methods=['POST'])
@require_admin
def create_user():
    data = request.get_json() or {}
    username = str(data.get('username','')).strip().lower()
    pin = str(data.get('pin','')).strip()
    full_name = str(data.get('full_name','')).strip()
    email = str(data.get('email','')).strip()
    phone = str(data.get('phone','')).strip()
    role = data.get('role','user')
    hint = str(data.get('password_hint', data.get('hint', ''))).strip()
    if not username or not pin: return jsonify({'ok':False,'error':'Username and password required'}), 400
    if role not in ('admin','user','field'): role = 'user'
    try:
        r = http.post(sb_url('hd_users'), headers=sb_headers(), json={'username':username,'full_name':full_name,'email':email,'phone':phone,'password_hash':hash_password(pin),'pin_hash':hash_pin(pin),'role':role,'active':True,'created_by':session.get('username','admin'),'password_hint':hint}, timeout=5)
        if r.status_code in (200,201):
            user = r.json()[0] if isinstance(r.json(),list) else r.json()
            user.pop('pin_hash',None)
            return jsonify({'ok':True,'user':user})
        return jsonify({'ok':False,'error':r.text}), 400
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)}), 500

@app.route('/admin/users/<int:uid>', methods=['PATCH'])
@require_admin
def update_user(uid):
    data = request.get_json() or {}
    update = {}
    if 'full_name' in data: update['full_name'] = data['full_name']
    if 'email' in data: update['email'] = str(data['email']).strip()
    if 'phone' in data: update['phone'] = str(data['phone']).strip()
    if 'username' in data and data['username']:
        new_un = str(data['username']).strip().lower()
        if new_un: update['username'] = new_un
    if 'role' in data and data['role'] in ('admin','user','field'): update['role'] = data['role']
    if 'active' in data: update['active'] = bool(data['active'])
    if 'password' in data and data['password']:
        update['password_hash'] = hash_password(data['password'])
        update['pin_hash'] = hash_pin(data['password'])
    elif 'pin' in data and data['pin']:
        update['pin_hash'] = hash_pin(data['pin'])
        update['password_hash'] = hash_password(data['pin'])
    if 'password_hint' in data: update['password_hint'] = str(data['password_hint']).strip()
    if not update: return jsonify({'ok':False,'error':'Nothing to update'}), 400
    try:
        # If username is changing, look up the old one first
        old_username = None
        if 'username' in update:
            try:
                r0 = http.get(sb_url('hd_users', f'?id=eq.{uid}&select=username'), headers=sb_headers(), timeout=5)
                if r0.status_code == 200 and r0.json():
                    old_username = r0.json()[0]['username']
            except Exception:
                pass

        headers = {**sb_headers(), 'Prefer': 'return=representation'}
        r = http.patch(sb_url('hd_users', f'?id=eq.{uid}'), headers=headers, json=update, timeout=5)
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
        return jsonify({'ok':False,'error':str(e)}), 500


def _cascade_username(old, new):
    """Update username references across tables when a user is renamed."""
    h = sb_headers()
    try:
        # hd_notifications: recipient
        http.patch(sb_url('hd_notifications', f'?recipient=eq.{old}'), headers=h,
                   json={'recipient': new}, timeout=5)
        # hd_notifications: created_by
        http.patch(sb_url('hd_notifications', f'?created_by=eq.{old}'), headers=h,
                   json={'created_by': new}, timeout=5)
        # hd_access_log: username
        http.patch(sb_url('hd_access_log', f'?username=eq.{old}'), headers=h,
                   json={'username': new}, timeout=5)
        # proposals: created_by
        http.patch(sb_url('proposals', f'?created_by=eq.{old}'), headers=h,
                   json={'created_by': new}, timeout=5)
        # projects: created_by
        http.patch(sb_url('projects', f'?created_by=eq.{old}'), headers=h,
                   json={'created_by': new}, timeout=5)
    except Exception:
        pass  # Best-effort — don't fail the user update

@app.route('/admin/logs', methods=['GET'])
@require_admin
def get_logs():
    try:
        limit = int(request.args.get('limit',100))
        uf = request.args.get('username','')
        params = f'?order=logged_at.desc&limit={limit}'
        if uf: params += f'&username=eq.{uf}'
        r = http.get(sb_url('hd_access_log', params), headers=sb_headers(), timeout=5)
        return jsonify({'ok':True,'logs':r.json() if r.status_code==200 else []})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)}), 500

@app.route('/admin/archived')
@require_admin
def admin_archived():
    try:
        r = http.get(
            sb_url('proposals', '?archived=is.true&select=id,name,client,total,archived_at,snap&order=archived_at.desc&limit=50'),
            headers=sb_headers(), timeout=10
        )
        r.raise_for_status()
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/admin/restore/<int:qid>', methods=['POST'])
@require_admin
def admin_restore(qid):
    try:
        r = http.patch(
            sb_url('proposals', f'?id=eq.{qid}'),
            json={'archived': False, 'archived_at': None},
            headers=sb_headers(), timeout=10
        )
        r.raise_for_status()
        log_access(session.get('username',''), session.get('full_name',''), f'restored archived proposal id={qid}')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/generate-pdf', methods=['POST'])
@require_auth
def generate_pdf():
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        build(data, out)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name='HD_Proposal.pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/generate-docx', methods=['POST'])
@require_auth
def generate_docx_route():
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
        out = f.name
    try:
        generate_docx.build(data, out)
        return send_file(out, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                         as_attachment=True, download_name='HD_Proposal.docx')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/change-orders/list')
@require_auth
def co_list():
    try:
        proposal_id = request.args.get('proposal_id', '')
        params = '?select=*&order=created_at.desc'
        if proposal_id:
            params += f'&proposal_id=eq.{proposal_id}'
        r = http.get(sb_url('change_orders', params), headers=sb_headers(), timeout=10)
        if r.status_code == 200:
            return jsonify({'ok': True, 'change_orders': r.json()})
        return jsonify({'ok': True, 'change_orders': []})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ââ Email âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/change-orders/delete/<int:coid>', methods=['DELETE'])
@require_auth
def co_delete(coid):
    try:
        r = http.delete(sb_url('change_orders', f'?id=eq.{coid}'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        log_access(session.get('username',''), session.get('full_name',''), f'deleted change order #{coid}')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        proj_r = http.get(sb_url('proposals', f'?id=eq.{project_id}&select=snap'), headers=sb_headers(), timeout=5)
        rows = proj_r.json()
        if rows:
            snap = rows[0].get('snap') or {}
            if isinstance(snap, str):
                snap = json.loads(snap)
            snap['site_plan_url'] = public_url
            http.patch(
                sb_url('proposals', f'?id=eq.{project_id}'),
                headers=sb_headers(),
                json={'snap': snap},
                timeout=5
            )

        return jsonify({'ok': True, 'url': public_url})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
    safe_name = file.filename.replace(' ', '_').replace('/', '_')
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
        proj_r = http.get(sb_url('proposals', f'?id=eq.{project_id}&select=snap'), headers=sb_headers(), timeout=5)
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
                sb_url('proposals', f'?id=eq.{project_id}'),
                headers=sb_headers(),
                json={'snap': snap},
                timeout=5
            )

        return jsonify({'ok': True, 'url': public_url, 'name': file.filename, 'path': storage_path, 'size': len(file_data), 'type': ext})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/upload/project-file/<int:project_id>/delete', methods=['POST'])
@require_auth
def delete_project_file(project_id):
    """Delete a file attachment from a project."""
    data = request.get_json() or {}
    storage_path = data.get('path', '')
    if not storage_path:
        return jsonify({'ok': False, 'error': 'No path provided'}), 400

    svc_key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    try:
        # Delete from Supabase Storage
        http.delete(
            f'{SUPABASE_URL}/storage/v1/object/{FILES_BUCKET}/{storage_path}',
            headers={'apikey': svc_key, 'Authorization': f'Bearer {svc_key}'},
            timeout=10
        )

        # Remove from project snap.files[]
        proj_r = http.get(sb_url('proposals', f'?id=eq.{project_id}&select=snap'), headers=sb_headers(), timeout=5)
        rows = proj_r.json()
        if rows:
            snap = rows[0].get('snap') or {}
            if isinstance(snap, str):
                snap = json.loads(snap)
            snap['files'] = [f for f in (snap.get('files') or []) if f.get('path') != storage_path]
            http.patch(
                sb_url('proposals', f'?id=eq.{project_id}'),
                headers=sb_headers(),
                json={'snap': snap},
                timeout=5
            )

        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Setup: create hd_settings table if needed ───────────────────────────────

@app.route('/setup/settings-table', methods=['POST'])
@require_admin
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
@require_admin
def setup_user_fields():
    """Add profile fields and update role constraint to include 'field'."""
    sql = """
    ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS email TEXT DEFAULT '';
    ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT '';
    ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS avatar_data TEXT DEFAULT '';
    ALTER TABLE hd_users DROP CONSTRAINT IF EXISTS hd_users_role_check;
    ALTER TABLE hd_users ADD CONSTRAINT hd_users_role_check CHECK (role IN ('admin', 'user', 'field'));
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
@require_admin
def setup_notifications_table():
    """Create hd_notifications table. Run once."""
    if ensure_notif_table():
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Run this SQL manually in Supabase dashboard.', 'sql': _NOTIF_SQL.strip()})


@app.route('/notifications/list')
@require_auth
def notifications_list():
    """Get notifications for the current user."""
    username = session.get('username', '')
    try:
        r = http.get(
            sb_url('hd_notifications', f'?recipient=eq.{username}&dismissed=eq.false&order=created_at.desc&limit=50'),
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
            sb_url('hd_notifications', f'?recipient=eq.{username}&dismissed=eq.false&read=eq.false&select=id'),
            headers=sb_headers(), timeout=5)
        count = len(r.json()) if r.status_code == 200 else 0
        return jsonify({'ok': True, 'count': count})
    except Exception as e:
        return jsonify({'ok': True, 'count': 0})


@app.route('/notifications/read/<int:nid>', methods=['POST'])
@require_auth
def notifications_read(nid):
    try:
        http.patch(sb_url('hd_notifications', f'?id=eq.{nid}'), headers=sb_headers(), json={'read': True}, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/notifications/read-all', methods=['POST'])
@require_auth
def notifications_read_all():
    username = session.get('username', '')
    try:
        http.patch(sb_url('hd_notifications', f'?recipient=eq.{username}&read=eq.false'),
            headers=sb_headers(), json={'read': True}, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/notifications/dismiss/<int:nid>', methods=['POST'])
@require_auth
def notifications_dismiss(nid):
    try:
        http.patch(sb_url('hd_notifications', f'?id=eq.{nid}'), headers=sb_headers(), json={'dismissed': True}, timeout=5)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


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
        return jsonify({'ok': False, 'error': str(e)}), 500


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
            r = http.get(sb_url('hd_users', f'?username=eq.{username}&select=email,full_name'), headers=sb_headers(), timeout=5)
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
        r = http.get(sb_url('hd_settings', f'?key=eq.{key}&select=value'), headers=sb_headers(), timeout=5)
        rows = r.json()
        if rows and len(rows) > 0:
            return jsonify({'ok': True, 'value': rows[0]['value']})
        return jsonify({'ok': True, 'value': None})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        r = http.get(sb_url('hd_settings', f'?key=in.({key_filter})&select=key,value'), headers=sb_headers(), timeout=5)
        rows = r.json()
        values = {row['key']: row['value'] for row in rows}
        return jsonify({'ok': True, 'values': values})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/settings/save', methods=['POST'])
@require_auth
def settings_save():
    data = request.get_json() or {}
    key = data.get('key')
    value = data.get('value')
    if not key:
        return jsonify({'ok': False, 'error': 'Missing key'}), 400
    # Personal settings any user can save
    personal_keys = {'hd_notif_prefs', 'hd_sender'}
    # Shared business settings require admin role
    if key not in personal_keys and session.get('role') != 'admin':
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
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/bugs/list')
@require_admin
def list_bugs():
    try:
        r = http.get(f"{SUPABASE_URL}/rest/v1/hd_bug_reports?select=*&order=submitted_at.desc", headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': 'Failed to load bug reports', 'details': r.text[:500]}), r.status_code
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/bugs/<int:bug_id>', methods=['PATCH'])
@require_admin
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
        r = http.patch(f"{SUPABASE_URL}/rest/v1/hd_bug_reports?id=eq.{bug_id}", json=updates, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to update bug report', 'details': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ── Roadmap ──────────────────────────────────────────────
@app.route('/roadmap/list')
@require_admin
def list_roadmap():
    try:
        r = http.get(f"{SUPABASE_URL}/rest/v1/hd_roadmap?select=*&order=sort_order.asc,created_at.desc", headers=sb_admin_headers(), timeout=10)
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': 'Failed to load roadmap items', 'details': r.text[:500]}), r.status_code
        return jsonify({'ok': True, 'items': r.json()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/roadmap/save', methods=['POST'])
@require_admin
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
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/roadmap/<int:item_id>', methods=['PATCH'])
@require_admin
def update_roadmap(item_id):
    try:
        d = request.json or {}
        updates = {}
        for k in ('title', 'description', 'category', 'priority', 'effort', 'status', 'target_version', 'sort_order'):
            if k in d:
                updates[k] = d[k]
        updates['updated_at'] = datetime.utcnow().isoformat()
        r = http.patch(f"{SUPABASE_URL}/rest/v1/hd_roadmap?id=eq.{item_id}", json=updates, headers=sb_admin_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to update roadmap item', 'details': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/roadmap/<int:item_id>', methods=['DELETE'])
@require_admin
def delete_roadmap(item_id):
    try:
        r = http.delete(f"{SUPABASE_URL}/rest/v1/hd_roadmap?id=eq.{item_id}", headers=sb_admin_headers(prefer='return=minimal'), timeout=10)
        if r.status_code >= 300:
            return jsonify({'ok': False, 'error': 'Failed to delete roadmap item', 'details': r.text[:500]}), 400
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
