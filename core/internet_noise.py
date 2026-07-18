from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from flask import current_app


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, dict[str, Any]] = {}
_IN_FLIGHT: dict[str, Future] = {}
_METRICS: dict[str, int] = {
    "lookups_succeeded": 0,
    "commodity_results": 0,
    "malicious_results": 0,
    "neutral_results": 0,
    "cache_hits": 0,
    "lookup_failures": 0,
    "alerts_deprioritized": 0,
    "local_override": 0,
    "incidents_prevented": 0,
    "shadow_alerts_would_deprioritize": 0,
    "shadow_incidents_would_prevent": 0,
    "shadow_local_override": 0,
}
_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(int(os.getenv("SIEM_INTERNET_NOISE_WORKERS", "2")), 1),
    thread_name_prefix="internet-noise",
)
_VALID_ASSESSMENTS = frozenset({"commodity", "malicious", "neutral"})
_VALID_POLICY_MODES = frozenset({"shadow", "policy"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cache_ttl_seconds() -> int:
    return max(int(os.getenv("SIEM_INTERNET_NOISE_CACHE_TTL_SECONDS", "86400")), 60)


def _request_timeout_seconds() -> float:
    return max(float(os.getenv("SIEM_INTERNET_NOISE_TIMEOUT_SECONDS", "2.0")), 0.25)


def _max_retries() -> int:
    return max(int(os.getenv("SIEM_INTERNET_NOISE_MAX_RETRIES", "2")), 0)


def _retry_backoff_seconds() -> float:
    return max(float(os.getenv("SIEM_INTERNET_NOISE_RETRY_BACKOFF_SECONDS", "0.2")), 0.0)


def _provider_name() -> str:
    return (os.getenv("SIEM_INTERNET_NOISE_PROVIDER") or "GreyNoise").strip() or "GreyNoise"


def _provider_key() -> str | None:
    return (os.getenv("SIEM_GREYNOISE_API_KEY") or os.getenv("GREYNOISE_API_KEY") or "").strip() or None


def get_internet_noise_policy_mode() -> str:
    mode = str(os.getenv("INTERNET_NOISE_POLICY_MODE") or "shadow").strip().lower()
    return mode if mode in _VALID_POLICY_MODES else "shadow"


def _inc(metric_name: str, amount: int = 1) -> None:
    with _CACHE_LOCK:
        _METRICS[metric_name] = int(_METRICS.get(metric_name, 0)) + amount


def _log_warning(message: str, *args: Any) -> None:
    try:
        current_app.logger.warning(message, *args)
    except RuntimeError:
        return


def build_internet_noise_assessment(
    *,
    provider: str | None = None,
    assessment: str = "neutral",
    explanation: str | None = None,
    confidence: str | None = None,
    last_checked: str | None = None,
    cached: bool = False,
    lookup_status: str = "unknown",
    provider_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_assessment = str(assessment or "neutral").strip().lower()
    if normalized_assessment not in _VALID_ASSESSMENTS:
        normalized_assessment = "neutral"
    return {
        "provider": provider or _provider_name(),
        "assessment": normalized_assessment,
        "explanation": explanation
        or (
            "Known commodity internet scanner."
            if normalized_assessment == "commodity"
            else "Known malicious internet activity."
            if normalized_assessment == "malicious"
            else "Internet-noise assessment is unavailable."
        ),
        "confidence": str(confidence).strip().lower() if confidence not in (None, "") else None,
        "last_checked": last_checked,
        "cached": bool(cached),
        "lookup_status": str(lookup_status or "unknown").strip().lower() or "unknown",
        "provider_metadata": provider_metadata if isinstance(provider_metadata, dict) else {},
    }


def build_internet_noise_decision(
    assessment: dict[str, Any] | None,
    *,
    override_reasons: list[dict[str, str]] | None = None,
    policy_mode: str | None = None,
) -> dict[str, Any]:
    normalized = assessment if isinstance(assessment, dict) else build_internet_noise_assessment()
    override_reasons = list(override_reasons or [])
    normalized_assessment = str(normalized.get("assessment") or "neutral").lower()
    normalized_policy_mode = str(policy_mode or get_internet_noise_policy_mode()).strip().lower()
    if normalized_policy_mode not in _VALID_POLICY_MODES:
        normalized_policy_mode = "shadow"
    decision = {
        **normalized,
        "policy_mode": normalized_policy_mode,
        "effect": "neutral",
        "result": "No internet-noise adjustment applied.",
        "deprioritized": False,
        "override_reasons": override_reasons,
        "would_reduce_urgency": False,
        "applied_to_investigation": False,
        "would_affect_incident": False,
        "applied_to_incident": False,
        "local_evidence_override": False,
    }
    if normalized_assessment == "commodity":
        if override_reasons:
            decision["effect"] = "local_evidence_override"
            decision["result"] = "Local evidence overrides internet-noise assessment."
            decision["local_evidence_override"] = True
        else:
            decision["would_reduce_urgency"] = True
            decision["would_affect_incident"] = True
            if normalized_policy_mode == "policy":
                decision["effect"] = "reduced_urgency"
                decision["result"] = "Reduced investigation urgency."
                decision["deprioritized"] = True
                decision["applied_to_investigation"] = True
                decision["applied_to_incident"] = True
            else:
                decision["effect"] = "shadow_observation"
                decision["result"] = "Shadow mode recorded a potential urgency reduction."
    elif normalized_assessment == "malicious":
        decision["result"] = "Internet-noise assessment did not lower urgency."
    return decision


def get_internet_noise_metrics() -> dict[str, int]:
    with _CACHE_LOCK:
        return dict(_METRICS)


def record_internet_noise_outcome(metric_name: str) -> None:
    if metric_name in _METRICS:
        _inc(metric_name)


def reset_internet_noise_state_for_tests() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
        _IN_FLIGHT.clear()
        for key in list(_METRICS):
            _METRICS[key] = 0


def get_internet_noise_assessment(
    ip_address: str | None,
    *,
    allow_enqueue: bool = True,
) -> dict[str, Any]:
    ip_address = str(ip_address or "").strip()
    if not ip_address:
        return build_internet_noise_assessment(lookup_status="unknown")

    if not _provider_key():
        assessment = build_internet_noise_assessment(
            lookup_status="provider_unavailable",
            explanation="Internet-noise provider is unavailable; the result is neutral.",
            cached=False,
        )
        with _CACHE_LOCK:
            _CACHE[ip_address] = {
                "assessment": assessment,
                "expires_at": _utcnow() + timedelta(seconds=_cache_ttl_seconds()),
            }
        return assessment

    now = _utcnow()
    expired_assessment: dict[str, Any] | None = None
    with _CACHE_LOCK:
        cached = _CACHE.get(ip_address)
        if cached and cached["expires_at"] > now:
            _METRICS["cache_hits"] += 1
            return {
                **cached["assessment"],
                "cached": True,
            }
        if cached and cached["expires_at"] <= now:
            expired_assessment = cached["assessment"]
            _CACHE.pop(ip_address, None)
        future = _IN_FLIGHT.get(ip_address)

    if expired_assessment is not None:
        if allow_enqueue and future is None:
            _enqueue_refresh(ip_address)
        return build_internet_noise_assessment(
            provider=expired_assessment.get("provider"),
            assessment="neutral",
            explanation="Cached internet-noise assessment expired; the result remains neutral while a refresh is pending.",
            confidence=expired_assessment.get("confidence"),
            last_checked=expired_assessment.get("last_checked"),
            cached=False,
            lookup_status="stale",
            provider_metadata={
                "stale_assessment": expired_assessment.get("assessment"),
            },
        )

    if allow_enqueue and future is None:
        _enqueue_refresh(ip_address)
        return build_internet_noise_assessment(
            lookup_status="pending",
            explanation="Internet-noise assessment is being refreshed.",
        )
    return build_internet_noise_assessment()


def refresh_internet_noise_assessment(ip_address: str) -> dict[str, Any]:
    ip_address = str(ip_address or "").strip()
    if not ip_address:
        return build_internet_noise_assessment()

    assessment = _lookup_provider_assessment(ip_address)
    with _CACHE_LOCK:
        _CACHE[ip_address] = {
            "assessment": assessment,
            "expires_at": _utcnow() + timedelta(seconds=_cache_ttl_seconds()),
        }
    return assessment


def _enqueue_refresh(ip_address: str) -> None:
    with _CACHE_LOCK:
        existing = _IN_FLIGHT.get(ip_address)
        if existing is not None:
            return
        future = _EXECUTOR.submit(_refresh_task, ip_address)
        _IN_FLIGHT[ip_address] = future


def _refresh_task(ip_address: str) -> dict[str, Any]:
    try:
        return refresh_internet_noise_assessment(ip_address)
    finally:
        with _CACHE_LOCK:
            _IN_FLIGHT.pop(ip_address, None)


def _lookup_provider_assessment(ip_address: str) -> dict[str, Any]:
    api_key = _provider_key()
    provider = _provider_name()
    if not api_key:
        _inc("neutral_results")
        return build_internet_noise_assessment(
            provider=provider,
            lookup_status="provider_unavailable",
            explanation="Internet-noise provider is unavailable; the result is neutral.",
        )

    url = f"https://api.greynoise.io/v3/community/{ip_address}"
    headers = {"Accept": "application/json", "key": api_key}
    max_retries = _max_retries()
    backoff = _retry_backoff_seconds()

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=_request_timeout_seconds())
            if response.status_code == 404:
                _inc("lookups_succeeded")
                _inc("neutral_results")
                return build_internet_noise_assessment(
                    provider=provider,
                    lookup_status="succeeded",
                    last_checked=_utcnow().isoformat(),
                    explanation="Internet-noise provider returned no commodity or malicious classification.",
                    provider_metadata={"http_status": 404},
                )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < max_retries:
                    time.sleep(backoff * (2 ** attempt))
                    continue
                raise requests.HTTPError(f"provider_status_{response.status_code}")
            response.raise_for_status()
            payload = response.json()
            assessment = _normalize_provider_payload(payload)
            _inc("lookups_succeeded")
            if assessment["assessment"] == "commodity":
                _inc("commodity_results")
            elif assessment["assessment"] == "malicious":
                _inc("malicious_results")
            else:
                _inc("neutral_results")
            return {
                **assessment,
                "provider": provider,
                "last_checked": _utcnow().isoformat(),
                "lookup_status": "succeeded",
            }
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError, ValueError) as error:
            if attempt < max_retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            _log_warning(
                "Internet-noise lookup failed for ip=%s provider=%s error=%s",
                ip_address,
                provider,
                error,
            )
            _inc("lookup_failures")
            _inc("neutral_results")
            return build_internet_noise_assessment(
                provider=provider,
                lookup_status="failed",
                last_checked=_utcnow().isoformat(),
                explanation="Internet-noise lookup failed; the result remains neutral.",
                provider_metadata={"error": str(error)},
            )

    _inc("lookup_failures")
    _inc("neutral_results")
    return build_internet_noise_assessment(
        provider=provider,
        lookup_status="failed",
        last_checked=_utcnow().isoformat(),
        explanation="Internet-noise lookup failed; the result remains neutral.",
    )


def _normalize_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    raw_classification = str(
        payload.get("classification")
        or payload.get("noise_classification")
        or payload.get("verdict")
        or payload.get("status")
        or ""
    ).strip().lower()
    noise = bool(payload.get("noise"))
    riot = bool(payload.get("riot"))
    malicious = bool(payload.get("malicious"))
    confidence = payload.get("confidence")
    confidence_text = str(confidence).strip().lower() if confidence not in (None, "") else None

    if malicious or raw_classification == "malicious":
        assessment = "malicious"
        explanation = "Known malicious internet activity."
    elif raw_classification in {"benign", "benign actor", "internet scanner", "scanner", "research"} or (noise and not malicious) or riot:
        assessment = "commodity"
        explanation = "Known commodity internet scanner."
    else:
        assessment = "neutral"
        explanation = "Internet-noise provider returned no commodity or malicious classification."

    provider_metadata = {
        "raw_classification": raw_classification or None,
        "noise": noise,
        "riot": riot,
        "name": payload.get("name"),
        "category": payload.get("category"),
        "actor": payload.get("actor"),
    }
    return build_internet_noise_assessment(
        assessment=assessment,
        explanation=explanation,
        confidence=confidence_text,
        provider_metadata={key: value for key, value in provider_metadata.items() if value not in (None, "")},
    )
