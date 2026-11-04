"""Authentication (A-06, NFR-16, NFR-17): seeded accounts, two roles, signed tokens.

- A password is stored only as a salted PBKDF2-SHA256 hash: ``pbkdf2_sha256$iterations$salt$hash``.
- A token is ``v1.<payload>.<signature>``: the payload is JSON (user, role, module, expiry) and the
  signature is HMAC-SHA256 with ``SECRET_KEY``. There is no default key: without one core refuses
  to build the service, so no secret is ever written in the repository.
- The role in a token is not trusted. The user is read again on every request, so a deactivated
  user or a changed role takes effect at once.
- A service token (``iot_sim``) is issued in code for the simulator and is not tied to an account.
- Expiry uses the injected clock (D-005), so it is testable.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core.actor import Actor
from core.clock import Clock
from core.domain.entities import UserAccount
from core.domain.enums import Role
from core.errors import ErrorCode
from core.result import Err, Ok, Result
from core.services.runtime import Runtime

_SCHEME = "pbkdf2_sha256"
_TOKEN_VERSION = "v1"
DEFAULT_ITERATIONS = 120_000
DEFAULT_TOKEN_MINUTES = 60
INTERFACE_MODULE = "ui"


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    """A salted hash to store. The same password gives a different string every time."""
    if iterations < 1:
        raise ValueError("iterations must be at least 1")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_SCHEME}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """True when ``password`` matches ``stored``. A damaged ``stored`` never raises, it is False."""
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != _SCHEME:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True, slots=True)
class AuthConfig:
    secret_key: str
    token_minutes: int = DEFAULT_TOKEN_MINUTES
    hash_iterations: int = DEFAULT_ITERATIONS

    def __post_init__(self) -> None:
        if len(self.secret_key) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters")
        if self.token_minutes < 1 or self.hash_iterations < 1:
            raise ValueError("token_minutes and hash_iterations must be at least 1")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AuthConfig":
        env = os.environ if environ is None else environ
        key = env.get("SECRET_KEY", "").strip()
        if not key:
            raise ValueError("SECRET_KEY is not set; generate one locally and put it in .env")
        return cls(
            secret_key=key,
            token_minutes=int(env.get("ACCESS_TOKEN_TTL_MINUTES") or DEFAULT_TOKEN_MINUTES),
            hash_iterations=int(env.get("PASSWORD_HASH_ITERATIONS") or DEFAULT_ITERATIONS),
        )


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    role: Role
    module: str

    def actor(self) -> Actor:
        return Actor(self.user_id, self.role, self.module)


@dataclass(frozen=True, slots=True)
class LoginResult:
    access_token: str
    expires_at: datetime
    user_id: str
    role: Role


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class AuthService:
    def __init__(self, runtime: Runtime, config: AuthConfig, clock: Clock) -> None:
        self._rt = runtime
        self._config = config
        self._clock = clock
        # Checked when the account does not exist, so a wrong code and a wrong password take the
        # same time and a caller cannot tell which accounts exist.
        self._dummy_hash = hash_password("not-a-real-password", config.hash_iterations)

    # ------------------------------------------------------------------ tokens

    def _sign(self, message: str) -> str:
        key = self._config.secret_key.encode("utf-8")
        return _b64(hmac.new(key, message.encode("ascii"), hashlib.sha256).digest())

    def _issue(
        self, user_id: str, role: Role, module: str, service: bool, minutes: int
    ) -> tuple[str, datetime]:
        expires = self._clock.now() + timedelta(minutes=minutes)
        payload = {
            "sub": user_id,
            "role": role.value,
            "module": module,
            "svc": service,
            "exp": int(expires.timestamp()),
        }
        body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        message = f"{_TOKEN_VERSION}.{body}"
        return f"{message}.{self._sign(message)}", datetime.fromtimestamp(
            int(expires.timestamp()), UTC
        )

    def issue_service_token(self, module: str, user_id: str, minutes: int | None = None) -> str:
        """A token for a system module such as the simulator (not stored, not an account)."""
        token, _ = self._issue(
            user_id, Role.OPERATOR, module, True, minutes or self._config.token_minutes
        )
        return token

    # ------------------------------------------------------------------ login and checking

    def login(self, code: str, password: str) -> Result[LoginResult]:
        denied = Err(ErrorCode.UNAUTHENTICATED, "wrong account or password")
        with self._rt.lock:
            matches = self._rt.repo.query(UserAccount, lambda u: u.code == code)
        user = matches[0] if matches else None
        verified = verify_password(
            password, user.password_hash if user and user.password_hash else self._dummy_hash
        )
        if user is None or not user.password_hash or not user.is_active or not verified:
            return denied
        token, expires = self._issue(
            user.user_id, user.role, INTERFACE_MODULE, False, self._config.token_minutes
        )
        return Ok(LoginResult(token, expires, user.user_id, user.role))

    def authenticate(self, token: str) -> Result[Principal]:
        """The caller behind a token, or UNAUTHENTICATED (bad, tampered, expired, or stale)."""
        denied = Err(ErrorCode.UNAUTHENTICATED, "missing, invalid or expired token")
        try:
            version, body, signature = token.split(".")
            if version != _TOKEN_VERSION:
                return denied
            if not hmac.compare_digest(self._sign(f"{version}.{body}"), signature):
                return denied
            payload = json.loads(_unb64(body))
            if int(payload["exp"]) <= int(self._clock.now().timestamp()):
                return denied
            user_id = str(payload["sub"])
            module = str(payload["module"])
            if payload["svc"] is True:
                return Ok(Principal(user_id, Role.OPERATOR, module))
        except (ValueError, KeyError, TypeError, AttributeError):
            return denied
        with self._rt.lock:
            user = self._rt.repo.get(UserAccount, user_id)
        if user is None or not user.is_active:
            return denied
        return Ok(Principal(user.user_id, user.role, INTERFACE_MODULE))
