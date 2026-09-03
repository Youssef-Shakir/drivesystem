"""
PIN gate for the dashboard.

This is a shared-terminal deterrent (so a customer glancing at an unlocked
tab, or someone finding the dashboard on the LAN, can't fiddle with sensor
thresholds or volumes) - not a security boundary meant to withstand a
determined attacker. Keep the intercom off the public internet regardless
of this.
"""

import hashlib
import hmac
import logging
import secrets
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SESSION_COOKIE = "dt_session"
# Staff shouldn't have to re-enter the PIN every day - a long-lived session
# is fine here since the PIN itself is the actual gate.
SESSION_MAX_AGE_SEC = 30 * 24 * 3600

_SECRET_PATH = Path(__file__).resolve().parent.parent / ".session_secret"


def _load_or_create_secret() -> bytes:
    if _SECRET_PATH.exists():
        return _SECRET_PATH.read_bytes()
    secret = secrets.token_bytes(32)
    _SECRET_PATH.write_bytes(secret)
    _SECRET_PATH.chmod(0o600)
    return secret


_SECRET = _load_or_create_secret()


def make_session_token() -> str:
    """issued_at:hmac(issued_at) - stateless, no server-side session store needed."""
    issued_at = str(int(time.time()))
    sig = hmac.new(_SECRET, issued_at.encode(), hashlib.sha256).hexdigest()
    return f"{issued_at}:{sig}"


def verify_session_token(token: str | None) -> bool:
    if not token or ":" not in token:
        return False
    issued_at, sig = token.split(":", 1)
    expected = hmac.new(_SECRET, issued_at.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        return (time.time() - int(issued_at)) <= SESSION_MAX_AGE_SEC
    except ValueError:
        return False


def verify_pin(submitted: str, expected: str) -> bool:
    return hmac.compare_digest(submitted.strip(), expected.strip())


# --- Light throttling against PIN guessing. This is a 4-digit PIN (10,000
# combinations) on a LAN dashboard, not a bank vault - just enough to stop
# a trivial script from brute-forcing it in a few seconds. ---
_attempts: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
WINDOW_SEC = 60


def is_rate_limited(client_ip: str) -> bool:
    now = time.time()
    history = [t for t in _attempts.get(client_ip, []) if now - t < WINDOW_SEC]
    _attempts[client_ip] = history
    return len(history) >= MAX_ATTEMPTS


def record_attempt(client_ip: str) -> None:
    _attempts.setdefault(client_ip, []).append(time.time())


def login_page_html(error: str | None = None) -> str:
    error_html = f'<div class="error">{error}</div>' if error else ""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Drive-Thru Intercom - Sign In</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{
        margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
        background: #ECE9D8; font-family: Tahoma, Arial, sans-serif; color: #000;
    }}
    .box {{
        background: #FFFFFF; border: 2px groove #808080; padding: 28px 32px; width: 260px;
        box-shadow: 4px 4px 10px rgba(0,0,0,0.25);
    }}
    h1 {{ font-size: 1.1rem; margin: 0 0 4px; color: #CC0000; }}
    p.sub {{ margin: 0 0 18px; font-size: 0.75rem; color: #4A4A4A; }}
    input[type=password] {{
        width: 100%; font-size: 1.4rem; letter-spacing: 8px; text-align: center; padding: 8px 0;
        border: 2px inset #808080; margin-bottom: 14px;
    }}
    button {{
        width: 100%; padding: 8px; font-size: 0.9rem; background: #D4D0C8; border: 2px outset #808080;
        cursor: pointer;
    }}
    button:active {{ border-style: inset; }}
    .error {{
        background: #FFE0E0; border: 1px solid #CC0000; color: #CC0000; font-size: 0.75rem;
        padding: 6px 8px; margin-bottom: 14px;
    }}
</style>
</head>
<body>
    <form class="box" method="POST" action="/login">
        <h1>Drive-Thru Intercom</h1>
        <p class="sub">Enter PIN to continue</p>
        {error_html}
        <input type="password" name="pin" inputmode="numeric" pattern="[0-9]*" maxlength="8" autofocus autocomplete="off">
        <button type="submit">Unlock</button>
    </form>
</body>
</html>"""
