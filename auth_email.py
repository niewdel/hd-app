"""
Gmail API sender for HD Hauling transactional emails (2FA codes, reset links).

Credentials are read from environment variables on first send; ImportError and
missing-credentials failures surface as RuntimeError so the caller can return
a 503 to the browser.

Required env vars:
    GMAIL_CLIENT_ID
    GMAIL_CLIENT_SECRET
    GMAIL_REFRESH_TOKEN
    GMAIL_SENDER_EMAIL   (defaults to admin@hdgrading.com)
"""
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build as _gmail_build
    _GMAIL_OK = True
except ImportError:
    _GMAIL_OK = False

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
    if not _GMAIL_OK:
        raise RuntimeError('Gmail libraries not installed')
    if not (_CLIENT_ID and _CLIENT_SECRET and _REFRESH_TOKEN):
        raise RuntimeError('Gmail credentials not configured (GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN)')
    creds = Credentials(
        token=None,
        refresh_token=_REFRESH_TOKEN,
        token_uri=_TOKEN_URI,
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        scopes=_SCOPES,
    )
    _service = _gmail_build('gmail', 'v1', credentials=creds, cache_discovery=False)
    return _service


def _send_raw(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    msg = MIMEMultipart('alternative')
    msg['To'] = to_email
    msg['From'] = f'HD Hauling <{_SENDER}>'
    msg['Subject'] = subject
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
    service = _get_service()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()


def send_2fa_code(to_email: str, code: str) -> None:
    subject = f'HD Hauling verification code: {code}'
    text = (f'Your HD Hauling login code is {code}. It expires in 10 minutes. '
            'If you did not request this, you can ignore this email.')
    html = f'''
    <div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#111;">
      <h2 style="margin:0 0 8px;color:#CC0000;">HD Hauling &amp; Grading</h2>
      <p>Use this code to finish signing in:</p>
      <p style="font-size:32px;letter-spacing:8px;font-weight:700;background:#f5f5f5;padding:16px;text-align:center;border-radius:6px;">{code}</p>
      <p style="color:#666;font-size:13px;">Expires in 10 minutes. If you did not try to log in, you can ignore this email.</p>
    </div>'''
    _send_raw(to_email, subject, html, text)


def send_reset_link(to_email: str, reset_url: str) -> None:
    subject = 'Reset your HD Hauling password'
    text = (f'Click this link to reset your password: {reset_url}\n\n'
            'Expires in 1 hour. If you did not request a reset, ignore this email.')
    html = f'''
    <div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#111;">
      <h2 style="margin:0 0 8px;color:#CC0000;">HD Hauling &amp; Grading</h2>
      <p>Click the button below to choose a new password. The link expires in 1 hour.</p>
      <p><a href="{reset_url}" style="display:inline-block;background:#CC0000;color:#fff;padding:12px 20px;text-decoration:none;border-radius:4px;font-weight:600;">Reset password</a></p>
      <p style="color:#666;font-size:13px;">If the button does not work, paste this URL into your browser:<br><span style="word-break:break-all;">{reset_url}</span></p>
      <p style="color:#666;font-size:13px;">If you did not request a reset, ignore this email.</p>
    </div>'''
    _send_raw(to_email, subject, html, text)
