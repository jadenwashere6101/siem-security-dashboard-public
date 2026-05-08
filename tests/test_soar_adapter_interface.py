import inspect

import pytest

from core.approval_store import approve_request, create_approval_request
from core.ip_helpers import enqueue_response_action
from engines.soar_action_worker import process_next_action
from engines.soar_errors import RetryableActionError, SkippedAction
from engines.soar_executor import AdapterBackedExecutor, SimulationExecutor
from integrations.soar_adapters.base import (
    AdapterExecutionResult,
    AdapterTerminalError,
    BaseSoarActionAdapter,
    classify_adapter_error,
    validate_public_ip_target,
)
from integrations.soar_adapters.config import SoarAdapterConfig, load_soar_adapter_config
from integrations.soar_adapters.linux_firewall import LinuxFirewallDryRunAdapter
from integrations.soar_adapters.registry import SoarAdapterRegistry


def insert_minimal_alert(cur, source_ip="8.8.8.8"):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message)
        VALUES ('test_alert', 'low', %s, 'adapter test alert')
        RETURNING id
        """,
        (source_ip,),
    )
    return cur.fetchone()[0]


def fetch_action_log_count(cur, alert_id):
    cur.execute("SELECT COUNT(*) FROM response_actions_log WHERE alert_id = %s", (alert_id,))
    return cur.fetchone()[0]


def insert_user(cur, username="adapter_approver"):
    cur.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, 'hash', 'super_admin')
        RETURNING id
        """,
        (username,),
    )
    return cur.fetchone()[0]


class FakeSuccessAdapter(BaseSoarActionAdapter):
    adapter_name = "fake_success"
    supported_actions = {"block_ip"}

    def execute(self, row, context=None):
        return AdapterExecutionResult(
            code="fake_block_success",
            message="Fake adapter blocked IP",
            details={
                "adapter": self.adapter_name,
                "action": row["action"],
                "source_ip": row["source_ip"],
                "simulated": True,
            },
        ).as_dict()


class FakeInvalidResultAdapter(BaseSoarActionAdapter):
    adapter_name = "fake_invalid"
    supported_actions = {"block_ip"}

    def execute(self, row, context=None):
        return {"code": "", "message": ""}


def test_base_adapter_contract_defaults():
    adapter = BaseSoarActionAdapter()

    assert adapter.adapter_name == "base"
    assert adapter.supported_actions == set()
    assert adapter.can_handle("block_ip") is False
    with pytest.raises(NotImplementedError):
        adapter.execute({"action": "block_ip"})


def test_adapter_result_contract_shape():
    result = AdapterExecutionResult(
        code="sample_code",
        message="Sample adapter message",
        details={"adapter": "fake"},
    ).as_dict()

    assert result["code"] == "sample_code"
    assert result["message"] == "Sample adapter message"
    assert result["details"]["adapter"] == "fake"


@pytest.mark.parametrize(
    "error, expected",
    [
        (RetryableActionError("retry"), "retryable"),
        (SkippedAction("skip"), "skipped"),
        (AdapterTerminalError("boom"), "terminal_failure"),
    ],
)
def test_adapter_error_classification(error, expected):
    assert classify_adapter_error(error) == expected


def test_validate_public_ip_target_blocks_private():
    with pytest.raises(SkippedAction) as exc_info:
        validate_public_ip_target("10.0.0.1")
    assert exc_info.value.code == "validation_private_ip"


def test_validate_public_ip_target_accepts_public():
    parsed = validate_public_ip_target("8.8.8.8")
    assert str(parsed) == "8.8.8.8"


