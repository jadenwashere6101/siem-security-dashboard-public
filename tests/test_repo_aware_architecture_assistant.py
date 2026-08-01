from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from core.ai.config import AI_MODE_LOCAL_ONLY, AiGatewayConfig
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayRequest, AiGatewayResponse, AiRequestMetadata
from core.ai.repo_assistant_service import (
    AI_STATUS_INSUFFICIENT_EVIDENCE,
    AI_STATUS_SCOPE_BOUNDARY,
    QUESTION_TYPE_ARCHITECTURAL,
    QUESTION_TYPE_EVALUATIVE,
    QUESTION_TYPE_FACTUAL,
    QUESTION_TYPE_LIVE_SIEM_DATA,
    answer_repo_question,
    classify_repo_question,
    is_live_siem_data_question,
)
from core.ai.repo_index import RepoIndex
from core.ai.repo_sources import (
    LABEL_CURRENT,
    LABEL_HISTORICAL,
    TRUST_TIER_CURRENT_SOURCE,
    TRUST_TIER_HISTORICAL,
    TRUST_TIER_POLICY,
    classify_repo_path,
    excluded_repo_path,
    stronger_source,
)


class RecordingRepoGateway:
    def __init__(self, content: str | None = None):
        self.content = content or "Detection rules live here [engines/detection_rule_catalog.py:1-3]."
        self.requests: list[AiGatewayRequest] = []

    def generate(self, request: AiGatewayRequest) -> AiGatewayResponse:
        self.requests.append(request)
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content=self.content,
            error=None,
            metadata=AiRequestMetadata(
                provider="local",
                model="qwen3:4b-instruct",
                mode=AI_MODE_LOCAL_ONLY,
                status=AI_STATUS_SUCCESS,
                latency_ms=21,
                estimated_prompt_tokens=10,
                estimated_completion_tokens=8,
                estimated_cost_usd=0,
                local_request=True,
                paid_request=False,
            ),
        )


def _config(**overrides) -> AiGatewayConfig:
    return replace(
        AiGatewayConfig(
            mode=AI_MODE_LOCAL_ONLY,
            configured_mode=AI_MODE_LOCAL_ONLY,
            local_provider="local",
            local_base_url="http://127.0.0.1:11434",
            local_model="qwen3:4b-instruct",
            max_prompt_chars=12000,
        ),
        **overrides,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path) -> Path:
    _write(tmp_path / "AGENTS.md", "# Policy\nDo not deploy from repo assistant.\n")
    _write(tmp_path / "docs/mac-vm-source-of-truth-policy.md", "# Mac VM policy\nMac is source of truth.\n")
    _write(
        tmp_path / "engines/detection_rule_catalog.py",
        "def load_detection_rules():\n    return ['port_scan']\n# detection rules location\n",
    )
    _write(
        tmp_path / "routes/playbook_routes.py",
        "@playbook_bp.route('/api/playbooks/<id>', methods=['POST'])\ndef update_playbook(id):\n    return {}\n",
    )
    _write(
        tmp_path / "core/incidents.py",
        "class IncidentStateFlow:\n    def transition(self):\n        return 'resolved'\n",
    )
    _write(
        tmp_path / "core/soar_worker.py",
        "class SoarWorker:\n    def claim_action(self):\n        return 'tracking-only'\n",
    )
    _write(
        tmp_path / "core/ai/gateway.py",
        "class AiGateway:\n    def generate(self):\n        return 'profile-routed local response'\n",
    )
    _write(tmp_path / "openspec/changes/current-feature/proposal.md", "# Current feature\nActive OpenSpec requirement.\n")
    _write(tmp_path / "openspec/archive/old-feature/proposal.md", "# Old feature\nArchived OpenSpec.\n")
    _write(tmp_path / "docs/MODULARIZATION_HANDOFF.md", "# Historical handoff\nOld backend files.\n")
    _write(tmp_path / "frontend/build/asset.js", "secret build output")
    _write(tmp_path / "venv/lib/python3.11/site-packages/vendor.py", "def vendor_secret():\n    return 'ignored'\n")
    _write(tmp_path / ".venv/lib/python3.11/site-packages/local_vendor.py", "def local_vendor_secret():\n    return 'ignored'\n")
    _write(tmp_path / ".env", "DATABASE_URL=postgres://secret")
    _write(tmp_path / "sonar_issues.csv", "secret,export")
    return tmp_path


