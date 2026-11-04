"""Server-side password checks and short-lived, revocable sessions."""

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

_sessions = {}
_attempts = deque()
_lock = threading.Lock()
SESSION_SECONDS = 8 * 60 * 60


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000)
    return f'pbkdf2_sha256$600000${salt.hex()}${digest.hex()}'


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt, digest = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or int(rounds) != 600_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual.hex(), digest)
    except (ValueError, TypeError):
        return False


def login(username, password):
    configured_user = os.getenv('WEB_USERNAME')
    configured_hash = os.getenv('WEB_PASSWORD_HASH')
    if not configured_user or not configured_hash:
        raise HTTPException(503, '管理者尚未設定查詢帳號密碼。')
    now = time.monotonic()
    with _lock:
        while _attempts and _attempts[0] < now - 60:
            _attempts.popleft()
        if len(_attempts) >= 20:
            raise HTTPException(429, '登入次數過多，請一分鐘後再試。')
        _attempts.append(now)
    password_ok = verify_password(password, configured_hash)
    if not hmac.compare_digest(username.encode(), configured_user.encode()) or not password_ok:
        raise HTTPException(401, '帳號或密碼錯誤。')
    token = secrets.token_urlsafe(32)
    with _lock:
        expired = [key for key, value in _sessions.items() if value < now]
        for key in expired:
            del _sessions[key]
        if len(_sessions) >= 500:
            raise HTTPException(503, '目前登入人數已滿，請稍後再試。')
        _sessions[hashlib.sha256(token.encode()).hexdigest()] = now + SESSION_SECONDS
    return token


def require_session(request: Request):
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 200:
        raise HTTPException(401, '請先登入後再查詢。')
    key = hashlib.sha256(header[7:].encode()).hexdigest()
    with _lock:
        expires = _sessions.get(key, 0)
        if expires <= time.monotonic():
            _sessions.pop(key, None)
            raise HTTPException(401, '登入已過期，請重新登入。')
    return key


def logout(request: Request):
    key = require_session(request)
    with _lock:
        _sessions.pop(key, None)
