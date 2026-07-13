"""Strict Sigma subset import for the Detection Playground (Version 3).

Sigma YAML is parsed safely, validated against an explicit allowlist, mapped
onto this SIEM's canonical sources/fields, and compiled into the existing
bounded temporary-rule model. Compilation feeds only
``engines.detection_simulator``'s temporary-rule evaluator — this module is
not a second detection engine and does not execute Sigma semantics directly.

See openspec/changes/add-sigma-subset-import-to-detection-playground/.
"""
from __future__ import annotations

import re
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from engines.detection_simulator import (
    SOURCE_TYPE_BY_SOURCE,
    TEMPORARY_RULE_ALLOWED_FIELDS_BY_SOURCE,
    TEMPORARY_RULE_GROUPABLE_FIELDS_BY_SOURCE,
    TEMPORARY_RULE_SUPPORTED_INPUT_FORMATS,
    SimulationValidationError,
)

# --- bounds -----------------------------------------------------------------

MAX_SIGMA_YAML_BYTES = 64 * 1024
MAX_SIGMA_YAML_DEPTH = 12
MAX_SIGMA_YAML_NODES = 400
MAX_SIGMA_SELECTION_FIELDS = 20
MAX_SIGMA_SELECTIONS = 20
MAX_SIGMA_LIST_VALUES = 20
MAX_SIGMA_CONDITION_LENGTH = 512
MAX_SIGMA_TAGS = 40
MAX_SIGMA_STRING_LENGTH = 512

SIGMA_SUBSET_COMPATIBILITY_NOTE = (
    "Strict Sigma subset import for Detection Playground Version 3; "
    "not full Sigma compatibility."
)

ALLOWED_TOP_LEVEL_KEYS = frozenset(
    {
        "title",
        "id",
        "status",
        "description",
        "author",
        "date",
        "logsource",
        "detection",
        "level",
        "tags",
    }
)

ALLOWED_LOGSOURCE_KEYS = frozenset({"product", "service", "category", "definition"})
ALLOWED_SIGMA_LEVELS = frozenset({"informational", "low", "medium", "high", "critical"})
ALLOWED_FIELD_MODIFIERS = frozenset({"contains", "startswith", "endswith"})
REJECTED_FIELD_MODIFIERS = frozenset(
    {
        "re",
        "regex",
        "cidr",
        "base64",
        "base64offset",
        "utf16",
        "utf16le",
        "utf16be",
        "wide",
        "all",
        "windash",
        "expand",
        "cased",
        "gt",
        "gte",
        "lt",
        "lte",
    }
)

LEVEL_TO_SEVERITY = {
    "informational": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}

ATTACK_TAG_PATTERN = re.compile(r"^attack\.t(\d{4}(?:\.\d{3})?)$", re.IGNORECASE)
CONDITION_TOKEN_PATTERN = re.compile(
    r"\s*(?:(\()|(\))|(\bnot\b)|(\band\b)|(\bor\b)|([A-Za-z_][A-Za-z0-9_]*)|(.))",
    re.IGNORECASE,
)

# Explicit, fail-closed logsource fingerprints. Each entry matches when every
# (key, lowercase-value) pair is present on the Sigma logsource object.
# Ambiguity (different canonical sources matching the same input) is rejected.
LOGSOURCE_FINGERPRINTS: tuple[tuple[frozenset[tuple[str, str]], str], ...] = (
    (frozenset({("product", "pfsense")}), "pfsense"),
    (frozenset({("product", "pfsense"), ("category", "firewall")}), "pfsense"),
    (frozenset({("service", "pfsense")}), "pfsense"),
    (frozenset({("product", "nginx")}), "nginx"),
    (frozenset({("service", "nginx")}), "nginx"),
    (frozenset({("product", "nginx"), ("category", "webserver")}), "nginx"),
    (frozenset({("product", "honeypot")}), "honeypot"),
    (frozenset({("service", "honeypot")}), "honeypot"),
    (frozenset({("product", "bank_app")}), "bank_app"),
    (frozenset({("service", "bank_app")}), "bank_app"),
    (frozenset({("product", "bank")}), "bank_app"),
    (frozenset({("product", "azure_insights")}), "azure_insights"),
    (frozenset({("product", "azure"), ("service", "insights")}), "azure_insights"),
    (frozenset({("product", "azure"), ("service", "applicationinsights")}), "azure_insights"),
    (frozenset({("product", "opentelemetry")}), "opentelemetry"),
    (frozenset({("product", "otel")}), "opentelemetry"),
    (frozenset({("service", "opentelemetry")}), "opentelemetry"),
)