def _fake_user(username: str, password: str, role: str):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, role: str):
    username = f"{role}_user"
    password = "testpassword123!"
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


def test_source_policy_includes_current_sources_and_excludes_secrets_runtime_and_generated_paths():
    assert classify_repo_path("AGENTS.md").trust_tier == TRUST_TIER_POLICY
    assert classify_repo_path("engines/detection_rule_catalog.py").trust_tier == TRUST_TIER_CURRENT_SOURCE
    assert classify_repo_path("frontend/src/App.js").label == LABEL_CURRENT
    assert classify_repo_path("openspec/archive/old/proposal.md").label == LABEL_HISTORICAL
    assert excluded_repo_path(".env").reason == "secret_file"
    assert excluded_repo_path("frontend/build/static/main.js").reason == "excluded_runtime_or_generated_path"
    assert excluded_repo_path("venv/lib/python/site-packages/package.py").reason == "excluded_runtime_or_generated_path"
    assert excluded_repo_path(".venv/lib/python/site-packages/package.py").reason == "excluded_runtime_or_generated_path"
    assert excluded_repo_path("sonar_issues.csv").reason == "generated_report"
    assert excluded_repo_path("private.pem").reason == "credential_file"


def test_trust_priority_prefers_policy_source_current_source_and_active_specs():
    policy = classify_repo_path("AGENTS.md")
    source = classify_repo_path("routes/ai_routes.py")
    active_spec = classify_repo_path("openspec/changes/active/proposal.md")
    archived_spec = classify_repo_path("openspec/archive/old/proposal.md")
    assert stronger_source(policy, source) is policy
    assert stronger_source(source, active_spec) is source
    assert stronger_source(active_spec, archived_spec) is active_spec
    assert archived_spec.trust_tier == TRUST_TIER_HISTORICAL


def test_repo_index_returns_metadata_line_ranges_historical_labels_and_refresh(tmp_path):
    root = _repo(tmp_path)
    index = RepoIndex(root)
    result = index.search("where do detection rules live", refresh=True)

    assert result.refreshed is True
    assert result.indexed_files >= 5
    assert result.chunks[0].path == "engines/detection_rule_catalog.py"
    assert result.chunks[0].line_start == 1
    assert result.chunks[0].line_end >= 3
    assert result.chunks[0].source_kind == "source"
    assert result.chunks[0].label == LABEL_CURRENT
    assert result.chunks[0].content_hash
    assert any(match["path"] == ".env" for match in index.search("env database", refresh=False).excluded_matches)

    _write(root / "engines/detection_rule_catalog.py", "def load_detection_rules():\n    return ['ssh_bruteforce']\n")
    refreshed = index.search("ssh brute force detection rules", refresh=True)
    assert refreshed.refreshed is True
    assert refreshed.chunks[0].content_hash != result.chunks[0].content_hash

    historical = index.search("historical old backend files", include_historical=True)
    assert any(chunk.label == LABEL_HISTORICAL for chunk in historical.chunks)


def test_repo_index_excludes_virtualenv_directories(tmp_path):
    index = RepoIndex(_repo(tmp_path))
    result = index.search("venv", refresh=True)

    assert all("venv/" not in chunk.path and ".venv/" not in chunk.path for chunk in result.chunks)
    assert any(match["path"].startswith("venv") for match in result.excluded_matches)
    assert any(match["path"].startswith(".venv") for match in result.excluded_matches)


