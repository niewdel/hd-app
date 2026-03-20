import os, json, tempfile, time
from collections import defaultdict
from flask import Flask, request, send_file, jsonify, redirect
from generate_proposal import build

app = Flask(__name__, static_folder='.', static_url_path='')

# ── Config ─────────────────────────────────────────────────────────────────────
APP_PIN = os.environ.get('APP_PIN', '1234')   # Set APP_PIN env var on Railway to change

# ── Simple in-memory rate limiter ──────────────────────────────────────────────
_rate_store = defaultdict(list)
RATE_LIMIT   = 30    # max requests
RATE_WINDOW  = 3600  # per hour (seconds)

def is_rate_limited(ip):
    now = time.time()
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < RATE_WINDOW]
    if len(_rate_store[ip]) >= RATE_LIMIT:
        return True
    _rate_store[ip].append(now)
    return False

# ── HTTPS redirect in production ───────────────────────────────────────────────
@app.before_request
def enforce_https():
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        if request.headers.get('X-Forwarded-Proto', 'https') == 'http':
            return redirect(request.url.replace('http://', 'https://'), 301)

# ── PIN verification ───────────────────────────────────────────────────────────
@app.route('/verify-pin', methods=['POST'])
def verify_pin():
    data = request.get_json() or {}
    pin  = str(data.get('pin', '')).strip()
    if pin == APP_PIN:
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Incorrect PIN'}), 401

# ── PDF generation ─────────────────────────────────────────────────────────────
@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if is_rate_limited(ip):
        return jsonify({'error': 'Rate limit exceeded. Max 30 PDFs per hour.'}), 429

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Basic validation
        if not isinstance(data.get('line_items', []), list):
            return jsonify({'error': 'Invalid line_items'}), 400
        if not isinstance(data.get('total', 0), (int, float)):
            return jsonify({'error': 'Invalid total'}), 400

        # Sanitise project name for filename
        proj_raw  = str(data.get('project_name', 'Proposal'))
        proj_safe = ''.join(c for c in proj_raw if c.isalnum() or c in ' _-').strip() or 'Proposal'
        filename  = f"HD_Proposal_{proj_safe.replace(' ', '_')}.pdf"

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name

        build(data, tmp_path)

        return send_file(
            tmp_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        app.logger.error(f'PDF generation error: {e}')
        return jsonify({'error': 'PDF generation failed. Check your quote data and try again.'}), 500
    finally:
        try:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '1.0.0'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = not bool(os.environ.get('RAILWAY_ENVIRONMENT'))
    app.run(host='0.0.0.0', port=port, debug=debug)