def test_config_defaults_to_simulation(monkeypatch):
    monkeypatch.delenv("SOAR_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("SOAR_ACTION_TIMEOUT_SECONDS", raising=False)
    config = load_soar_adapter_config()

    assert config.execution_mode == "simulation"
    assert config.timeout_seconds == 5
    assert config.action_to_adapter == {}


def test_registry_fails_closed_in_simulation_mode():
    registry = SoarAdapterRegistry(
        SoarAdapterConfig(
            execution_mode="simulation",
            action_to_adapter={"block_ip": "fake_success"},
            timeout_seconds=5,
            adapter_enabled={"fake_success": True},
        )
    )
    registry.register("fake_success", FakeSuccessAdapter())

    with pytest.raises(SkippedAction) as exc_info:
        registry.get_adapter_for_action("block_ip")
    assert exc_info.value.code == "real_mode_disabled"


def test_registry_unknown_adapter_rejected():
    registry = SoarAdapterRegistry(
        SoarAdapterConfig(
            execution_mode="real",
            action_to_adapter={"block_ip": "missing_adapter"},
            timeout_seconds=5,
            adapter_enabled={"missing_adapter": True},
        )
    )

    with pytest.raises(SkippedAction) as exc_info:
        registry.get_adapter_for_action("block_ip")
    assert exc_info.value.code == "unknown_adapter"


def test_registry_unsupported_action_rejected():
    registry = SoarAdapterRegistry(
        SoarAdapterConfig(
            execution_mode="real",
            action_to_adapter={"block_ip": "fake_success"},
            timeout_seconds=5,
            adapter_enabled={"fake_success": True},
        )
    )
    registry.register("fake_success", FakeSuccessAdapter())

    with pytest.raises(SkippedAction) as exc_info:
        registry.get_adapter_for_action("monitor")
    assert exc_info.value.code == "adapter_not_configured"


def test_adapter_backed_executor_integrates_with_worker(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    queue_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    user_id = insert_user(cur, "adapter_success_approver")
    approval = create_approval_request(conn, queue_id=queue_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    registry = SoarAdapterRegistry(
        SoarAdapterConfig(
            execution_mode="real",
            action_to_adapter={"block_ip": "fake_success"},
            timeout_seconds=5,
            adapter_enabled={"fake_success": True},
        )
    )
    registry.register("fake_success", FakeSuccessAdapter())
    executor = AdapterBackedExecutor(registry)

    result = process_next_action(conn, executor=executor)

    assert result["queue_id"] == queue_id
    assert result["outcome"] == "success"
    assert result["new_status"] == "success"
    assert fetch_action_log_count(cur, alert_id) == 1


def test_adapter_backed_executor_invalid_result_fails(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    queue_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    user_id = insert_user(cur, "adapter_invalid_approver")
    approval = create_approval_request(conn, queue_id=queue_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    registry = SoarAdapterRegistry(
        SoarAdapterConfig(
            execution_mode="real",
            action_to_adapter={"block_ip": "fake_invalid"},
            timeout_seconds=5,
            adapter_enabled={"fake_invalid": True},
        )
    )
    registry.register("fake_invalid", FakeInvalidResultAdapter())
    executor = AdapterBackedExecutor(registry)

    result = process_next_action(conn, executor=executor)

    assert result["queue_id"] == queue_id
    assert result["outcome"] == "failed"


def test_simulation_executor_remains_default_behavior(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    queue_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "monitor")
    conn.commit()

    result = process_next_action(conn)
    assert result["queue_id"] == queue_id
    assert result["outcome"] == "success"
    assert fetch_action_log_count(cur, alert_id) == 1


def test_adapter_modules_do_not_import_network_or_cloud_clients():
    from integrations.soar_adapters import base as adapter_base
    from integrations.soar_adapters import config as adapter_config
    from integrations.soar_adapters import linux_firewall as adapter_linux_firewall
    from integrations.soar_adapters import registry as adapter_registry

    source = (
        inspect.getsource(adapter_base)
        + inspect.getsource(adapter_config)
        + inspect.getsource(adapter_linux_firewall)
        + inspect.getsource(adapter_registry)
    )

    assert "requests" not in source
    assert "urllib" not in source
    assert "http.client" not in source
    assert "boto3" not in source
    assert "azure." not in source
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "socket" not in source


def test_linux_firewall_dry_run_public_ip_plan():
    adapter = LinuxFirewallDryRunAdapter(config={"enabled": True, "firewall_tool": "ufw"})

    result = adapter.execute(
        {
            "id": 7,
            "action": "block_ip",
            "source_ip": "8.8.8.8",
            "alert_id": 99,
        }
    )

    assert result["code"] == "linux_firewall_dry_run_plan"
    assert "DRY RUN" in result["message"]
    assert result["details"]["simulated"] is True
    assert result["details"]["dry_run"] is True
    assert result["details"]["executed"] is False
    assert result["details"]["firewall_tool"] == "ufw"
    assert result["details"]["command_plan"] == ["ufw", "deny", "from", "8.8.8.8"]


@pytest.mark.parametrize(
    "source_ip, expected_code",
    [
        (None, "validation_null_source_ip"),
        ("not-an-ip", "validation_invalid_ip_format"),
        ("10.0.0.1", "validation_private_ip"),
        ("127.0.0.1", "validation_private_ip"),
        ("169.254.1.1", "validation_private_ip"),
        ("224.0.0.1", "validation_private_ip"),
        ("240.0.0.1", "validation_private_ip"),
    ],
)
def test_linux_firewall_dry_run_rejects_unsafe_ips(source_ip, expected_code):
    adapter = LinuxFirewallDryRunAdapter(config={"enabled": True, "firewall_tool": "ufw"})
    with pytest.raises(SkippedAction) as exc_info:
        adapter.execute(
            {
                "id": 8,
                "action": "block_ip",
                "source_ip": source_ip,
                "alert_id": 100,
            }
        )
    assert exc_info.value.code == expected_code


def test_linux_firewall_dry_run_unsupported_backend_fails_safely():
    adapter = LinuxFirewallDryRunAdapter(config={"enabled": True, "firewall_tool": "unknownfw"})
    with pytest.raises(SkippedAction) as exc_info:
        adapter.execute(
            {
                "id": 9,
                "action": "block_ip",
                "source_ip": "8.8.4.4",
                "alert_id": 101,
            }
        )
    assert exc_info.value.code == "unsupported_firewall_tool"


def test_linux_firewall_dry_run_disabled_by_default():
    adapter = LinuxFirewallDryRunAdapter(config={})
    with pytest.raises(SkippedAction) as exc_info:
        adapter.execute(
            {
                "id": 10,
                "action": "block_ip",
                "source_ip": "8.8.4.4",
                "alert_id": 102,
            }
        )
    assert exc_info.value.code == "adapter_disabled"


def test_registry_uses_linux_dry_run_only_when_explicitly_configured():
    registry = SoarAdapterRegistry(
        SoarAdapterConfig(
            execution_mode="real",
            action_to_adapter={"block_ip": "linux_firewall_dry_run"},
            timeout_seconds=5,
            adapter_enabled={"linux_firewall_dry_run": True},
        )
    )
    adapter = LinuxFirewallDryRunAdapter(config={"enabled": True, "firewall_tool": "iptables"})
    registry.register("linux_firewall_dry_run", adapter)

    selected = registry.get_adapter_for_action("block_ip")
    assert selected is adapter


def test_worker_processes_linux_dry_run_as_success(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur)
    queue_id = enqueue_response_action(cur, alert_id, "8.8.8.8", "block_ip")
    user_id = insert_user(cur, "linux_dry_run_approver")
    approval = create_approval_request(conn, queue_id=queue_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    registry = SoarAdapterRegistry(
        SoarAdapterConfig(
            execution_mode="real",
            action_to_adapter={"block_ip": "linux_firewall_dry_run"},
            timeout_seconds=5,
            adapter_enabled={"linux_firewall_dry_run": True},
        )
    )
    registry.register(
        "linux_firewall_dry_run",
        LinuxFirewallDryRunAdapter(config={"enabled": True, "firewall_tool": "nft"}),
    )
    result = process_next_action(conn, executor=AdapterBackedExecutor(registry))

    assert result["queue_id"] == queue_id
    assert result["outcome"] == "success"
    assert result["new_status"] == "success"


def test_worker_processes_linux_dry_run_unsafe_ip_as_skipped(postgres_db):
    conn, cur = postgres_db
    alert_id = insert_minimal_alert(cur, source_ip="10.0.0.5")
    queue_id = enqueue_response_action(cur, alert_id, "10.0.0.5", "block_ip")
    user_id = insert_user(cur, "linux_dry_run_skip_approver")
    approval = create_approval_request(conn, queue_id=queue_id, action="block_ip")
    approve_request(conn, approval["id"], actor_user_id=user_id)
    conn.commit()

    registry = SoarAdapterRegistry(
        SoarAdapterConfig(
            execution_mode="real",
            action_to_adapter={"block_ip": "linux_firewall_dry_run"},
            timeout_seconds=5,
            adapter_enabled={"linux_firewall_dry_run": True},
        )
    )
    registry.register(
        "linux_firewall_dry_run",
        LinuxFirewallDryRunAdapter(config={"enabled": True, "firewall_tool": "ufw"}),
    )
    result = process_next_action(conn, executor=AdapterBackedExecutor(registry))

    assert result["queue_id"] == queue_id
    assert result["outcome"] == "skipped"
    assert result["new_status"] == "skipped"
