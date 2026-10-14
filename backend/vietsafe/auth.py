"""User accounts and session management."""
import hashlib
import hmac
import secrets
import time
from .db import connect

def hash_password(pwd):
    """Salted PBKDF2 password hash; no deterministic password fingerprints."""
    salt=secrets.token_bytes(16)
    rounds=310_000
    digest=hashlib.pbkdf2_hmac('sha256',pwd.encode('utf-8'),salt,rounds)
    return f'pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}'


def verify_password(password, stored):
    """Verify PBKDF2 and legacy unsalted SHA-256 (for backward compatibility)."""
    if not isinstance(stored,str):
        return False
    try:
        if stored.startswith('pbkdf2_sha256$'):
            algorithm, count, salt, digest=stored.split('$')
            rounds=int(count)
            if not 100_000<=rounds<=2_000_000:
                return False
            expected=bytes.fromhex(digest)
            actual=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),rounds)
            return hmac.compare_digest(actual,expected)
        if len(stored)==64 and all(c in '0123456789abcdef' for c in stored):
            return hmac.compare_digest(stored,hashlib.sha256(password.encode('utf-8')).hexdigest())
    except (ValueError,TypeError):
        pass
    return False


def create_session(username):
    token = secrets.token_hex(32)
    now = time.time()
    with connect() as db:
        # Clean expired sessions
        db.execute('DELETE FROM sessions WHERE expires_at < ?', (now,))
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token, username, now, now + 86400))
    return token


def get_user_by_session(token):
    if not token:
        return None
    with connect() as db:
        row = db.execute(
            'SELECT u.username, u.display_name, u.role FROM sessions s '
            'JOIN users u ON s.username=u.username WHERE s.token=? AND s.expires_at>?',
            (token, time.time())
        ).fetchone()
    return dict(row) if row else None
