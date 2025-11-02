"""Symmetric encryption utilities for protecting stored tokens."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class TokenCipherService:
    """Encrypt and decrypt sensitive strings using a derived Fernet key."""

    def __init__(self, *, secret: str) -> None:
        if not secret:
            raise ValueError("Token encryption secret must be provided.")
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string and return the ciphertext."""
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string and return the plaintext."""
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("utf-8"))
        except InvalidToken as exc:  # pragma: no cover - defensive
            raise ValueError(
                "Failed to decrypt token; invalid ciphertext provided."
            ) from exc
        return plaintext.decode("utf-8")


__all__ = ["TokenCipherService"]
