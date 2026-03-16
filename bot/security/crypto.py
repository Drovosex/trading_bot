from cryptography.fernet import Fernet


class KeyVault:
    """Encrypts/decrypts MEXC API keys at rest using Fernet (AES-128-CBC)."""

    def __init__(self, encryption_key: str) -> None:
        self._fernet = Fernet(encryption_key.encode())

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        return self._fernet.decrypt(ciphertext).decode()