# Source-aware Sigma field alias -> normalized temporary-rule field.
# Only aliases listed here are accepted; everything else fails closed.
FIELD_ALIASES_BY_SOURCE: dict[str, dict[str, frozenset[str]]] = {
    "honeypot": {
        "source_ip": frozenset({"source_ip", "src_ip", "srcip", "client_ip", "c-ip"}),
        "username": frozenset({"username", "user", "user.name", "UserName"}),
        "event_type": frozenset({"event_type", "EventType", "event.type"}),
        "severity": frozenset({"severity", "Severity"}),
    },
    "bank_app": {
        "source_ip": frozenset({"source_ip", "src_ip", "srcip", "client_ip", "c-ip", "ClientIP"}),
        "username": frozenset({"username", "user", "user.name", "UserName", "userPrincipalName"}),
        "event_type": frozenset({"event_type", "EventType", "event.type"}),
        "event_outcome": frozenset({"event_outcome", "outcome", "EventOutcome"}),
        "severity": frozenset({"severity", "Severity"}),
    },
    "pfsense": {
        "source_ip": frozenset({"source_ip", "src_ip", "srcip", "src", "SourceIP"}),
        "destination_ip": frozenset({"destination_ip", "dst_ip", "dstip", "dst", "DestinationIP"}),
        "destination_port": frozenset(
            {"destination_port", "dst_port", "dstport", "dport", "DestinationPort"}
        ),
        "event_type": frozenset({"event_type", "EventType", "event.type"}),
        "action": frozenset({"action", "Action"}),
        "severity": frozenset({"severity", "Severity"}),
    },
    "nginx": {
        "source_ip": frozenset({"source_ip", "src_ip", "srcip", "client_ip", "c-ip", "remote_addr"}),
        "event_type": frozenset({"event_type", "EventType", "event.type"}),
        "http_status": frozenset({"http_status", "status", "status_code", "statusCode", "cs-status"}),
        "severity": frozenset({"severity", "Severity"}),
    },
    "azure_insights": {
        "source_ip": frozenset({"source_ip", "src_ip", "ClientIP", "client_ip", "callerIpAddress"}),
        "username": frozenset({"username", "user", "userPrincipalName", "UserName", "identity"}),
        "event_type": frozenset({"event_type", "EventType", "event.type", "operationName"}),
        "event_outcome": frozenset({"event_outcome", "outcome", "resultType"}),
        "http_status": frozenset({"http_status", "status", "status_code", "resultCode", "responseCode"}),
        "severity": frozenset({"severity", "Severity"}),
    },
    "opentelemetry": {
        "source_ip": frozenset({"source_ip", "src_ip", "client_ip", "net.peer.ip"}),
        "event_type": frozenset({"event_type", "EventType", "event.type"}),
        "http_status": frozenset({"http_status", "status", "http.status_code", "status_code"}),
        "severity": frozenset({"severity", "Severity"}),
    },
}


def _validation_error(message: str, *, failure_class: str, element: str, reason: str):
    raise SimulationValidationError(
        message,
        details={
            "class": failure_class,
            "element": element,
            "reason": reason,
            "compatibility": SIGMA_SUBSET_COMPATIBILITY_NOTE,
        },
    )


def _measure_yaml_structure(node: Any, *, depth: int = 1, counter: list[int] | None = None) -> int:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_SIGMA_YAML_NODES:
        _validation_error(
            "Sigma YAML exceeds maximum structural size",
            failure_class="oversized_yaml",
            element="document",
            reason=f"Document exceeds {MAX_SIGMA_YAML_NODES} nodes",
        )
    if depth > MAX_SIGMA_YAML_DEPTH:
        _validation_error(
            "Sigma YAML exceeds maximum nesting depth",
            failure_class="oversized_yaml",
            element="document",
            reason=f"Document exceeds maximum depth of {MAX_SIGMA_YAML_DEPTH}",
        )
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                _validation_error(
                    "Sigma YAML mapping keys must be strings",
                    failure_class="malformed_yaml",
                    element="document",
                    reason="Non-string mapping keys are not allowed",
                )
            _measure_yaml_structure(value, depth=depth + 1, counter=counter)
    elif isinstance(node, list):
        for item in node:
            _measure_yaml_structure(item, depth=depth + 1, counter=counter)
    elif isinstance(node, (str, int, float, bool)) or node is None:
        pass
    else:
        _validation_error(
            "Sigma YAML contains unsupported node types",
            failure_class="malformed_yaml",
            element="document",
            reason=f"Unsupported YAML node type: {type(node).__name__}",
        )
    return counter[0]


