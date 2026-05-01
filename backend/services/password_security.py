"""Password security: hashing, complexity validation, HIBP check.

Strategy:
  - **Hashing**: Argon2id is the algorithm of choice for new passwords.
    `argon2-cffi` (BSD-3) implements the OWASP-recommended params.
    Existing bcrypt hashes are still verified seamlessly; on next successful
    login they are silently rehashed to Argon2id (`needs_rehash` mechanism).
  - **Complexity**: minimum 8 characters, at least 1 uppercase letter and at
    least 1 digit OR symbol. We deliberately keep the rule simple and easy to
    explain — research shows that long passphrases beat complex-but-short.
  - **HIBP check**: privacy-preserving k-anonymity (only first 5 chars of
    SHA-1 are sent over HTTPS to the public API at api.pwnedpasswords.com).
    Returns True if the password has appeared in a known breach.
"""
from __future__ import annotations

import hashlib
import logging
import re

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

logger = logging.getLogger(__name__)

# Argon2id parameters per OWASP 2024 minimum:
#   memory=46_336 KiB (~45 MiB), time=1, parallelism=1
# These are the library defaults from argon2-cffi which already match.
_ph = PasswordHasher()


# ─── Complexity validation ───────────────────────────────────────────────────
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128
_RE_UPPER = re.compile(r"[A-Z]")
_RE_DIGIT_OR_SYMBOL = re.compile(r"[0-9!@#$%^&*()_\-+=\[\]{};:'\",.<>/?\\|`~]")


def validate_complexity(password: str) -> str | None:
    """Return None if the password meets the policy; otherwise an error msg
    in Bulgarian (frontend i18n is responsible for re-translating using the
    backend response)."""
    if not password:
        return "Паролата е задължителна."
    if len(password) < PASSWORD_MIN_LEN:
        return f"Паролата трябва да е поне {PASSWORD_MIN_LEN} символа."
    if len(password) > PASSWORD_MAX_LEN:
        return f"Паролата трябва да е най-много {PASSWORD_MAX_LEN} символа."
    if not _RE_UPPER.search(password):
        return "Паролата трябва да съдържа поне една главна буква."
    if not _RE_DIGIT_OR_SYMBOL.search(password):
        return "Паролата трябва да съдържа поне една цифра или специален символ."
    return None


# ─── Hashing & verification (Argon2id with bcrypt backwards compat) ──────────
def hash_password(password: str) -> str:
    """Hash a new password with Argon2id."""
    return _ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify against either Argon2id ($argon2…) or legacy bcrypt ($2b$…)."""
    if not hashed:
        return False
    try:
        if hashed.startswith("$argon2"):
            try:
                _ph.verify(hashed, plain)
                return True
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return False
        # Bcrypt fallback (legacy accounts)
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """True if the stored hash is bcrypt OR an outdated Argon2 parameter set.
    Caller should rehash with `hash_password(plaintext)` and persist on the
    next successful authentication.
    """
    if not hashed:
        return False
    if not hashed.startswith("$argon2"):
        return True  # legacy bcrypt → migrate
    try:
        return _ph.check_needs_rehash(hashed)
    except Exception:
        return True


# ─── HIBP k-anonymity check ──────────────────────────────────────────────────
async def is_password_pwned(password: str, *, timeout: float = 3.0) -> bool:
    """Returns True if the password appears in HaveIBeenPwned's breach
    corpus. Privacy-preserving: only the first 5 chars of the SHA-1 hash
    are transmitted; the API returns a list of suffixes which we match
    locally.

    Failure modes (network down, timeout, etc.) → returns False so that
    HIBP availability never blocks user registration.
    """
    if not password:
        return False
    try:
        import httpx  # local import — keeps cold-start light
    except Exception:
        return False
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    url = f"https://api.pwnedpasswords.com/range/{prefix}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers={"Add-Padding": "true"})
        if r.status_code != 200:
            return False
        for line in r.text.splitlines():
            parts = line.split(":")
            if len(parts) < 2:
                continue
            if parts[0].strip().upper() == suffix:
                # Found — count is parts[1]; we only care about the boolean
                return True
    except Exception as e:
        logger.warning("HIBP lookup failed: %s", e)
        return False
    return False
