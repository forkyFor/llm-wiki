"""Password hashing (PBKDF2-HMAC-SHA256) and JWT HS256 — stdlib only."""
import base64
import hashlib
import hmac
import json
import os
import time

from backend.config import settings

COOKIE_NAME = "llm_wiki_session"
_ITERATIONS = 480_000
_SALT_BYTES = 32


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    b64_salt = base64.b64encode(salt).decode()
    b64_hash = base64.b64encode(dk).decode()
    return f"$pbkdf2-sha256${_ITERATIONS}${b64_salt}${b64_hash}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, alg, iterations_str, b64_salt, b64_hash = stored.split("$")
        assert alg == "pbkdf2-sha256"
        iterations = int(iterations_str)
        salt = base64.b64decode(b64_salt)
        expected = base64.b64decode(b64_hash)
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(dk, expected)


# ── JWT HS256 — manual implementation ─────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _sign(header_b64: str, payload_b64: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    secret = settings.jwt_secret.encode()
    sig = hmac.new(secret, msg, hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_token(user_id: int, username: str, is_admin: bool) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    payload = _b64url_encode(json.dumps({
        "sub": str(user_id),
        "usr": username,
        "adm": is_admin,
        "iat": now,
        "exp": now + settings.jwt_expire_hours * 3600,
    }).encode())
    sig = _sign(header, payload)
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")

    expected_sig = _sign(header_b64, payload_b64)
    if not hmac.compare_digest(expected_sig, sig_b64):
        raise ValueError("Invalid signature")

    payload = json.loads(_b64url_decode(payload_b64))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token expired")
    return payload