def parse_sigma_yaml(sigma_yaml: str) -> dict:
    """Safe-parse Sigma YAML text into a bounded mapping."""
    if not isinstance(sigma_yaml, str):
        _validation_error(
            "sigma_yaml must be a string",
            failure_class="invalid_request",
            element="sigma_yaml",
            reason="sigma_yaml must be a string",
        )
    if not sigma_yaml.strip():
        _validation_error(
            "sigma_yaml must be a non-empty string",
            failure_class="invalid_request",
            element="sigma_yaml",
            reason="Empty Sigma YAML is not allowed",
        )
    encoded = sigma_yaml.encode("utf-8")
    if len(encoded) > MAX_SIGMA_YAML_BYTES:
        _validation_error(
            f"sigma_yaml exceeds maximum size of {MAX_SIGMA_YAML_BYTES} bytes",
            failure_class="oversized_yaml",
            element="sigma_yaml",
            reason=f"Payload exceeds {MAX_SIGMA_YAML_BYTES} bytes",
        )

    try:
        loaded = yaml.safe_load(sigma_yaml)
    except (ScannerError, ParserError, ConstructorError, yaml.YAMLError) as error:
        _validation_error(
            f"Malformed Sigma YAML: {error}",
            failure_class="malformed_yaml",
            element="sigma_yaml",
            reason=str(error),
        )

    if not isinstance(loaded, dict):
        _validation_error(
            "Sigma YAML must decode to a mapping",
            failure_class="malformed_yaml",
            element="document",
            reason="Top-level YAML value must be a mapping/object",
        )

    _measure_yaml_structure(loaded)
    return loaded


def _require_string(value: Any, element: str, *, optional: bool = False) -> str | None:
    if value is None:
        if optional:
            return None
        _validation_error(
            f"Missing required Sigma field '{element}'",
            failure_class="unsupported_metadata",
            element=element,
            reason=f"'{element}' is required for the Version 3 Sigma subset",
        )
    if not isinstance(value, str) or not value.strip():
        _validation_error(
            f"Sigma field '{element}' must be a non-empty string",
            failure_class="unsupported_metadata",
            element=element,
            reason="Value must be a non-empty string",
        )
    trimmed = value.strip()
    if len(trimmed) > MAX_SIGMA_STRING_LENGTH:
        _validation_error(
            f"Sigma field '{element}' exceeds maximum length",
            failure_class="unsupported_metadata",
            element=element,
            reason=f"Maximum length is {MAX_SIGMA_STRING_LENGTH}",
        )
    return trimmed


def _parse_metadata(rule: dict) -> dict:
    unexpected = sorted(set(rule) - ALLOWED_TOP_LEVEL_KEYS)
    if unexpected:
        _validation_error(
            f"Unsupported Sigma top-level fields: {', '.join(unexpected)}",
            failure_class="unsupported_construct",
            element=",".join(unexpected),
            reason=(
                "Version 3 accepts only title, id, status, description, author, date, "
                "logsource, detection, level, and tags"
            ),
        )

    for rejected_key in ("correlation", "action", "timeframe", "backend", "pipelines"):
        if rejected_key in rule:
            _validation_error(
                f"Unsupported Sigma construct '{rejected_key}'",
                failure_class="unsupported_construct",
                element=rejected_key,
                reason="Correlation, aggregation/timeframe, and backend-specific extensions are out of scope",
            )

    title = _require_string(rule.get("title"), "title")
    metadata = {
        "title": title,
        "id": _require_string(rule.get("id"), "id", optional=True),
        "status": _require_string(rule.get("status"), "status", optional=True),
        "description": _require_string(rule.get("description"), "description", optional=True),
        "author": _require_string(rule.get("author"), "author", optional=True),
        "date": _require_string(rule.get("date"), "date", optional=True),
    }

    level = rule.get("level")
    if level is None:
        metadata["level"] = None
        metadata["severity"] = "medium"
    else:
        level_text = _require_string(level, "level")
        if level_text not in ALLOWED_SIGMA_LEVELS:
            _validation_error(
                f"Unsupported Sigma level '{level_text}'",
                failure_class="unsupported_metadata",
                element="level",
                reason=f"Allowed levels: {', '.join(sorted(ALLOWED_SIGMA_LEVELS))}",
            )
        metadata["level"] = level_text
        metadata["severity"] = LEVEL_TO_SEVERITY[level_text]

    return metadata


