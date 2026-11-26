"""Rate limiting substituível para operações públicas de autenticação."""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import hmac
import math
import secrets
from threading import Lock
import time
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """Limite aplicado a uma chave durante uma janela deslizante."""

    key: str
    maximum: int
    window_seconds: int

    def __post_init__(self) -> None:
        if not self.key or self.maximum < 1 or self.window_seconds < 1:
            raise ValueError("A regra de rate limiting deve ter chave e limites positivos.")


class RateLimitStore(Protocol):
    """Contrato para armazenamentos locais ou compartilhados de limites."""

    def check_and_record(self, rules: Sequence[RateLimitRule]) -> int | None:
        """Retorna segundos para retry, ou ``None`` quando as regras permitem."""


class InMemoryRateLimitStore:
    """Armazenamento de processo único; não serve para produção distribuída."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._windows: dict[str, int] = {}
        self._lock = Lock()
        self._operations = 0

    def check_and_record(self, rules: Sequence[RateLimitRule]) -> int | None:
        now = self._clock()
        with self._lock:
            self._operations += 1
            if self._operations % 128 == 0:
                self._remove_expired_buckets(now)

            waits: list[int] = []
            active: list[tuple[RateLimitRule, deque[float]]] = []
            for rule in rules:
                events = self._events.setdefault(rule.key, deque())
                self._windows[rule.key] = max(
                    rule.window_seconds, self._windows.get(rule.key, 0)
                )
                cutoff = now - rule.window_seconds
                while events and events[0] <= cutoff:
                    events.popleft()
                active.append((rule, events))
                if len(events) >= rule.maximum:
                    waits.append(max(1, math.ceil(events[0] + rule.window_seconds - now)))

            if waits:
                return max(waits)

            for _, events in active:
                events.append(now)
            return None

    def _remove_expired_buckets(self, now: float) -> None:
        for key, events in tuple(self._events.items()):
            window = self._windows.get(key, 0)
            while events and events[0] <= now - window:
                events.popleft()
            if not events:
                self._events.pop(key, None)
                self._windows.pop(key, None)


@dataclass(frozen=True, slots=True)
class AuthRateLimitPolicy:
    """Limites independentes por IP e conta para cadastro e login."""

    login_ip_maximum: int = 30
    login_account_maximum: int = 10
    login_window_seconds: int = 15 * 60
    register_ip_maximum: int = 20
    register_account_maximum: int = 5
    register_window_seconds: int = 60 * 60


class AuthenticationRateLimiter:
    """Aplica limites por IP e e-mail sem armazenar e-mails em claro como chave."""

    def __init__(
        self,
        store: RateLimitStore,
        policy: AuthRateLimitPolicy | None = None,
        fingerprint_key: bytes | None = None,
    ) -> None:
        self.store = store
        self.policy = policy or AuthRateLimitPolicy()
        # O segredo JWT compartilhado torna as chaves de conta estáveis entre
        # processos; em desenvolvimento sem segredo, a chave é só do processo.
        self._fingerprint_key = fingerprint_key or secrets.token_bytes(32)

    def check(self, action: str, client_ip: str, email: str) -> int | None:
        if action == "login":
            ip_maximum = self.policy.login_ip_maximum
            account_maximum = self.policy.login_account_maximum
            window = self.policy.login_window_seconds
        elif action == "register":
            ip_maximum = self.policy.register_ip_maximum
            account_maximum = self.policy.register_account_maximum
            window = self.policy.register_window_seconds
        else:
            raise ValueError("Operação de autenticação sem limite configurado.")

        account_digest = hmac.new(
            self._fingerprint_key,
            email.strip().casefold().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        prefix = f"auth:{action}"
        return self.store.check_and_record(
            (
                RateLimitRule(f"{prefix}:ip:{client_ip}", ip_maximum, window),
                RateLimitRule(f"{prefix}:account:{account_digest}", account_maximum, window),
            )
        )
