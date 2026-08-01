from core.ai.config import AI_MODE_LOCAL_ONLY
import scripts.soc_briefing_worker as worker_script


def test_soc_briefing_worker_script_passes_environment_gateway_config(monkeypatch):
    captured = {}

    monkeypatch.setenv("AI_GATEWAY_MODE", "local_only")
    monkeypatch.setenv("AI_LOCAL_PROVIDER", "ollama")
    monkeypatch.setenv("AI_LOCAL_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("AI_LOCAL_MODEL", "llama3.1:8b")

    def fake_run_soc_briefing_worker(**kwargs):
        captured.update(kwargs)
        return {"errors": 0}

    monkeypatch.setattr(worker_script, "install_shutdown_signal_handlers", lambda _shutdown: None)
    monkeypatch.setattr(worker_script, "run_soc_briefing_worker", fake_run_soc_briefing_worker)

    assert worker_script.main(["--json"]) == 0

    config = captured["gateway_config"]
    assert config.mode == AI_MODE_LOCAL_ONLY
    assert config.local_provider == "ollama"
    assert config.local_configured is True
    assert config.paid_fallback_enabled is False
    assert "http://127.0.0.1:11434" not in str(config.sanitized())
