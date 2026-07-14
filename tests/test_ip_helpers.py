from core.ip_helpers import floor_response_action_for_severity


def test_floor_response_action_for_severity_raises_critical_monitor_to_flag_high_priority():
    assert floor_response_action_for_severity("monitor", "critical") == "flag_high_priority"


def test_floor_response_action_for_severity_never_auto_selects_block_ip():
    assert floor_response_action_for_severity("monitor", "critical") != "block_ip"
    assert floor_response_action_for_severity("flag_high_priority", "critical") == "flag_high_priority"
    assert floor_response_action_for_severity("block_ip", "critical") == "block_ip"
