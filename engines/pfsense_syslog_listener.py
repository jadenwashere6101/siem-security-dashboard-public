from __future__ import annotations

import json
import logging
import os
import signal
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from adapters.pfsense_filterlog_adapter import MAX_PACKET_BYTES, parse_pfsense_filterlog_packet


logger = logging.getLogger(__name__)

DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 5514
DEFAULT_BACKEND_URL = "http://127.0.0.1:5051/ingest/pfsense"
DEFAULT_API_KEY_HEADER = "X-API-Key"
DEFAULT_GLOBAL_RATE_LIMIT = 200
DEFAULT_PER_SOURCE_RATE_LIMIT = 50
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 1.0
DEFAULT_BACKEND_TIMEOUT_SECONDS = 5.0
DEFAULT_RECV_TIMEOUT_SECONDS = 1.0
DEFAULT_ENVIRONMENT = "prod"


@dataclass(frozen=True)
class PfSenseListenerConfig:
    bind_host: str = DEFAULT_BIND_HOST
    bind_port: int = DEFAULT_BIND_PORT
    allowed_source_ips: frozenset[str] = frozenset()
    backend_url: str = DEFAULT_BACKEND_URL
    api_key: str = ""
    api_key_header: str = DEFAULT_API_KEY_HEADER
    max_packet_bytes: int = MAX_PACKET_BYTES
    global_rate_limit: int = DEFAULT_GLOBAL_RATE_LIMIT
    per_source_rate_limit: int = DEFAULT_PER_SOURCE_RATE_LIMIT
    rate_limit_window_seconds: float = DEFAULT_RATE_LIMIT_WINDOW_SECONDS
    backend_timeout_seconds: float = DEFAULT_BACKEND_TIMEOUT_SECONDS
    recv_timeout_seconds: float = DEFAULT_RECV_TIMEOUT_SECONDS
    environment: str = DEFAULT_ENVIRONMENT
    max_packets: int | None = None


@dataclass
class PfSenseListenerStats:
    accepted: int = 0
    rejected_source: int = 0
    oversized: int = 0
    rate_limited: int = 0
    parse_failed: int = 0
    forwarded: int = 0
    filtered: int = 0
    ingested: int = 0
    rejected: int = 0
    backend_failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "accepted": self.accepted,
            "rejected_source": self.rejected_source,
            "oversized": self.oversized,
            "rate_limited": self.rate_limited,
            "parse_failed": self.parse_failed,
            "forwarded": self.forwarded,
            "filtered": self.filtered,
            "ingested": self.ingested,
            "rejected": self.rejected,
            "backend_failed": self.backend_failed,
        }


class PfSenseListenerShutdown:
    def __init__(self) -> None:
        self.requested = False
        self.reason = "not_requested"

    def request(self, reason: str = "requested") -> None:
        self.requested = True
        self.reason = reason


class RateLimiter:
    def __init__(
        self,
        *,
        global_limit: int,
        per_source_limit: int,
        window_seconds: float,
        monotonic_fn: Callable[[], float] | None = None,
    ) -> None:
        self.global_limit = max(0, int(global_limit))
        self.per_source_limit = max(0, int(per_source_limit))
        self.window_seconds = max(0.0, float(window_seconds))
        self._monotonic = monotonic_fn or time.monotonic
        self._global_events: list[float] = []
        self._per_source_events: dict[str, list[float]] = {}

    def allow(self, source_ip: str) -> bool:
        if self.global_limit == 0 or self.per_source_limit == 0:
            return False

        now = self._monotonic()
        cutoff = now - self.window_seconds
        self._global_events = [stamp for stamp in self._global_events if stamp > cutoff]
        source_events = self._per_source_events.setdefault(source_ip, [])
        source_events[:] = [stamp for stamp in source_events if stamp > cutoff]

        if len(self._global_events) >= self.global_limit:
            return False
        if len(source_events) >= self.per_source_limit:
            return False

        self._global_events.append(now)
        source_events.append(now)
        return True