def _parse_tags(raw_tags: Any) -> tuple[list[str], list[str]]:
    if raw_tags is None:
        return [], []
    if not isinstance(raw_tags, list):
        _validation_error(
            "Sigma tags must be a list of strings",
            failure_class="unsupported_metadata",
            element="tags",
            reason="tags must be a list",
        )
    if len(raw_tags) > MAX_SIGMA_TAGS:
        _validation_error(
            f"Sigma tags exceed maximum of {MAX_SIGMA_TAGS}",
            failure_class="unsupported_metadata",
            element="tags",
            reason=f"At most {MAX_SIGMA_TAGS} tags are allowed",
        )

    tags: list[str] = []
    attack_tags: list[str] = []
    for index, item in enumerate(raw_tags):
        if not isinstance(item, str) or not item.strip():
            _validation_error(
                f"Sigma tags[{index}] must be a non-empty string",
                failure_class="unsupported_metadata",
                element=f"tags[{index}]",
                reason="Each tag must be a non-empty string",
            )
        tag = item.strip()
        if len(tag) > MAX_SIGMA_STRING_LENGTH:
            _validation_error(
                f"Sigma tags[{index}] exceeds maximum length",
                failure_class="unsupported_metadata",
                element=f"tags[{index}]",
                reason=f"Maximum length is {MAX_SIGMA_STRING_LENGTH}",
            )
        tags.append(tag)
        match = ATTACK_TAG_PATTERN.match(tag)
        if match:
            attack_tags.append(f"T{match.group(1)}")
    return tags, attack_tags


def map_logsource(logsource: Any) -> dict:
    if not isinstance(logsource, dict) or not logsource:
        _validation_error(
            "Sigma logsource must be a non-empty mapping",
            failure_class="ambiguous_logsource",
            element="logsource",
            reason="logsource is required and must resolve to one canonical source",
        )

    unexpected = sorted(set(logsource) - ALLOWED_LOGSOURCE_KEYS)
    if unexpected:
        _validation_error(
            f"Unsupported logsource fields: {', '.join(unexpected)}",
            failure_class="unsupported_construct",
            element="logsource",
            reason="Only product, service, category, and definition are accepted",
        )

    normalized_pairs: set[tuple[str, str]] = set()
    for key, value in logsource.items():
        if not isinstance(value, str) or not value.strip():
            _validation_error(
                f"logsource.{key} must be a non-empty string",
                failure_class="ambiguous_logsource",
                element=f"logsource.{key}",
                reason="logsource values must be non-empty strings",
            )
        normalized_pairs.add((key, value.strip().lower()))

    matches: list[str] = []
    for fingerprint, canonical_source in LOGSOURCE_FINGERPRINTS:
        if fingerprint.issubset(normalized_pairs):
            if canonical_source not in matches:
                matches.append(canonical_source)

    if not matches:
        provided = ", ".join(f"{key}={value}" for key, value in sorted(normalized_pairs))
        _validation_error(
            "Sigma logsource does not map to a supported canonical source",
            failure_class="ambiguous_logsource",
            element="logsource",
            reason=(
                f"No safe mapping for [{provided}]. Supported sources: "
                f"{', '.join(sorted(SOURCE_TYPE_BY_SOURCE))}"
            ),
        )

    unique_sources = sorted(set(matches))
    if len(unique_sources) > 1:
        _validation_error(
            "Sigma logsource is ambiguous across multiple canonical sources",
            failure_class="ambiguous_logsource",
            element="logsource",
            reason=f"Matched sources: {', '.join(unique_sources)}",
        )

    source = unique_sources[0]
    return {
        "source": source,
        "source_type": SOURCE_TYPE_BY_SOURCE[source],
        "logsource": {key: value.strip() for key, value in logsource.items()},
    }


