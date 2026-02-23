import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def generate_key():
    """Generate a random 32-byte key and return as base64 string."""
    return base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()

def encrypt_data(data: bytes, key_b64: str) -> bytes:
    """Encrypt data using AES-GCM."""
    key = base64.b64decode(key_b64)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext

def decrypt_data(data: bytes, key_b64: str) -> bytes:
    """Decrypt data using AES-GCM."""
    key = base64.b64decode(key_b64)
    aesgcm = AESGCM(key)
    nonce = data[:12]
    ciphertext = data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)