def install_shutdown_signal_handlers(shutdown: PfSenseListenerShutdown) -> None:
    def _handle_signal(signum, _frame) -> None:
        shutdown.request(f"signal_{signum}")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def _parse_allowed_source_ips(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(item.strip() for item in value.split(",") if item.strip())


def load_config_from_environ(environ: dict[str, str] | None = None) -> PfSenseListenerConfig:
    env = environ or os.environ
    api_key = (
        env.get("PFSENSE_INGEST_API_KEY")
        or env.get("SIEM_INGEST_API_KEY")
        or env.get("INGEST_API_KEY")
        or ""
    )
    max_packets_raw = env.get("PFSENSE_LISTENER_MAX_PACKETS", "").strip()
    max_packets = int(max_packets_raw) if max_packets_raw else None

    return PfSenseListenerConfig(
        bind_host=env.get("PFSENSE_LISTENER_BIND_HOST", DEFAULT_BIND_HOST).strip() or DEFAULT_BIND_HOST,
        bind_port=int(env.get("PFSENSE_LISTENER_PORT", str(DEFAULT_BIND_PORT))),
        allowed_source_ips=_parse_allowed_source_ips(env.get("PFSENSE_ALLOWED_SOURCE_IPS")),
        backend_url=env.get("PFSENSE_BACKEND_URL", DEFAULT_BACKEND_URL).strip() or DEFAULT_BACKEND_URL,
        api_key=api_key.strip(),
        api_key_header=env.get("PFSENSE_API_KEY_HEADER", DEFAULT_API_KEY_HEADER).strip() or DEFAULT_API_KEY_HEADER,
        max_packet_bytes=int(env.get("PFSENSE_MAX_PACKET_BYTES", str(MAX_PACKET_BYTES))),
        global_rate_limit=int(env.get("PFSENSE_GLOBAL_RATE_LIMIT", str(DEFAULT_GLOBAL_RATE_LIMIT))),
        per_source_rate_limit=int(env.get("PFSENSE_PER_SOURCE_RATE_LIMIT", str(DEFAULT_PER_SOURCE_RATE_LIMIT))),
        rate_limit_window_seconds=float(
            env.get("PFSENSE_RATE_LIMIT_WINDOW_SECONDS", str(DEFAULT_RATE_LIMIT_WINDOW_SECONDS))
        ),
        backend_timeout_seconds=float(
            env.get("PFSENSE_BACKEND_TIMEOUT_SECONDS", str(DEFAULT_BACKEND_TIMEOUT_SECONDS))
        ),
        recv_timeout_seconds=float(
            env.get("PFSENSE_RECV_TIMEOUT_SECONDS", str(DEFAULT_RECV_TIMEOUT_SECONDS))
        ),
        environment=env.get("PFSENSE_ENVIRONMENT", DEFAULT_ENVIRONMENT).strip() or DEFAULT_ENVIRONMENT,
        max_packets=max_packets,
    )


def validate_config(config: PfSenseListenerConfig) -> None:
    if not config.allowed_source_ips:
        raise ValueError("PFSENSE_ALLOWED_SOURCE_IPS must include at least one source IP")
    if not config.api_key:
        raise ValueError("PFSENSE_INGEST_API_KEY or SIEM_INGEST_API_KEY must be set")
    if config.bind_port < 1 or config.bind_port > 65535:
        raise ValueError("PFSENSE_LISTENER_PORT must be between 1 and 65535")
    if config.max_packet_bytes < 1:
        raise ValueError("PFSENSE_MAX_PACKET_BYTES must be positive")


def create_udp_socket(bind_host: str, bind_port: int, *, recv_timeout_seconds: float) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_host, bind_port))
    sock.settimeout(recv_timeout_seconds)
    return sock


def log_listener_event(
    outcome: str,
    *,
    source_ip: str | None = None,
    packet_bytes: int | None = None,
    parse_stage: str | None = None,
    parse_reason: str | None = None,
    backend_status: int | None = None,
    backend_error: str | None = None,
) -> None:
    logger.info(
        "pfsense_listener_event outcome=%s source_ip=%s packet_bytes=%s parse_stage=%s "
        "parse_reason=%s backend_status=%s backend_error=%s",
        outcome,
        source_ip,
        packet_bytes,
        parse_stage,
        parse_reason,
        backend_status,
        backend_error,
    )


def log_startup_summary(config: PfSenseListenerConfig) -> None:
    logger.info(
        "pfsense_listener_startup bind_host=%s bind_port=%s allowed_source_count=%s "
        "backend_url=%s max_packet_bytes=%s global_rate_limit=%s per_source_rate_limit=%s "
        "rate_limit_window_seconds=%s backend_timeout_seconds=%s environment=%s",
        config.bind_host,
        config.bind_port,
        len(config.allowed_source_ips),
        config.backend_url,
        config.max_packet_bytes,
        config.global_rate_limit,
        config.per_source_rate_limit,
        config.rate_limit_window_seconds,
        config.backend_timeout_seconds,
        config.environment,
    )


def forward_normalized_event(
    event: dict,
    *,
    backend_url: str,
    api_key: str,
    api_key_header: str,
    timeout_seconds: float,
    opener: Callable | None = None,
) -> tuple[bool, int | None, str | None]:
    payload = json.dumps(event).encode("utf-8")
    request = urllib.request.Request(
        backend_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            api_key_header: api_key,
        },
        method="POST",
    )
    urlopen = opener or urllib.request.urlopen
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None) or response.getcode()
            return True, int(status), None
    except urllib.error.HTTPError as error:
        return False, int(error.code), "http_error"
    except urllib.error.URLError:
        return False, None, "network_error"
    except TimeoutError:
        return False, None, "timeout"


