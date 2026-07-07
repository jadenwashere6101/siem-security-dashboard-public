from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engines.pfsense_syslog_listener import (
    DEFAULT_BIND_HOST,
    DEFAULT_BIND_PORT,
    DEFAULT_ENVIRONMENT,
    DEFAULT_GLOBAL_RATE_LIMIT,
    DEFAULT_PER_SOURCE_RATE_LIMIT,
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    MAX_PACKET_BYTES,
    PfSenseListenerConfig,
    PfSenseListenerShutdown,
    _parse_allowed_source_ips,
    install_shutdown_signal_handlers,
    load_config_from_environ,
    run_pfsense_syslog_listener,
)


def _parse_args(argv=None):
    env_config = load_config_from_environ()
    parser = argparse.ArgumentParser(
        description="Run the pfSense UDP syslog listener daemon."
    )
    parser.add_argument("--bind-host", default=env_config.bind_host)
    parser.add_argument("--port", type=int, default=env_config.bind_port)
    parser.add_argument(
        "--allowed-source-ips",
        default=",".join(sorted(env_config.allowed_source_ips)),
        help="Comma-separated pfSense source IP allow-list.",
    )
    parser.add_argument("--backend-url", default=env_config.backend_url)
    parser.add_argument("--api-key", default=env_config.api_key)
    parser.add_argument("--api-key-header", default=env_config.api_key_header)
    parser.add_argument("--max-packet-bytes", type=int, default=env_config.max_packet_bytes)
    parser.add_argument("--global-rate-limit", type=int, default=env_config.global_rate_limit)
    parser.add_argument("--per-source-rate-limit", type=int, default=env_config.per_source_rate_limit)
    parser.add_argument(
        "--rate-limit-window-seconds",
        type=float,
        default=env_config.rate_limit_window_seconds,
    )
    parser.add_argument(
        "--backend-timeout-seconds",
        type=float,
        default=env_config.backend_timeout_seconds,
    )
    parser.add_argument(
        "--recv-timeout-seconds",
        type=float,
        default=env_config.recv_timeout_seconds,
    )
    parser.add_argument("--environment", default=env_config.environment)
    parser.add_argument(
        "--max-packets",
        type=int,
        default=env_config.max_packets,
        help="Test mode: exit after processing this many UDP packets.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def build_config_from_args(args) -> PfSenseListenerConfig:
    return PfSenseListenerConfig(
        bind_host=args.bind_host or DEFAULT_BIND_HOST,
        bind_port=args.port or DEFAULT_BIND_PORT,
        allowed_source_ips=_parse_allowed_source_ips(args.allowed_source_ips),
        backend_url=args.backend_url,
        api_key=args.api_key,
        api_key_header=args.api_key_header,
        max_packet_bytes=args.max_packet_bytes or MAX_PACKET_BYTES,
        global_rate_limit=args.global_rate_limit or DEFAULT_GLOBAL_RATE_LIMIT,
        per_source_rate_limit=args.per_source_rate_limit or DEFAULT_PER_SOURCE_RATE_LIMIT,
        rate_limit_window_seconds=args.rate_limit_window_seconds or DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        backend_timeout_seconds=args.backend_timeout_seconds,
        recv_timeout_seconds=args.recv_timeout_seconds,
        environment=args.environment or DEFAULT_ENVIRONMENT,
        max_packets=args.max_packets,
    )


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = build_config_from_args(args)
    shutdown = PfSenseListenerShutdown()
    install_shutdown_signal_handlers(shutdown)
    stats = run_pfsense_syslog_listener(config=config, shutdown=shutdown)
    return 0 if stats["backend_failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
