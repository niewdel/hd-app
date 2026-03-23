import os, tempfile, functools, json
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
import db  # quote storage

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'hd-hauling-dev-key')

APP_PIN         = os.environ.get('APP_PIN', '2025')
NOTION_KEY      = os.environ.get('NOTION_KEY', '')
NOTION_PIPELINE = os.environ.get('NOTION_PIPELINE', '2ada1cc5891b80bebe53fde6c337bf8b')
NOTION_CLIENTS  = os.environ.get('NOTION_CLIENTS',  '2ada1cc5891b804cbaa1c4d2577b674c')
NOTION_VER      = '2022-06-28'

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ── Static / Auth ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/auth/login', methods=['POST'])
def login():
    pin = str((request.get_json() or {}).get('pin', '')).strip()
    if pin == APP_PIN:
        session['authenticated'] = True
        session.permanent = True
        return jsonify({'ok': True})
    return jsonify({'error': 'Incorrect PIN'}), 401

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/auth/check')
def auth_check():
    return jsonify({'authenticated': bool(session.get('authenticated'))})

# ── Quote Storage ─────────────────────────────────────────────────────────────

@app.route('/quotes/save', methods=['POST'])
@require_auth
def quotes_save():
    data = request.get_json() or {}
    try:
        qid = db.save_quote(
            name   = data.get('name', 'Unnamed'),
            client = data.get('client', ''),
            date   = data.get('date', ''),
            total  = data.get('total', 0),
            snap   = json.dumps(data.get('snap', {}))
        )
        return jsonify({'ok': True, 'id': qid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/quotes/list')
@require_auth
def quotes_list():
    try:
        quotes = db.list_quotes()
        # Parse snap back to object so the client gets it as JSON
        for q in quotes:
            try:
                q['snap'] = json.loads(q['snap'])
            except Exception:
                pass
        return jsonify({'ok': True, 'quotes': quotes})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/quotes/delete/<int:qid>', methods=['DELETE'])
@require_auth
def quotes_delete(qid):
    try:
        db.delete_quote(qid)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ── PDF / DOCX ────────────────────────────────────────────────────────────────

@app.route('/generate-pdf', methods=['POST'])
@require_auth
def generate_pdf():
    data = request.get_json()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        out = f.name
    try:
        build(data, out)
        return send_file(out, mimetype='application/pdf',
                         as_attachment=True,
                         download_name='HD_Proposal.pdf')
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
                         as_attachment=True,
                         download_name='HD_Proposal.docx')
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
        return send_file(out, mimetype='application/pdf',
                         as_attachment=True,
                         download_name='HD_ChangeOrder.pdf')
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
        return send_file(out, mimetype='application/pdf',
                         as_attachment=True,
                         download_name='HD_JobCost.pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Email ─────────────────────────────────────────────────────────────────────

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

    data    = request.get_json() or {}
    to      = data.get('to', '')
    subject = data.get('subject', '')
    body    = data.get('body', '')
    pdf_b64 = data.get('pdf_b64', '')
    fname   = data.get('pdf_filename', 'HD_Proposal.pdf')

    try:
        token_json = os.environ.get('GMAIL_TOKEN_JSON', '')
        if not token_json:
            return jsonify({'ok': False, 'error': 'Gmail token not configured'}), 500
        creds = Credentials.from_authorized_user_info(json.loads(token_json))
        service = gmail_build('gmail', 'v1', credentials=creds)

        msg = MIMEMultipart()
        msg['to'] = to
        msg['subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        if pdf_b64:
            part = MIMEBase('application', 'pdf')
            part.set_payload(base64.b64decode(pdf_b64))
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{fname}"')
            msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ── Notion ────────────────────────────────────────────────────────────────────

def notion_headers():
    return {
        'Authorization': f'Bearer {NOTION_KEY}',
        'Notion-Version': NOTION_VER,
        'Content-Type': 'application/json'
    }

@app.route('/notion/push', methods=['POST'])
@require_auth
def notion_push():
    if not NOTION_KEY:
        return jsonify({'ok': False, 'error': 'Notion not configured'}), 500
    data = request.get_json() or {}
    payload = {
        'parent': {'database_id': NOTION_PIPELINE},
        'properties': {
            'Name': {'title': [{'text': {'content': data.get('project_name','')}}]},
            'Client': {'rich_text': [{'text': {'content': data.get('client_name','')}}]},
            'Address': {'rich_text': [{'text': {'content': data.get('address','')}}]},
            'Date': {'date': {'start': data.get('date_iso','')} if data.get('date_iso') else None},
            'Total': {'number': float(data.get('total', 0))},
        }
    }
    try:
        r = http.post('https://api.notion.com/v1/pages',
                      headers=notion_headers(), json=payload, timeout=10)
        if r.ok:
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': r.text}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/notion/clients')
@require_auth
def notion_clients():
    if not NOTION_KEY:
        return jsonify({'results': []}), 200
    try:
        r = http.post(f'https://api.notion.com/v1/databases/{NOTION_CLIENTS}/query',
                      headers=notion_headers(), json={}, timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=5000)