def process_datagram(
    data: bytes,
    source_ip: str,
    *,
    config: PfSenseListenerConfig,
    stats: PfSenseListenerStats,
    rate_limiter: RateLimiter,
    forwarder: Callable[..., tuple[bool, int | None, str | None]] | None = None,
    parser: Callable[..., dict] | None = None,
) -> str:
    packet_bytes = len(data)

    if source_ip not in config.allowed_source_ips:
        stats.rejected_source += 1
        log_listener_event("rejected_source", source_ip=source_ip, packet_bytes=packet_bytes)
        return "rejected_source"

    if not rate_limiter.allow(source_ip):
        stats.rate_limited += 1
        log_listener_event("rate_limited", source_ip=source_ip, packet_bytes=packet_bytes)
        return "rate_limited"

    if packet_bytes > config.max_packet_bytes:
        stats.oversized += 1
        log_listener_event("oversized", source_ip=source_ip, packet_bytes=packet_bytes)
        return "oversized"

    stats.accepted += 1

    parse_packet = parser or parse_pfsense_filterlog_packet
    parse_result = parse_packet(
        data,
        environment=config.environment,
        sender_ip=source_ip,
    )
    if not parse_result.get("ok"):
        stats.parse_failed += 1
        error = parse_result.get("error") or {}
        log_listener_event(
            "parse_failed",
            source_ip=source_ip,
            packet_bytes=packet_bytes,
            parse_stage=error.get("stage"),
            parse_reason=error.get("reason"),
        )
        return "parse_failed"

    event = parse_result["event"]
    send_event = forwarder or forward_normalized_event
    ok, backend_status, backend_error = send_event(
        event,
        backend_url=config.backend_url,
        api_key=config.api_key,
        api_key_header=config.api_key_header,
        timeout_seconds=config.backend_timeout_seconds,
    )
    stats.forwarded += 1
    if ok and backend_status == 202:
        stats.filtered += 1
        log_listener_event("filtered", source_ip=source_ip, packet_bytes=packet_bytes, backend_status=backend_status)
        return "filtered"
    if ok and backend_status is not None and 200 <= backend_status < 300:
        stats.ingested += 1
        log_listener_event("ingested", source_ip=source_ip, packet_bytes=packet_bytes, backend_status=backend_status)
        return "ingested"
    if backend_status is not None and 400 <= backend_status < 500:
        stats.rejected += 1
        log_listener_event("rejected", source_ip=source_ip, packet_bytes=packet_bytes, backend_status=backend_status, backend_error=backend_error)
        return "rejected"
    if not ok:
        stats.backend_failed += 1
        log_listener_event(
            "backend_failed",
            source_ip=source_ip,
            packet_bytes=packet_bytes,
            backend_status=backend_status,
            backend_error=backend_error,
        )
        return "backend_failed"

    stats.backend_failed += 1
    return "backend_failed"


def run_pfsense_syslog_listener(
    *,
    config: PfSenseListenerConfig,
    shutdown: PfSenseListenerShutdown | None = None,
    sock: socket.socket | None = None,
    forwarder: Callable[..., tuple[bool, int | None, str | None]] | None = None,
    parser: Callable[..., dict] | None = None,
) -> dict[str, int]:
    validate_config(config)
    state = shutdown or PfSenseListenerShutdown()
    stats = PfSenseListenerStats()
    rate_limiter = RateLimiter(
        global_limit=config.global_rate_limit,
        per_source_limit=config.per_source_rate_limit,
        window_seconds=config.rate_limit_window_seconds,
    )
    owned_socket = sock is None
    listener_socket = sock or create_udp_socket(
        config.bind_host,
        config.bind_port,
        recv_timeout_seconds=config.recv_timeout_seconds,
    )

    log_startup_summary(config)
    packets_processed = 0

    try:
        while not state.requested:
            if config.max_packets is not None and packets_processed >= config.max_packets:
                break
            try:
                data, address = listener_socket.recvfrom(config.max_packet_bytes + 1)
            except socket.timeout:
                continue
            except OSError as error:
                if state.requested:
                    break
                logger.error("pfsense_listener_socket_error error=%s", error.__class__.__name__)
                continue

            packets_processed += 1
            process_datagram(
                data,
                address[0],
                config=config,
                stats=stats,
                rate_limiter=rate_limiter,
                forwarder=forwarder,
                parser=parser,
            )
    finally:
        if owned_socket:
            listener_socket.close()
        logger.info("pfsense_listener_shutdown reason=%s stats=%s", state.reason, stats.as_dict())

    return stats.as_dict()
