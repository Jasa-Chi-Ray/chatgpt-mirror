import base64
import json
import os
from hashlib import sha256

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import models


PREFIX = "enc:v1:"


def _key():
    secret = os.environ.get("CREDENTIAL_ENCRYPTION_KEY") or settings.SECRET_KEY
    if not secret:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY 未配置")
    return sha256(secret.encode("utf-8")).digest()


def encrypt_value(value):
    if value is None or value == "" or str(value).startswith(PREFIX):
        return value
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, str(value).encode("utf-8"), None)
    return PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_value(value):
    if value is None or value == "" or not str(value).startswith(PREFIX):
        return value
    raw = base64.urlsafe_b64decode(str(value)[len(PREFIX):])
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")


class EncryptedTextField(models.TextField):
    def from_db_value(self, value, expression, connection):
        return decrypt_value(value)

    def to_python(self, value):
        return decrypt_value(value)

    def get_prep_value(self, value):
        return encrypt_value(value)


class EncryptedJSONField(EncryptedTextField):
    def from_db_value(self, value, expression, connection):
        plaintext = decrypt_value(value)
        if plaintext in (None, ""):
            return []
        if isinstance(plaintext, (list, dict)):
            return plaintext
        return json.loads(plaintext)

    def to_python(self, value):
        if isinstance(value, (list, dict)):
            return value
        plaintext = decrypt_value(value)
        return json.loads(plaintext) if plaintext else []

    def get_prep_value(self, value):
        if value is None:
            value = []
        return encrypt_value(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
