import os, tempfile, functools
from flask import Flask, request, jsonify, session
from generate_proposal import build
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

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
