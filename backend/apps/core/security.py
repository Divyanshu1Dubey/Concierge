"""Security utilities for credential encryption, secret masking, and origin validation."""
import base64
import os
import re
from urllib.parse import urlparse
from django.conf import settings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import hashlib

def _get_encryption_key() -> bytes:
    """Derive 256-bit AES key from Django SECRET_KEY."""
    raw = getattr(settings, 'SECRET_KEY', 'default-insecure-key').encode('utf-8')
    return hashlib.sha256(raw).digest()

def encrypt_secret(plain_text: str) -> str:
    """Encrypt a secret string using AES-256-GCM. Returns base64 encoded string."""
    if not plain_text:
        return ""
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    encrypted = aesgcm.encrypt(nonce, plain_text.encode('utf-8'), None)
    payload = nonce + encrypted
    return base64.b64encode(payload).decode('utf-8')

def decrypt_secret(encrypted_text: str) -> str:
    """Decrypt an AES-256-GCM encrypted secret string."""
    if not encrypted_text:
        return ""
    try:
        payload = base64.b64decode(encrypted_text.encode('utf-8'))
        nonce = payload[:12]
        encrypted = payload[12:]
        key = _get_encryption_key()
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, encrypted, None)
        return decrypted.decode('utf-8')
    except Exception:
        # Fallback in case raw text was passed during transition
        return encrypted_text

SENSITIVE_KEYS = {'password', 'smtp_password', 'secret', 'token', 'api_key', 'authorization', 'credentials'}

def redact_dict(data: dict) -> dict:
    """Recursively redact sensitive keys from dictionary for safe logging and serialization."""
    if not isinstance(data, dict):
        return data
    redacted = {}
    for k, v in data.items():
        if k.lower() in SENSITIVE_KEYS:
            redacted[k] = '[REDACTED]'
        elif isinstance(v, dict):
            redacted[k] = redact_dict(v)
        else:
            redacted[k] = v
    return redacted

redact_secrets = redact_dict

def is_allowed_origin(origin: str, allowed_hostnames: list) -> bool:
    """
    Validate whether the given request Origin / Referer matches the tenant's allowed domains.
    Always allows localhost, 127.0.0.1, and local file:// / null origins in development.
    """
    if not origin:
        return True
    
    # Always allow local file protocol or null origin from local browser HTML previews
    origin_clean = origin.strip().lower()
    if origin_clean in ('null', 'file://', 'file:', 'none') or origin_clean.startswith('file:'):
        return True

    parsed = urlparse(origin)
    hostname = (parsed.hostname or origin).lower().strip()
    
    # Always allow local development
    if hostname in ('localhost', '127.0.0.1', 'null'):
        return True
    
    if not allowed_hostnames:
        return True
        
    for allowed in allowed_hostnames:
        allowed_clean = allowed.lower().strip()
        # strip protocol if provided in domain list
        if '://' in allowed_clean:
            allowed_clean = urlparse(allowed_clean).hostname or allowed_clean
        
        if hostname == allowed_clean or hostname.endswith('.' + allowed_clean):
            return True
            
    return False
