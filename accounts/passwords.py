from __future__ import annotations

import secrets
import string


def generate_temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%*-_"
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%*-_"),
    ]
    remaining = [secrets.choice(alphabet) for _ in range(max(length - len(required), 0))]
    chars = required + remaining
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
