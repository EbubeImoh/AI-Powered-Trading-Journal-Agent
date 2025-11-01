import pytest

from app.services.token_cipher import TokenCipherService


def test_token_cipher_roundtrip() -> None:
    cipher = TokenCipherService(secret="super-secret-key")
    plaintext = "sensitive-token"

    encrypted = cipher.encrypt(plaintext)
    assert encrypted != plaintext

    decrypted = cipher.decrypt(encrypted)
    assert decrypted == plaintext


def test_token_cipher_rejects_bad_ciphertext() -> None:
    cipher = TokenCipherService(secret="another-secret")

    with pytest.raises(ValueError):
        cipher.decrypt("not-valid")
