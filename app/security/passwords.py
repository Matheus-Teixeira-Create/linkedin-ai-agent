"""Hash e verificação de senhas com Argon2id."""

from functools import lru_cache
import secrets

from pwdlib import PasswordHash


class PasswordManager:
    """Encapsula a política de hash e a verificação fictícia anti-enumeração."""

    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, encoded_hash: str | None) -> bool:
        target_hash = encoded_hash or self._dummy_hash
        try:
            valid = self._hasher.verify(password, target_hash)
        except Exception:
            return False
        return bool(valid and encoded_hash)

    def needs_rehash(self, encoded_hash: str) -> bool:
        return self._hasher.current_hasher.check_needs_rehash(encoded_hash)


@lru_cache(maxsize=1)
def get_password_manager() -> PasswordManager:
    """Compartilha hasher e hash fictício, evitando custo por requisição."""
    return PasswordManager()
