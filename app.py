import os, tempfile, functools, json, hashlib
from flask import Flask, request, jsonify, session, send_file
from generate_proposal import build
try:
    from googleapiclient.discovery import build as gmail_build
    from google.oauth2.credentials import Credentials
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
import generate_docx
import requests as http

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'hd-hauling-dev-key')

APP_PIN        = os.environ.get('APP_PIN', '2025')
SUPABASE_URL   = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY   = os.environ.get('SUPABASE_KEY', '')

def sb_headers():
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def sb_url(table, params=''):
    return f'{SUPABASE_URL}/rest/v1/{table}{params}'

def hash_pin(pin):
    return hashlib.sha256(str(pin).encode()).hexdigest()

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
    pin = str(data.get('pin', '')).strip()
    users_ok = False
    try:
        r = http.get(sb_url('hd_users', f'?username=eq.{username}&active=eq.true&limit=1'),
                     headers=sb_headers(), timeout=5)
        if r.status_code == 200:
            users_ok = True
            rows = r.json()
            if rows and rows[0].get('pin_hash') == hash_pin(pin):
                user = rows[0]
                session['authenticated'] = True
                session['username'] = user['username']
                session['full_name'] = user.get('full_name', username)
                session['role'] = user.get('role', 'user')
                session.permanent = True
                log_access(user['username'], user.get('full_name',''), 'login', True)
                return jsonify({'ok': True, 'role': session['role'], 'full_name': session['full_name']})
            else:
                log_access(username, '', 'login', False)
                return jsonify({'error': 'Incorrect username or PIN'}), 401
    except Exception:
        pass
    if not users_ok and pin == APP_PIN:
        session['authenticated'] = True
        session['username'] = 'admin'
        session['full_name'] = 'Admin'
        session['role'] = 'admin'
        session.permanent = True
        return jsonify({'ok': True, 'role': 'admin', 'full_name': 'Admin'})
    return jsonify({'error': 'Incorrect username or PIN'}), 401

@app.route('/auth/logout', methods=['POST'])
def logout():
    if session.get('username'):
        log_access(session.get('username',''), session.get('full_name',''), 'logout', True)
    session.clear()
    return jsonify({'ok': True})

@app.route('/auth/check')
def auth_check():
    return jsonify({'authenticated': bool(session.get('authenticated')), 'role': session.get('role','user'), 'username': session.get('username',''), 'full_name': session.get('full_name','')})

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
        return jsonify({'ok': True, 'id': qid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/quotes/list')
@require_auth
def quotes_list():
    try:
        r = http.get(sb_url('proposals', '?select=*&order=created_at.desc'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
        return jsonify({'ok': True, 'quotes': r.json()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/quotes/delete/<int:qid>', methods=['DELETE'])
@require_auth
def quotes_delete(qid):
    try:
        r = http.delete(sb_url('proposals', f'?id=eq.{qid}'), headers=sb_headers(), timeout=10)
        r.raise_for_status()
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
            sb_url('proposals', '?select=*,pipeline_stages!left(name,color,counts_in_ratio,is_closed)&order=created_at.desc'),
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
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/projects/create', methods=['POST'])
@require_auth
def project_create():
    data = request.get_json() or {}
    try:
        snap = {
            'is_project': True,
            'address': data.get('address', ''),
            'city_state': data.get('city_state', ''),
            'bid_due_date': data.get('bid_due_date', ''),
            'bid_due_time': data.get('bid_due_time', ''),
            'notes': data.get('notes', ''),
            'linked_proposals': [],
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
        return jsonify({'ok': True, 'id': result[0]['id'] if result else None})
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


@app.route('/admin/users', methods=['GET'])
@require_admin
def get_users():
    try:
        r = http.get(sb_url('hd_users', '?order=created_at.asc'), headers=sb_headers(), timeout=5)
        users = r.json() if r.status_code == 200 else []
        for u in users: u.pop('pin_hash', None)
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
    role = data.get('role','user')
    if not username or not pin: return jsonify({'ok':False,'error':'Username and PIN required'}), 400
    if role not in ('admin','user'): role = 'user'
    try:
        r = http.post(sb_url('hd_users'), headers=sb_headers(), json={'username':username,'full_name':full_name,'pin_hash':hash_pin(pin),'role':role,'active':True,'created_by':session.get('username','admin')}, timeout=5)
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
    if 'username' in data and data['username']:
        new_un = str(data['username']).strip().lower()
        if new_un: update['username'] = new_un
    if 'role' in data and data['role'] in ('admin','user'): update['role'] = data['role']
    if 'active' in data: update['active'] = bool(data['active'])
    if 'pin' in data and data['pin']: update['pin_hash'] = hash_pin(data['pin'])
    if not update: return jsonify({'ok':False,'error':'Nothing to update'}), 400
    try:
        headers = {**sb_headers(), 'Prefer': 'return=representation'}
        r = http.patch(sb_url('hd_users', f'?id=eq.{uid}'), headers=headers, json=update, timeout=5)
        if r.status_code not in (200, 204):
            return jsonify({'ok': False, 'error': r.text}), 400
        rows = r.json() if r.status_code == 200 else []
        if isinstance(rows, list) and len(rows) == 0:
            return jsonify({'ok': False, 'error': 'User not found'}), 404
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)}), 500

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

@app.route('/change-orders/save', methods=['POST'])
@require_auth
def co_save():
    data = request.get_json() or {}
    try:
        snap = {
            'line_items': data.get('line_items', []),
            'orig_contract_amount': data.get('orig_contract_amount', 0),
            'description': data.get('description', ''),
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
