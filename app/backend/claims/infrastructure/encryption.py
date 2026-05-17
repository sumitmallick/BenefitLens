"""
PHI field encryption.

All Protected Health Information (PHI) fields — member names, dates of birth,
diagnosis codes, member IDs — are encrypted at rest using Fernet (AES-128-CBC
with HMAC-SHA256 authentication).

Design decisions:
  - Encryption happens in the infrastructure layer, NOT the domain.
    Domain entities always hold plaintext; ORM models hold ciphertext.
  - Key rotation: we use a MultiFernet to support rolling key rotation
    without re-encrypting all rows at once.
  - No PII/PHI is written to application logs anywhere in this codebase.
    The logging middleware strips known-sensitive fields before output.

HIPAA consideration: in a production system this key would live in
AWS KMS / GCP Cloud KMS with envelope encryption, not in an env var.
That's a deliberate scope limitation documented in decisions.md.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken, MultiFernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning(
        "cryptography package not installed — PHI encryption disabled. "
        "Install with: pip install cryptography"
    )


class PHIEncryptor:
    """
    Wraps Fernet symmetric encryption for PHI fields.

    In development (no key configured), operates in passthrough mode
    so developers can work without setting up keys.
    Log a warning so it's visible.
    """

    def __init__(self, key: str = "") -> None:
        self._fernet: Optional[MultiFernet] = None

        if not CRYPTO_AVAILABLE:
            logger.warning("PHI encryption unavailable — cryptography not installed.")
            return

        if not key:
            logger.warning(
                "PHI_ENCRYPTION_KEY not set. PHI fields stored in plaintext. "
                "This is NOT acceptable in production."
            )
            return

        try:
            # Key can be a comma-separated list for rotation
            keys = [k.strip() for k in key.split(",") if k.strip()]
            fernets = [Fernet(k.encode() if isinstance(k, str) else k) for k in keys]
            self._fernet = MultiFernet(fernets)
        except Exception as exc:
            logger.error("Failed to initialize PHI encryptor: %s", exc)
            raise

    @property
    def is_active(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext PHI value. Returns base64 ciphertext."""
        if self._fernet is None:
            return plaintext
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext PHI value back to plaintext."""
        if self._fernet is None:
            return ciphertext
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except (InvalidToken, Exception) as exc:
            logger.error("PHI decryption failed — token may be corrupt or wrong key.")
            raise ValueError("PHI decryption failed") from exc

    def encrypt_optional(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return self.encrypt(value)

    def decrypt_optional(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return self.decrypt(value)


# Module-level singleton
_encryptor: Optional[PHIEncryptor] = None


def init_encryptor(key: str = "") -> None:
    global _encryptor
    _encryptor = PHIEncryptor(key)


def get_encryptor() -> PHIEncryptor:
    global _encryptor
    if _encryptor is None:
        _encryptor = PHIEncryptor()
    return _encryptor
