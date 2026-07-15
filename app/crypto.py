"""Symmetric encryption for cookies / sensitive payloads stored on disk."""
from cryptography.fernet import Fernet
from .config import Config


def _load_or_create_key() -> bytes:
    if Config.FERNET_KEY_PATH.exists():
        return Config.FERNET_KEY_PATH.read_bytes().strip()
    import os
    env_key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if env_key:
        Config.FERNET_KEY_PATH.write_bytes(env_key.encode())
        return env_key.encode()
    k = Fernet.generate_key()
    Config.FERNET_KEY_PATH.write_bytes(k)
    return k


_KEY = _load_or_create_key()
_FERNET = Fernet(_KEY)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return ""
    return _FERNET.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _FERNET.decrypt(token.encode()).decode()
    except Exception:
        return ""
