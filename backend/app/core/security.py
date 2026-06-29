from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from app.core.config import get_settings

settings = get_settings()
PASSWORD_SCHEME = 'pbkdf2_sha256'
PASSWORD_ITERATIONS = 390000


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def _b64decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(f'{value}{padding}'.encode('ascii'))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PASSWORD_ITERATIONS)
    return f'{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}'


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iteration_text, salt_text, digest_text = password_hash.split('$', 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iteration_text)
        salt = _b64decode(salt_text)
        expected_digest = _b64decode(digest_text)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return hmac.compare_digest(actual_digest, expected_digest)


def create_session_token(user_id: str) -> str:
    expires_at = int(time.time()) + settings.session_max_age_seconds
    nonce = secrets.token_hex(8)
    payload = f'{user_id}:{expires_at}:{nonce}'
    signature = hmac.new(settings.secret_key.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{payload}:{signature}'


def verify_session_token(token: str) -> str | None:
    try:
        user_id, expires_at_text, nonce, signature = token.rsplit(':', 3)
        payload = f'{user_id}:{expires_at_text}:{nonce}'
        expected_signature = hmac.new(
            settings.secret_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        expires_at = int(expires_at_text)
    except (ValueError, TypeError):
        return None

    if not hmac.compare_digest(signature, expected_signature):
        return None
    if expires_at < int(time.time()):
        return None
    return user_id
