"""
Security helpers for HD Hauling app.

Imported by app.py. Zero side effects at import time.
"""
import hashlib
import hmac
import secrets
import time
from typing import Tuple

import bcrypt
from itsdangerous import URLSafeTimedSerializer

BCRYPT_COST = 12


def _is_legacy_sha256(stored: str) -> bool:
    """Legacy SHA-256 hashes are exactly 64 lowercase hex chars."""
    return len(stored) == 64 and all(c in '0123456789abcdef' for c in stored.lower())


def hash_password(pw: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt(rounds=BCRYPT_COST)).decode('utf-8')


def verify_password(pw: str, stored: str) -> Tuple[bool, bool]:
    """Return (is_valid, needs_rehash).

    needs_rehash is True when the stored value is a legacy SHA-256 hash and the
    password matched — caller should rehash with bcrypt on next successful login.
    """
    if not stored:
        return (False, False)
    if _is_legacy_sha256(stored):
        legacy = hashlib.sha256(pw.encode('utf-8')).hexdigest()
        return (hmac.compare_digest(legacy, stored), True)
    try:
        return (bcrypt.checkpw(pw.encode('utf-8'), stored.encode('utf-8')), False)
    except (ValueError, TypeError):
        return (False, False)


# --------------------------------------------------------------------------
# Rate limiter
# In-memory per-process. Fine for a single-worker Railway deployment.
# Bucket values are lists of unix timestamps for recent attempts.
# --------------------------------------------------------------------------
_rate_buckets: dict = {}


def rate_limit_check(key: str, max_attempts: int, window_s: int) -> Tuple[bool, int]:
    """Return (allowed, retry_after_seconds). Records the attempt if allowed."""
    now = time.time()
    cutoff = now - window_s
    bucket = [t for t in _rate_buckets.get(key, []) if t > cutoff]
    if len(bucket) >= max_attempts:
        retry = int(bucket[0] + window_s - now) + 1
        _rate_buckets[key] = bucket
        return (False, max(retry, 1))
    bucket.append(now)
    _rate_buckets[key] = bucket
    return (True, 0)


def rate_limit_record_failure(key: str, window_s: int) -> None:
    """Record a failure timestamp without a pre-check."""
    now = time.time()
    bucket = [t for t in _rate_buckets.get(key, []) if t > now - window_s]
    bucket.append(now)
    _rate_buckets[key] = bucket


# --------------------------------------------------------------------------
# 2FA codes
# --------------------------------------------------------------------------
def generate_2fa_code() -> str:
    """Return a 6-digit zero-padded numeric code."""
    return f'{secrets.randbelow(1_000_000):06d}'


def hash_2fa_code(code: str) -> str:
    """SHA-256 hex of a short-lived single-use code. Fine given use case."""
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


# --------------------------------------------------------------------------
# CSRF double-submit
# --------------------------------------------------------------------------
def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(cookie_token: str, header_token: str) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)


# --------------------------------------------------------------------------
# Signed reset tokens (stateless body; consumption tracked in DB)
# --------------------------------------------------------------------------
def make_reset_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt='hd-reset-v1')


def sign_reset_token(serializer: URLSafeTimedSerializer, user_id: int) -> str:
    return serializer.dumps({'uid': int(user_id)})


def verify_reset_token(serializer: URLSafeTimedSerializer, token: str, max_age_s: int) -> int:
    """Return user_id or raise BadSignature/SignatureExpired."""
    data = serializer.loads(token, max_age=max_age_s)
    return int(data['uid'])


# --------------------------------------------------------------------------
# UX helpers
# --------------------------------------------------------------------------
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
    if '@' not in email:
        return False
    if not email.endswith('@hdgrading.com'):
        return False
    local = email.split('@', 1)[0]
    return len(local) >= 1