def map_field_alias(source: str, field_name: str) -> str:
    aliases = FIELD_ALIASES_BY_SOURCE.get(source) or {}
    for normalized_field, alias_set in aliases.items():
        if field_name in alias_set:
            if normalized_field not in TEMPORARY_RULE_ALLOWED_FIELDS_BY_SOURCE[source]:
                break
            return normalized_field
    _validation_error(
        f"Unsupported Sigma field '{field_name}' for source '{source}'",
        failure_class="unsupported_field",
        element=field_name,
        reason=(
            f"No safe mapping exists for field '{field_name}' on canonical source '{source}'. "
            f"Allowed normalized fields: {', '.join(sorted(TEMPORARY_RULE_ALLOWED_FIELDS_BY_SOURCE[source]))}"
        ),
    )


def _split_field_and_modifier(raw_key: str) -> tuple[str, str | None]:
    if "|" not in raw_key:
        return raw_key, None
    field_name, *modifiers = raw_key.split("|")
    if not field_name:
        _validation_error(
            f"Invalid Sigma selection field '{raw_key}'",
            failure_class="unsupported_modifier",
            element=raw_key,
            reason="Field name before modifier is required",
        )
    if len(modifiers) != 1:
        _validation_error(
            f"Unsupported Sigma modifier chain on '{raw_key}'",
            failure_class="unsupported_modifier",
            element=raw_key,
            reason="Only a single approved modifier is allowed per field",
        )
    modifier = modifiers[0].strip().lower()
    if modifier in REJECTED_FIELD_MODIFIERS or modifier not in ALLOWED_FIELD_MODIFIERS:
        _validation_error(
            f"Unsupported Sigma modifier '{modifier}' on field '{field_name}'",
            failure_class="unsupported_modifier",
            element=raw_key,
            reason=(
                f"Modifier '{modifier}' is not approved. "
                f"Allowed modifiers: {', '.join(sorted(ALLOWED_FIELD_MODIFIERS))}"
            ),
        )
    return field_name, modifier


def _normalize_selection_value(value: Any, *, element: str):
    if isinstance(value, bool) or value is None:
        _validation_error(
            f"Unsupported selection value at '{element}'",
            failure_class="unsupported_construct",
            element=element,
            reason="Boolean and null selection values are not supported",
        )
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            _validation_error(
                f"Unsupported non-integer numeric value at '{element}'",
                failure_class="unsupported_construct",
                element=element,
                reason="Only integers and strings are supported as selection values",
            )
        return int(value)
    if isinstance(value, str):
        if not value.strip():
            _validation_error(
                f"Empty selection value at '{element}'",
                failure_class="unsupported_construct",
                element=element,
                reason="Selection values must be non-empty",
            )
        if len(value) > MAX_SIGMA_STRING_LENGTH:
            _validation_error(
                f"Selection value at '{element}' exceeds maximum length",
                failure_class="unsupported_construct",
                element=element,
                reason=f"Maximum length is {MAX_SIGMA_STRING_LENGTH}",
            )
        return value
    _validation_error(
        f"Unsupported selection value type at '{element}'",
        failure_class="unsupported_construct",
        element=element,
        reason=f"Unsupported type {type(value).__name__}",
    )


def _compile_field_predicate(source: str, raw_key: str, raw_value: Any, *, element: str) -> dict:
    field_name, modifier = _split_field_and_modifier(raw_key)
    normalized_field = map_field_alias(source, field_name)

    if isinstance(raw_value, list):
        if not raw_value or len(raw_value) > MAX_SIGMA_LIST_VALUES:
            _validation_error(
                f"Selection list at '{element}' must contain between 1 and {MAX_SIGMA_LIST_VALUES} values",
                failure_class="unsupported_construct",
                element=element,
                reason=f"List size must be 1..{MAX_SIGMA_LIST_VALUES}",
            )
        if modifier is not None:
            _validation_error(
                f"Modifiers are not supported on list values at '{element}'",
                failure_class="unsupported_modifier",
                element=element,
                reason="List values only support exact-match OR semantics (in_list)",
            )
        values = [
            _normalize_selection_value(item, element=f"{element}[{index}]")
            for index, item in enumerate(raw_value)
        ]
        return {"field": normalized_field, "operator": "in_list", "value": values}

    value = _normalize_selection_value(raw_value, element=element)
    if modifier is None:
        return {"field": normalized_field, "operator": "equals", "value": value}
    operator = {
        "contains": "contains",
        "startswith": "starts_with",
        "endswith": "ends_with",
    }[modifier]
    if not isinstance(value, str):
        _validation_error(
            f"Modifier '{modifier}' requires a string value at '{element}'",
            failure_class="unsupported_modifier",
            element=element,
            reason="contains/startswith/endswith apply only to strings",
        )
    return {"field": normalized_field, "operator": operator, "value": value}


