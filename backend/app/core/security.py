"""Gerenciamento de criptografia segura em repouso para credenciais e tokens OAuth."""

import base64
import os
from pathlib import Path
from cryptography.fernet import Fernet
from backend.app.core.config import settings


class TokenVault:
    """Gerencia criptografia e decriptografia de tokens locais usando Fernet."""

    def __init__(self, key: str | None = None):
        if key:
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        elif settings.ENCRYPTION_KEY:
            self.fernet = Fernet(settings.ENCRYPTION_KEY.encode())
        else:
            # Fallback seguro para desenvolvimento: arquivo de chave local
            key_file = Path("logs/.vault_key")
            if not key_file.exists():
                generated_key = Fernet.generate_key()
                key_file.parent.mkdir(exist_ok=True)
                key_file.write_bytes(generated_key)
            self.fernet = Fernet(key_file.read_bytes())

    def encrypt(self, plain_text: str) -> str:
        """Criptografa texto puro retornando string base64 segura."""
        if not plain_text:
            return ""
        return self.fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def decrypt(self, cipher_text: str) -> str:
        """Decriptografa dados protegidos."""
        if not cipher_text:
            return ""
        return self.fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")


vault = TokenVault()
