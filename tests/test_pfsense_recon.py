import ipaddress

from core.pfsense_recon import classify_pfsense_tcp_traffic_role


PROTECTED_NETWORKS = [ipaddress.ip_network("8.14.136.0/24")]


def test_classify_tcp_syn_without_ack_as_initiation_like():
    result = classify_pfsense_tcp_traffic_role(
        source_ip="8.14.136.151",
        destination_ip="203.0.113.10",
        protocol="tcp",
        direction="out",
        source_port=51514,
        destination_port=22,
        tcp_flags="S",
        protected_networks=PROTECTED_NETWORKS,
    )

    assert result["classification"] == "initiation_like"


def test_classify_tcp_syn_ack_as_reply_like():
    result = classify_pfsense_tcp_traffic_role(
        source_ip="203.0.113.10",
        destination_ip="8.14.136.151",
        protocol="tcp",
        direction="in",
        source_port=443,
        destination_port=51999,
        tcp_flags="SA",
        protected_networks=PROTECTED_NETWORKS,
    )

    assert result["classification"] == "reply_or_teardown_like"


def test_classify_tcp_ack_only_service_to_ephemeral_as_reply_like():
    result = classify_pfsense_tcp_traffic_role(
        source_ip="8.14.136.151",
        destination_ip="216.226.76.10",
        protocol="tcp",
        direction="out",
        source_port=443,
        destination_port=52420,
        tcp_flags="A",
        protected_networks=PROTECTED_NETWORKS,
    )

    assert result["classification"] == "reply_or_teardown_like"
    assert "ephemeral port" in result["reason"]


def test_classify_tcp_fin_ack_as_reply_like():
    result = classify_pfsense_tcp_traffic_role(
        source_ip="8.14.136.151",
        destination_ip="216.226.76.10",
        protocol="tcp",
        direction="out",
        source_port=443,
        destination_port=52420,
        tcp_flags="FA",
        protected_networks=PROTECTED_NETWORKS,
    )

    assert result["classification"] == "reply_or_teardown_like"


def test_classify_tcp_rst_ack_as_reply_like():
    result = classify_pfsense_tcp_traffic_role(
        source_ip="8.14.136.151",
        destination_ip="216.226.76.10",
        protocol="tcp",
        direction="out",
        source_port=443,
        destination_port=52420,
        tcp_flags="RA",
        protected_networks=PROTECTED_NETWORKS,
    )

    assert result["classification"] == "reply_or_teardown_like"


def test_classify_missing_tcp_flags_as_ambiguous():
    result = classify_pfsense_tcp_traffic_role(
        source_ip="8.14.136.151",
        destination_ip="216.226.76.10",
        protocol="tcp",
        direction="out",
        source_port=443,
        destination_port=52420,
        tcp_flags=None,
        protected_networks=PROTECTED_NETWORKS,
    )

    assert result["classification"] == "ambiguous"


def test_classify_non_tcp_as_not_applicable():
    result = classify_pfsense_tcp_traffic_role(
        source_ip="8.14.136.151",
        destination_ip="216.226.76.10",
        protocol="udp",
        direction="out",
        source_port=53,
        destination_port=53000,
        tcp_flags=None,
        protected_networks=PROTECTED_NETWORKS,
    )

    assert result["classification"] == "not_applicable"
