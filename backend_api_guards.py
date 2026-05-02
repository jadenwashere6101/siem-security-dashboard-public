import os
from flask import jsonify, request

API_KEY_HEADER = "X-API-Key"


def require_api_key():
    ingest_api_key = os.getenv("SIEM_INGEST_API_KEY") or os.getenv("INGEST_API_KEY") or ""
    if not ingest_api_key:
        return jsonify({"error": "Unauthorized"}), 401

    api_key = request.headers.get(API_KEY_HEADER, "")
    if api_key != ingest_api_key:
        return jsonify({"error": "Unauthorized"}), 401

    return None


def require_azure_api_key():
    azure_ingest_api_key = os.getenv("AZURE_INGEST_API_KEY") or ""
    if not azure_ingest_api_key:
        return jsonify({"error": "Unauthorized"}), 401

    api_key = request.headers.get(API_KEY_HEADER, "")
    if api_key != azure_ingest_api_key:
        return jsonify({"error": "Unauthorized"}), 401

    return None


def require_otel_api_key():
    otel_ingest_api_key = os.getenv("OTEL_INGEST_API_KEY") or ""
    if not otel_ingest_api_key:
        return jsonify({"error": "Unauthorized"}), 401

    api_key = request.headers.get(API_KEY_HEADER, "")
    if api_key != otel_ingest_api_key:
        return jsonify({"error": "Unauthorized"}), 401

    return None