def _compile_selection(source: str, selection_name: str, selection_body: Any) -> dict:
    element = f"detection.{selection_name}"
    if not isinstance(selection_body, dict) or not selection_body:
        _validation_error(
            f"Selection '{selection_name}' must be a non-empty mapping",
            failure_class="unsupported_construct",
            element=element,
            reason="Each selection must map fields to values",
        )
    if len(selection_body) > MAX_SIGMA_SELECTION_FIELDS:
        _validation_error(
            f"Selection '{selection_name}' exceeds maximum field count",
            failure_class="unsupported_construct",
            element=element,
            reason=f"At most {MAX_SIGMA_SELECTION_FIELDS} fields per selection",
        )

    predicates = []
    for raw_key, raw_value in selection_body.items():
        if not isinstance(raw_key, str):
            _validation_error(
                f"Selection '{selection_name}' keys must be strings",
                failure_class="unsupported_construct",
                element=element,
                reason="Non-string selection keys are not allowed",
            )
        predicates.append(
            _compile_field_predicate(
                source,
                raw_key,
                raw_value,
                element=f"{element}.{raw_key}",
            )
        )

    if len(predicates) == 1:
        return predicates[0]
    return {"all": predicates}


class _ConditionParser:
    def __init__(self, expression: str, selection_names: set[str]):
        self.expression = expression
        self.selection_names = selection_names
        self.tokens = self._tokenize(expression)
        self.index = 0

    def _tokenize(self, expression: str) -> list[str]:
        if len(expression) > MAX_SIGMA_CONDITION_LENGTH:
            _validation_error(
                "Sigma condition exceeds maximum length",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason=f"Maximum length is {MAX_SIGMA_CONDITION_LENGTH}",
            )
        lowered = expression.strip()
        for banned in ("1 of", "all of", "near", "before", "after", "|", "*", "?"):
            if banned in lowered.lower() if banned.isalpha() else banned in lowered:
                _validation_error(
                    f"Unsupported Sigma condition construct involving '{banned.strip()}'",
                    failure_class="unsupported_condition",
                    element="detection.condition",
                    reason="Wildcard selection expansion, aggregation pipes, and timeframe operators are out of scope",
                )
        # Explicit wildcard / of-pattern checks (case-insensitive words).
        lowered_expr = lowered.lower()
        if re.search(r"\b\d+\s+of\b", lowered_expr) or re.search(r"\ball\s+of\b", lowered_expr):
            _validation_error(
                "Unsupported Sigma condition construct 'N of' / 'all of'",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason="Wildcard selection expansion is out of scope",
            )
        if any(ch in lowered for ch in "*?"):
            _validation_error(
                "Unsupported Sigma condition wildcard",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason="Wildcard selection names are out of scope",
            )

        tokens: list[str] = []
        position = 0
        while position < len(expression):
            match = CONDITION_TOKEN_PATTERN.match(expression, position)
            if not match:
                _validation_error(
                    "Unsupported Sigma condition syntax",
                    failure_class="unsupported_condition",
                    element="detection.condition",
                    reason=f"Could not tokenize condition near: {expression[position:position + 20]!r}",
                )
            position = match.end()
            if match.group(1):
                tokens.append("(")
            elif match.group(2):
                tokens.append(")")
            elif match.group(3):
                tokens.append("not")
            elif match.group(4):
                tokens.append("and")
            elif match.group(5):
                tokens.append("or")
            elif match.group(6):
                tokens.append(match.group(6))
            else:
                _validation_error(
                    f"Unsupported Sigma condition token {match.group(7)!r}",
                    failure_class="unsupported_condition",
                    element="detection.condition",
                    reason="Only named selections with and / or / not and parentheses are supported",
                )
        if not tokens:
            _validation_error(
                "Sigma condition must not be empty",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason="condition is required",
            )
        return tokens

    def _peek(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def _consume(self, expected: str | None = None) -> str:
        token = self._peek()
        if token is None:
            _validation_error(
                "Unexpected end of Sigma condition",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason="Condition ended before a complete expression",
            )
        if expected is not None and token != expected:
            _validation_error(
                f"Expected '{expected}' in Sigma condition, found '{token}'",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason="Condition syntax is invalid for the Version 3 subset",
            )
        self.index += 1
        return token

    def parse(self) -> dict:
        tree = self._parse_or()
        if self._peek() is not None:
            _validation_error(
                f"Unexpected token '{self._peek()}' in Sigma condition",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason="Condition has trailing unsupported tokens",
            )
        return tree

    def _parse_or(self) -> dict:
        node = self._parse_and()
        nodes = [node]
        while self._peek() == "or":
            self._consume("or")
            nodes.append(self._parse_and())
        if len(nodes) == 1:
            return nodes[0]
        return {"any": nodes}

    def _parse_and(self) -> dict:
        node = self._parse_not()
        nodes = [node]
        while self._peek() == "and":
            self._consume("and")
            nodes.append(self._parse_not())
        if len(nodes) == 1:
            return nodes[0]
        return {"all": nodes}

    def _parse_not(self) -> dict:
        if self._peek() == "not":
            self._consume("not")
            return {"not": self._parse_not()}
        return self._parse_primary()

    def _parse_primary(self) -> dict:
        token = self._peek()
        if token == "(":
            self._consume("(")
            node = self._parse_or()
            self._consume(")")
            return node
        name = self._consume()
        if name in {"and", "or", "not", "(", ")"}:
            _validation_error(
                f"Unexpected keyword '{name}' in Sigma condition",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason="Expected a selection name",
            )
        if name not in self.selection_names:
            _validation_error(
                f"Unknown selection '{name}' in Sigma condition",
                failure_class="unsupported_condition",
                element="detection.condition",
                reason=f"Selection '{name}' is not defined under detection",
            )
        return {"selection": name}


def _resolve_condition_tree(node: dict, compiled_selections: dict[str, dict]) -> dict:
    if "selection" in node:
        return compiled_selections[node["selection"]]
    if "not" in node:
        return {"not": _resolve_condition_tree(node["not"], compiled_selections)}
    if "all" in node:
        return {"all": [_resolve_condition_tree(child, compiled_selections) for child in node["all"]]}
    if "any" in node:
        return {"any": [_resolve_condition_tree(child, compiled_selections) for child in node["any"]]}
    _validation_error(
        "Internal condition tree is invalid",
        failure_class="unsupported_condition",
        element="detection.condition",
        reason="Condition compiler produced an invalid node",
    )


def _compile_detection(source: str, detection: Any) -> dict:
    if not isinstance(detection, dict) or not detection:
        _validation_error(
            "Sigma detection must be a non-empty mapping",
            failure_class="unsupported_construct",
            element="detection",
            reason="detection with named selections and condition is required",
        )

    if "timeframe" in detection:
        _validation_error(
            "Sigma aggregation/timeframe syntax is not supported",
            failure_class="unsupported_construct",
            element="detection.timeframe",
            reason="Aggregation and timeframe syntax are out of scope for Version 3",
        )

    condition_expr = detection.get("condition")
    if not isinstance(condition_expr, str) or not condition_expr.strip():
        _validation_error(
            "Sigma detection.condition must be a non-empty string",
            failure_class="unsupported_condition",
            element="detection.condition",
            reason="condition is required",
        )

    selection_items = {key: value for key, value in detection.items() if key != "condition"}
    if not selection_items:
        _validation_error(
            "Sigma detection must define at least one named selection",
            failure_class="unsupported_construct",
            element="detection",
            reason="At least one selection map is required",
        )
    if len(selection_items) > MAX_SIGMA_SELECTIONS:
        _validation_error(
            "Sigma detection exceeds maximum selection count",
            failure_class="unsupported_construct",
            element="detection",
            reason=f"At most {MAX_SIGMA_SELECTIONS} selections are allowed",
        )

    for name in selection_items:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            _validation_error(
                f"Unsupported selection name '{name}'",
                failure_class="unsupported_construct",
                element=f"detection.{name}",
                reason="Selection names must be alphanumeric identifiers without wildcards",
            )

    compiled_selections = {
        name: _compile_selection(source, name, body) for name, body in selection_items.items()
    }
    parsed = _ConditionParser(condition_expr.strip(), set(compiled_selections)).parse()
    return _resolve_condition_tree(parsed, compiled_selections)


def _default_input_format(source: str, requested: str | None) -> str:
    supported = TEMPORARY_RULE_SUPPORTED_INPUT_FORMATS[source]
    if requested is not None:
        if requested not in supported:
            _validation_error(
                f"input_format '{requested}' is not supported for source '{source}'",
                failure_class="invalid_request",
                element="input_format",
                reason=f"Allowed formats: {', '.join(sorted(supported))}",
            )
        return requested
    for preferred in ("json_array", "json_lines", "raw_text"):
        if preferred in supported:
            return preferred
    return sorted(supported)[0]


def _default_group_by_field(source: str) -> str:
    groupable = TEMPORARY_RULE_GROUPABLE_FIELDS_BY_SOURCE[source]
    if "source_ip" in groupable:
        return "source_ip"
    return sorted(groupable)[0]


def compile_sigma_rule_to_temporary_rule(
    sigma_yaml: str,
    *,
    input_format: str | None = None,
    event_type: str | None = None,
) -> dict:
    """Parse, validate, map, and compile Sigma YAML into a temporary-rule object.

    The returned object is intended only for
    ``engines.detection_simulator._run_temporary_rule_simulation`` / the shared
    temporary-rule evaluator. It is not executed here.
    """
    rule = parse_sigma_yaml(sigma_yaml)
    metadata = _parse_metadata(rule)
    tags, attack_tags = _parse_tags(rule.get("tags"))
    mapped_logsource = map_logsource(rule.get("logsource"))
    source = mapped_logsource["source"]
    predicate = _compile_detection(source, rule.get("detection"))
    resolved_input_format = _default_input_format(source, input_format)

    if event_type is not None and not isinstance(event_type, str):
        _validation_error(
            "event_type must be a string when provided",
            failure_class="invalid_request",
            element="event_type",
            reason="event_type must be a string or omitted",
        )

    compiled = {
        "source": source,
        "source_type": mapped_logsource["source_type"],
        "input_format": resolved_input_format,
        "event_type": event_type.strip() if isinstance(event_type, str) and event_type.strip() else None,
        "condition": predicate,
        "aggregation": {"type": "count", "group_by_field": _default_group_by_field(source)},
        # Sigma aggregation/timeframe are out of scope: match any qualifying
        # pasted event (threshold 1) inside the request-scoped window.
        "threshold": 1,
        "window_minutes": 15,
        "severity": metadata["severity"],
        "mitre_technique_id": None,
        "title": metadata["title"],
        "id": metadata["id"],
        "status": metadata["status"],
        "description": metadata["description"],
        "author": metadata["author"],
        "date": metadata["date"],
        "level": metadata["level"],
        "tags": tags,
        "attack_tags": attack_tags,
        "logsource": mapped_logsource["logsource"],
        "rule_provenance": "sigma_subset_import",
        "sigma_subset": True,
    }
    return compiled


def build_normalized_internal_rule_preview(compiled_rule: dict) -> dict:
    """Analyst-facing preview of the compiled internal playground rule."""
    return {
        "compatibility": SIGMA_SUBSET_COMPATIBILITY_NOTE,
        "source": compiled_rule["source"],
        "source_type": compiled_rule["source_type"],
        "input_format": compiled_rule["input_format"],
        "event_type": compiled_rule.get("event_type"),
        "condition": compiled_rule["condition"],
        "aggregation": compiled_rule["aggregation"],
        "threshold": compiled_rule["threshold"],
        "window_minutes": compiled_rule["window_minutes"],
        "severity": compiled_rule["severity"],
        "title": compiled_rule.get("title"),
        "id": compiled_rule.get("id"),
        "status": compiled_rule.get("status"),
        "description": compiled_rule.get("description"),
        "author": compiled_rule.get("author"),
        "date": compiled_rule.get("date"),
        "level": compiled_rule.get("level"),
        "tags": compiled_rule.get("tags") or [],
        "attack_tags": compiled_rule.get("attack_tags") or [],
        "logsource": compiled_rule.get("logsource"),
        "rule_provenance": compiled_rule.get("rule_provenance"),
        "sigma_subset": True,
        "evaluator": "temporary_playground_rule",
    }
