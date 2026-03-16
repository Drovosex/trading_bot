import pytest
from cryptography.fernet import Fernet

from bot.security.crypto import KeyVault


@pytest.fixture
def vault():
    key = Fernet.generate_key().decode()
    return KeyVault(key)


def test_encrypt_decrypt_roundtrip(vault):
    plaintext = "mx0vgltest12345abcde"
    encrypted = vault.encrypt(plaintext)
    assert encrypted != plaintext.encode()
    decrypted = vault.decrypt(encrypted)
    assert decrypted == plaintext


def test_different_ciphertexts_for_same_input(vault):
    """Fernet produces different ciphertexts each time (due to IV)."""
    enc1 = vault.encrypt("test")
    enc2 = vault.encrypt("test")
    assert enc1 != enc2
