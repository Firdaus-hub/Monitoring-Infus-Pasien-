import hashlib
import secrets


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt. Simple and dependency-free."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, hashed = stored_hash.split("$")
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except ValueError:
        return False