def test_repo_index_skips_symlinks_that_resolve_outside_repo_root(tmp_path):
    root = _repo(tmp_path / "repo")
    outside = tmp_path / "outside_secret.py"
    outside.write_text("def outside_secret():\n    return 'must not index'\n", encoding="utf-8")
    try:
        (root / "core" / "outside_secret.py").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    result = RepoIndex(root).search("outside secret", refresh=True)

    assert result.chunks == []
    assert any(match["path"] == "core/outside_secret.py" for match in result.excluded_matches)


def test_repo_index_failed_refresh_does_not_publish_partial_state(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    index = RepoIndex(root)
    baseline = index.search("detection rules", refresh=True)
    assert baseline.indexed_files > 0
    baseline_chunk_paths = set(index._chunks_by_path)

    def broken_read(path):
        if path.name == "playbook_routes.py":
            raise RuntimeError("simulated refresh failure")
        return "changed content"

    monkeypatch.setattr("core.ai.repo_index._read_text", broken_read)

    with pytest.raises(RuntimeError):
        index.refresh()

    assert index._indexed_files == baseline.indexed_files
    assert set(index._chunks_by_path) == baseline_chunk_paths
    assert index.search("detection rules", refresh=False).indexed_files == baseline.indexed_files


def test_repo_index_retrieves_representative_architecture_questions(tmp_path):
    index = RepoIndex(_repo(tmp_path))
    cases = [
        ("detection rules location", "engines/detection_rule_catalog.py"),
        ("incident state flow transition", "core/incidents.py"),
        ("playbook update route", "routes/playbook_routes.py"),
        ("current feature OpenSpec requirement", "openspec/changes/current-feature/proposal.md"),
        ("Mac source truth policy", "docs/mac-vm-source-of-truth-policy.md"),
    ]
    for question, expected_path in cases:
        result = index.search(question, refresh=True)
        assert any(chunk.path == expected_path for chunk in result.chunks)


def test_repo_assistant_builds_grounded_prompt_preserves_metadata_and_redacts_excluded_files(tmp_path):
    index = RepoIndex(_repo(tmp_path))
    gateway = RecordingRepoGateway()

    result = answer_repo_question(
        {
            "message": "Where do detection rules live? Also mention DATABASE_URL",
            "client_history": [{"role": "user", "content": "previous"}],
            "refresh": True,
        },
        gateway=gateway,
        config=_config(),
        index=index,
    )

    assert result.status_code == 200
    assert result.payload["status"] == AI_STATUS_SUCCESS
    assert result.payload["question_type"] == QUESTION_TYPE_FACTUAL
    assert result.payload["metadata"]["local_request"] is True
    assert result.payload["metadata"]["paid_request"] is False
    assert result.payload["metadata"]["estimated_cost_usd"] == 0
    assert result.payload["citations"][0]["path"] == "engines/detection_rule_catalog.py"
    assert "DATABASE_URL=postgres://secret" not in gateway.requests[0].prompt
    assert "frontend/build/asset.js" not in gateway.requests[0].prompt
    assert gateway.requests[0].metadata == {
        "context_type": "repository",
        "action": "repo_architecture_chat",
        "read_only": True,
        "question_type": QUESTION_TYPE_FACTUAL,
    }


def test_repo_assistant_classifies_factual_architectural_and_evaluative_questions():
    assert classify_repo_question("Where is the SOAR worker implemented?") == QUESTION_TYPE_FACTUAL
    assert classify_repo_question("How does the AI gateway fit into the worker flow?") == QUESTION_TYPE_ARCHITECTURAL
    assert classify_repo_question("What is my most impressive feature?") == QUESTION_TYPE_EVALUATIVE


def test_repo_assistant_detects_live_siem_data_questions():
    assert is_live_siem_data_question("What is my most severe alert?") is True
    assert is_live_siem_data_question("Which detections are currently firing?") is True
    assert is_live_siem_data_question("Where is the alert route implemented?") is False
    assert is_live_siem_data_question("What is my most impressive feature?") is False


def test_repo_assistant_live_alert_question_returns_boundary_without_retrieval(tmp_path):
    gateway = RecordingRepoGateway()
    index = RepoIndex(_repo(tmp_path))

    with patch.object(index, "search", side_effect=AssertionError("repo retrieval must not run for live SIEM data")):
        result = answer_repo_question(
            {"message": "What is my most severe alert?", "refresh": True},
            gateway=gateway,
            config=_config(),
            index=index,
        )

    assert result.status_code == 200
    assert result.payload["status"] == AI_STATUS_SCOPE_BOUNDARY
    assert result.payload["question_type"] == QUESTION_TYPE_LIVE_SIEM_DATA
    assert "requires live SIEM data" in result.payload["answer"]
    assert "Dashboard" in result.payload["answer"]
    assert result.payload["retrieval"]["skipped"] is True
    assert result.payload["citations"] == []
    assert gateway.requests == []


def test_repo_assistant_mixed_live_data_question_fails_conservatively_without_fabrication(tmp_path):
    gateway = RecordingRepoGateway()
    result = answer_repo_question(
        {"message": "In the repo assistant, summarize my open incidents right now."},
        gateway=gateway,
        config=_config(),
        index=RepoIndex(_repo(tmp_path)),
    )

    assert result.payload["status"] == AI_STATUS_SCOPE_BOUNDARY
    assert result.payload["question_type"] == QUESTION_TYPE_LIVE_SIEM_DATA
    assert "live SIEM data" in result.payload["answer"]
    assert gateway.requests == []


def test_repo_assistant_returns_insufficient_evidence_without_provider_call(tmp_path):
    _write(tmp_path / "docs/MODULARIZATION_HANDOFF.md", "# Old handoff\nOnly stale details.\n")
    gateway = RecordingRepoGateway()

    result = answer_repo_question(
        {"message": "How does the current dashboard work?"},
        gateway=gateway,
        config=_config(),
        index=RepoIndex(tmp_path),
    )

    assert result.payload["status"] == AI_STATUS_INSUFFICIENT_EVIDENCE
    assert result.payload["insufficient_evidence"] is True
    assert gateway.requests == []


def test_repo_assistant_attaches_backend_citations_when_model_citation_syntax_is_missing(tmp_path):
    gateway = RecordingRepoGateway(content="Detection rules live in the engine without a citation.")

    result = answer_repo_question(
        {"message": "Where do detection rules live?", "refresh": True},
        gateway=gateway,
        config=_config(),
        index=RepoIndex(_repo(tmp_path)),
    )

    assert result.payload["status"] == AI_STATUS_SUCCESS
    assert result.payload["insufficient_evidence"] is False
    assert result.payload["answer"] == "Detection rules live in the engine without a citation."
    assert result.payload["citations"][0]["path"] == "engines/detection_rule_catalog.py"


def test_repo_assistant_ignores_model_selected_paths_outside_retrieved_evidence(tmp_path):
    gateway = RecordingRepoGateway(
        content="Detection rules are documented in a fake place [secrets.txt:1-3]."
    )

    result = answer_repo_question(
        {"message": "Where do detection rules live?", "refresh": True},
        gateway=gateway,
        config=_config(),
        index=RepoIndex(_repo(tmp_path)),
    )

    assert result.payload["status"] == AI_STATUS_SUCCESS
    paths = {citation["path"] for citation in result.payload["citations"]}
    assert "secrets.txt" not in paths
    assert "engines/detection_rule_catalog.py" in paths


def test_repo_assistant_evaluative_question_returns_natural_grounded_answer(tmp_path):
    gateway = RecordingRepoGateway(
        content=(
            "Your most impressive feature is the policy-aware repo assistant because it combines "
            "safe source indexing, evidence retrieval, and read-only answering without requiring "
            "the model to format citations perfectly."
        )
    )

    result = answer_repo_question(
        {"message": "What is my most impressive feature?", "refresh": True},
        gateway=gateway,
        config=_config(),
        index=RepoIndex(_repo(tmp_path)),
    )

    assert result.payload["status"] == AI_STATUS_SUCCESS
    assert result.payload["question_type"] == QUESTION_TYPE_EVALUATIVE
    assert "most impressive feature" in result.payload["answer"]
    assert result.payload["citations"]
    assert "Question type: evaluative" in gateway.requests[0].prompt
    assert "make a clear judgment" in gateway.requests[0].prompt


def test_repo_assistant_factual_soar_worker_question_uses_backend_selected_citations(tmp_path):
    gateway = RecordingRepoGateway(content="The SOAR worker is implemented in core/soar_worker.py.")

    result = answer_repo_question(
        {"message": "Where is the SOAR worker implemented?", "refresh": True},
        gateway=gateway,
        config=_config(),
        index=RepoIndex(_repo(tmp_path)),
    )

    assert result.payload["status"] == AI_STATUS_SUCCESS
    assert result.payload["question_type"] == QUESTION_TYPE_FACTUAL
    assert result.payload["answer"] == "The SOAR worker is implemented in core/soar_worker.py."
    assert any(citation["path"] == "core/soar_worker.py" for citation in result.payload["citations"])


def test_repo_assistant_architecture_question_combines_explanation_and_evidence(tmp_path):
    gateway = RecordingRepoGateway(
        content="The AI gateway centralizes generation, while worker code can remain focused on lifecycle orchestration."
    )

    result = answer_repo_question(
        {"message": "How does the AI gateway fit with the worker architecture?", "refresh": True},
        gateway=gateway,
        config=_config(),
        index=RepoIndex(_repo(tmp_path)),
    )

    assert result.payload["status"] == AI_STATUS_SUCCESS
    assert result.payload["question_type"] == QUESTION_TYPE_ARCHITECTURAL
    paths = {citation["path"] for citation in result.payload["citations"]}
    assert "core/ai/gateway.py" in paths
    assert "Question type: architectural" in gateway.requests[0].prompt
    assert "explain relationships" in gateway.requests[0].prompt


def test_repo_assistant_routes_require_super_admin_and_validate_payload(client):
    response = client.post("/ai/repo/chat", json={"message": "Where are routes?"})
    assert response.status_code in {302, 401}

    for role in ("analyst", "viewer"):
        patchers = _login_role(client, role=role)
        try:
            response = client.post("/ai/repo/chat", json={"message": "Where are routes?"})
            assert response.status_code == 403
        finally:
            client.post("/logout")
            _stop_patchers(patchers)

    patchers = _login_role(client, role="super_admin")
    try:
        with patch("routes.ai_routes.answer_repo_question") as service:
            service.return_value.payload = {"status": "success", "answer": "ok"}
            service.return_value.status_code = 200
            response = client.post("/ai/repo/chat", json={"message": "Where are routes?"})
            assert response.status_code == 200
            assert response.get_json()["answer"] == "ok"
            service.assert_called_once()
        response = client.post("/ai/repo/chat", data="not json", content_type="text/plain")
        assert response.status_code == 400
    finally:
        _stop_patchers(patchers)


def test_repo_assistant_implementation_has_no_shell_db_or_mutation_calls():
    service_source = Path("core/ai/repo_assistant_service.py").read_text(encoding="utf-8")
    index_source = Path("core/ai/repo_index.py").read_text(encoding="utf-8")
    route_source = Path("routes/ai_routes.py").read_text(encoding="utf-8")
    combined = service_source + index_source + route_source
    forbidden = [
        "subprocess",
        "os.system",
        "get_db_connection",
        "psycopg2",
        "git push",
        "git commit",
        "rsync",
        "ssh ",
        "open(",
        "write_text(",
    ]
    for token in forbidden:
        assert token not in combined
