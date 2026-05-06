import inspect

import pytest

from engines.soar_errors import RetryableActionError, SkippedAction
from engines.soar_executor import SimulationExecutor
import engines.soar_executor as soar_executor


def queue_row(action, source_ip="8.8.8.8", alert_id=42):
    return {
        "id": 101,
        "action": action,
        "source_ip": source_ip,
        "alert_id": alert_id,
        "retry_count": 0,
        "max_retries": 3,
        "status": "running",
    }


def test_simulation_executor_block_ip_success():
    result = SimulationExecutor()(queue_row("block_ip", source_ip="8.8.8.8"))

    assert result["code"] == "simulated_block_ip"
    assert result["message"]
    assert result["details"]["source_ip"] == "8.8.8.8"


def test_simulation_executor_flag_high_priority_success():
    result = SimulationExecutor()(queue_row("flag_high_priority", alert_id=42))

    assert result["code"] == "simulated_flag_high_priority"
    assert result["message"]
    assert result["details"]["alert_id"] == 42


def test_simulation_executor_monitor_with_source_ip_success():
    result = SimulationExecutor()(queue_row("monitor", source_ip="8.8.4.4", alert_id=None))

    assert result["code"] == "simulated_monitor"
    assert result["message"]
    assert result["details"]["source_ip"] == "8.8.4.4"


def test_simulation_executor_monitor_with_only_alert_id_success():
    result = SimulationExecutor()(queue_row("monitor", source_ip=None, alert_id=42))

    assert result["code"] == "simulated_monitor"
    assert result["message"]
    assert result["details"]["alert_id"] == 42


@pytest.mark.parametrize(
    "row, expected_code",
    [
        (queue_row("unknown_action"), "unsupported_action"),
        (queue_row("block_ip", source_ip=None), "validation_null_source_ip"),
        (queue_row("block_ip", source_ip="127.0.0.1"), "validation_private_ip"),
        (queue_row("block_ip", source_ip="10.0.0.1"), "validation_private_ip"),
        (queue_row("block_ip", source_ip="192.168.1.1"), "validation_private_ip"),
        (queue_row("block_ip", source_ip="not-an-ip"), "validation_invalid_ip_format"),
        (queue_row("flag_high_priority", alert_id=None), "validation_missing_alert_id"),
        (queue_row("monitor", source_ip=None, alert_id=None), "validation_no_target"),
    ],
)
def test_simulation_executor_validation_skips_without_retryable_errors(row, expected_code):
    with pytest.raises(SkippedAction) as exc_info:
        SimulationExecutor()(row)

    assert exc_info.value.code == expected_code
    assert not isinstance(exc_info.value, RetryableActionError)


def test_simulation_executor_does_not_import_network_or_cloud_clients():
    source = inspect.getsource(soar_executor)

    assert "requests" not in source
    assert "urllib" not in source
    assert "boto3" not in source
    assert "azure" not in source
