import os, tempfile, functools
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

APP_PIN         = os.environ.get('APP_PIN', '2025')
NOTION_KEY      = os.environ.get('NOTION_KEY', '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')
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

@app.route('/generate-pdf', methods=['POST'])
@require_auth
def generate_pdf():
    tmp_path = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        if not data.get('project_name'):
            return jsonify({'error': 'project_name is required'}), 400
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
        build(data, tmp_path)
        with open(tmp_path, 'rb') as f:
            pdf_bytes = f.read()
        project_name = data.get('project_name', 'Proposal').replace(' ', '_')
        return app.response_class(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="HD_Proposal_{project_name}.pdf"',
                'Content-Length': len(pdf_bytes),
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.unlink(tmp_path)
            except: pass


@app.route('/generate-docx', methods=['POST'])
@require_auth
def generate_docx_route():
    try:
        data = request.get_json(force=True)
        buf  = generate_docx.build(data)
        fname = (data.get('project_name','Proposal') or 'Proposal').replace(' ','_')
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', as_attachment=True, download_name=f'HD_Proposal_{fname}.docx')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/send-email', methods=['POST'])
@require_auth
def send_email_route():
    if not GMAIL_AVAILABLE:
        return jsonify({'error': 'Gmail API not installed on server.'}), 500
    data       = request.get_json(force=True)
    to         = data.get('to','').strip()
    subject    = data.get('subject','').strip()
    body_text  = data.get('body','').strip()
    pdf_b64    = data.get('pdf_b64','')
    pdf_fn     = data.get('pdf_filename','HD_Proposal.pdf')
    if not to or not subject:
        return jsonify({'error': 'Recipient and subject required'}), 400
    token_json = os.environ.get('GMAIL_TOKEN_JSON','')
    if not token_json:
        return jsonify({'error': 'Gmail not configured. Add GMAIL_TOKEN_JSON to Railway environment variables.'}), 500
    try:
        import json as _j
        td = _j.loads(token_json)
        creds = Credentials(
            token=td.get('token'), refresh_token=td.get('refresh_token'),
            token_uri=td.get('token_uri','https://oauth2.googleapis.com/token'),
            client_id=td.get('client_id'), client_secret=td.get('client_secret'),
            scopes=td.get('scopes',['https://www.googleapis.com/auth/gmail.send'])
        )
        msg = MIMEMultipart()
        msg['to'] = to; msg['subject'] = subject
        msg.attach(MIMEText(body_text, 'plain'))
        if pdf_b64:
            pdf_bytes = base64.b64decode(pdf_b64)
            part = MIMEBase('application','pdf'); part.set_payload(pdf_bytes)
            email_encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{pdf_fn}"')
            msg.attach(part)
        svc = gmail_build('gmail','v1',credentials=creds)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        svc.users().messages().send(userId='me', body={'raw': raw}).execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/notion/clients')
@require_auth
def notion_clients():
    try:
        r = http.post(
            f'https://api.notion.com/v1/databases/{NOTION_CLIENTS}/query',
            headers={'Authorization': f'Bearer {NOTION_KEY}', 'Notion-Version': NOTION_VER, 'Content-Type': 'application/json'},
            json={'page_size': 100}, timeout=10
        )
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/notion/push', methods=['POST'])
@require_auth
def notion_push():
    try:
        data = request.get_json() or {}
        payload = {
            'parent': {'database_id': NOTION_PIPELINE},
            'properties': {
                'Project Name': {'title': [{'text': {'content': data.get('project_name','')}}]},
                'Scope Notes':  {'rich_text': [{'text': {'content': data.get('client_name','') + ' | ' + data.get('address','')}}]},
                
                'Due Date':     {'date': {'start': data.get('date_iso', '')}} if data.get('date_iso') else None,
                'Status':    {'select': {'name': 'Quoted'}},
                
                
            }
        }
        r = http.post(
            'https://api.notion.com/v1/pages',
            headers={'Authorization': f'Bearer {NOTION_KEY}', 'Notion-Version': NOTION_VER, 'Content-Type': 'application/json'},
            json=payload, timeout=10
        )
        resp = r.json()
        if r.ok:
            pid = resp.get('id','').replace('-','')
            return jsonify({'ok': True, 'url': f'https://notion.so/{pid}'})
        return jsonify({'error': resp.get('message','Notion error')}), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/generate-co-pdf', methods=['POST'])
@require_auth
def generate_co_pdf():
    data = request.get_json(force=True)
    try:
        from generate_change_order import build as co_build
        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        tmp.close()
        co_build(data, tmp.name)
        with open(tmp.name, 'rb') as f:
            pdf_bytes = f.read()
        os.unlink(tmp.name)
        from flask import Response
        return Response(pdf_bytes, mimetype='application/pdf',
            headers={'Content-Disposition': 'attachment; filename=change_order.pdf'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
