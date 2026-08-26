"""Gerenciamento de criptografia segura em repouso para credenciais e tokens OAuth."""

from pathlib import Path
from cryptography.fernet import Fernet
from backend.app.core.config import settings, APP_DATA_DIR
from backend.app.core.logging import logger


class TokenVault:
    """Gerencia criptografia e decriptografia de tokens locais usando Fernet."""

    def __init__(self, key: str | None = None):
        if key:
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        elif settings.ENCRYPTION_KEY:
            self.fernet = Fernet(settings.ENCRYPTION_KEY.encode())
        else:
            # Armazena em diretório protegido do usuário, desacoplado de logs
            vault_dir = APP_DATA_DIR / "vault"
            vault_dir.mkdir(parents=True, exist_ok=True)
            key_file = vault_dir / ".vault_key"
            
            if not key_file.exists():
                generated_key = Fernet.generate_key()
                key_file.write_bytes(generated_key)
                logger.warning(
                    "[SEGURANÇA] Nova chave mestra gerada em disco. "
                    "Se este arquivo for apagado, tokens previamente criptografados não poderão ser recuperados."
                )
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
        try:
            return self.fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.error(f"[SEGURANÇA] Falha ao decriptografar token: chave inconsistente ou corrompida. {e}")
            raise ValueError("Não foi possível decriptografar a credencial. A chave do vault pode ter sido alterada.")


vault = TokenVault()