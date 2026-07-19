from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import parse_qsl, unquote, urlsplit


ALLOWED_PRODUCTION_RATE_LIMIT_SCHEMES = {"redis", "rediss"}
LOOPBACK_RATE_LIMIT_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOCAL_MEMORY_STORAGE_URI = "memory://"


class RateLimitStorageConfigError(RuntimeError):
    """Raised when limiter storage configuration is unsafe for the runtime."""


@dataclass(frozen=True)
class RateLimitStorageConfig:
    storage_uri: str
    production: bool
    backend: str
    host: str
    port: int | None
    database: str | None

    @property
    def sanitized_summary(self) -> str:
        parts = [f"backend={self.backend}"]
        if self.host:
            parts.append(f"host={self.host}")
        if self.port is not None:
            parts.append(f"port={self.port}")
        if self.database:
            parts.append(f"db={self.database}")
        return " ".join(parts)


def env_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_rate_limit_storage_config(
    env: Mapping[str, str | None],
    *,
    production: bool | None = None,
) -> RateLimitStorageConfig:
    if production is None:
        production = not env_bool(env.get("SIEM_DEBUG"))

    raw_uri = (env.get("SIEM_RATE_LIMIT_STORAGE_URI") or "").strip()

    if not raw_uri:
        if production:
            raise RateLimitStorageConfigError("Missing SIEM_RATE_LIMIT_STORAGE_URI for production.")
        raw_uri = LOCAL_MEMORY_STORAGE_URI

    parsed = urlsplit(raw_uri)
    scheme = parsed.scheme.lower()

    if scheme == "memory":
        if production:
            raise RateLimitStorageConfigError("Production rate limiting cannot use memory storage.")
        return RateLimitStorageConfig(
            storage_uri=LOCAL_MEMORY_STORAGE_URI,
            production=False,
            backend="memory",
            host="",
            port=None,
            database=None,
        )

    if scheme not in ALLOWED_PRODUCTION_RATE_LIMIT_SCHEMES:
        raise RateLimitStorageConfigError(
            "SIEM_RATE_LIMIT_STORAGE_URI must use redis:// or rediss:// storage."
        )

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise RateLimitStorageConfigError("SIEM_RATE_LIMIT_STORAGE_URI must include a Redis host.")
    if production and host not in LOOPBACK_RATE_LIMIT_HOSTS:
        raise RateLimitStorageConfigError(
            "Production rate-limit Redis storage must use a loopback host."
        )

    try:
        port = parsed.port
    except ValueError as exc:
        raise RateLimitStorageConfigError("SIEM_RATE_LIMIT_STORAGE_URI has an invalid Redis port.") from exc

    database = _redis_database(parsed.path)

    return RateLimitStorageConfig(
        storage_uri=raw_uri,
        production=production,
        backend=scheme,
        host=host,
        port=port,
        database=database,
    )


def apply_rate_limit_config(app, env: Mapping[str, str | None], *, production: bool | None = None):
    config = resolve_rate_limit_storage_config(env, production=production)
    app.config["RATELIMIT_STORAGE_URI"] = config.storage_uri
    app.config["RATELIMIT_SWALLOW_ERRORS"] = False
    app.config["RATELIMIT_IN_MEMORY_FALLBACK_ENABLED"] = False
    app.config["RATELIMIT_IN_MEMORY_FALLBACK"] = []
    if config.backend in ALLOWED_PRODUCTION_RATE_LIMIT_SCHEMES:
        app.config["RATELIMIT_STORAGE_OPTIONS"] = {
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "retry_on_timeout": False,
            "wrap_exceptions": True,
        }
    app.config["SIEM_RATE_LIMIT_STORAGE_BACKEND"] = config.backend
    app.config["SIEM_RATE_LIMIT_STORAGE_SUMMARY"] = config.sanitized_summary
    return config


def validate_rate_limit_storage_runtime(
    env: Mapping[str, str | None],
    *,
    production: bool = True,
    ping: bool = True,
) -> RateLimitStorageConfig:
    config = resolve_rate_limit_storage_config(env, production=production)
    if config.backend == "memory":
        return config

    if ping:
        try:
            import redis
        except ImportError as exc:
            raise RateLimitStorageConfigError("Redis Python client is not installed.") from exc

        try:
            client = redis.Redis.from_url(
                config.storage_uri,
                socket_connect_timeout=1,
                socket_timeout=1,
                retry_on_timeout=False,
            )
            client.ping()
        except Exception as exc:
            raise RateLimitStorageConfigError(
                f"Unable to connect to rate-limit Redis storage ({type(exc).__name__})."
            ) from exc

    return config


def sanitize_rate_limit_storage_uri(uri: str) -> str:
    parsed = urlsplit(uri)
    if not parsed.scheme:
        return "<invalid>"
    host = parsed.hostname or "<missing-host>"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    path = parsed.path or ""
    return f"{parsed.scheme}://{netloc}{path}"


def _redis_database(path: str) -> str | None:
    cleaned = unquote(path or "").strip("/")
    if not cleaned:
        return None
    return cleaned.split("/", 1)[0]
