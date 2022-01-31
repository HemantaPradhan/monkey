from threading import Event
from unittest.mock import MagicMock

import pytest

from infection_monkey.i_puppet import (
    ExploiterResultData,
    FingerprintData,
    PingScanData,
    PortScanData,
    PortStatus,
)
from infection_monkey.master import IPScanResults, Propagator
from infection_monkey.model import VictimHost, VictimHostFactory
from infection_monkey.network import NetworkAddress, NetworkInterface
from infection_monkey.telemetry.exploit_telem import ExploitTelem


@pytest.fixture
def mock_victim_host_factory():
    class MockVictimHostFactory(VictimHostFactory):
        def __init__(self):
            pass

        def build_victim_host(self, network_address: NetworkAddress) -> VictimHost:
            domain = network_address.domain or ""
            return VictimHost(network_address.ip, domain)

    return MockVictimHostFactory()


empty_fingerprint_data = FingerprintData(None, None, {})

dot_1_scan_results = IPScanResults(
    PingScanData(True, "windows"),
    {
        22: PortScanData(22, PortStatus.CLOSED, None, None),
        445: PortScanData(445, PortStatus.OPEN, "SMB BANNER", "tcp-445"),
        3389: PortScanData(3389, PortStatus.OPEN, "", "tcp-3389"),
    },
    {
        "SMBFinger": FingerprintData("windows", "vista", {"tcp-445": {"name": "smb_service_name"}}),
        "SSHFinger": empty_fingerprint_data,
        "HTTPFinger": empty_fingerprint_data,
    },
)

dot_3_scan_results = IPScanResults(
    PingScanData(True, "linux"),
    {
        22: PortScanData(22, PortStatus.OPEN, "SSH BANNER", "tcp-22"),
        443: PortScanData(443, PortStatus.OPEN, "HTTPS BANNER", "tcp-443"),
        3389: PortScanData(3389, PortStatus.CLOSED, "", None),
    },
    {
        "SSHFinger": FingerprintData(
            "linux", "ubuntu", {"tcp-22": {"name": "SSH", "banner": "SSH BANNER"}}
        ),
        "HTTPFinger": FingerprintData(
            None,
            None,
            {
                "tcp-80": {"name": "http", "data": ("SERVER_HEADERS", False)},
                "tcp-443": {"name": "http", "data": ("SERVER_HEADERS_2", True)},
            },
        ),
        "SMBFinger": empty_fingerprint_data,
    },
)

dead_host_scan_results = IPScanResults(
    PingScanData(False, None),
    {
        22: PortScanData(22, PortStatus.CLOSED, None, None),
        443: PortScanData(443, PortStatus.CLOSED, None, None),
        3389: PortScanData(3389, PortStatus.CLOSED, "", None),
    },
    {},
)

dot_1_services = {
    "tcp-445": {
        "name": "smb_service_name",
        "display_name": "unknown(TCP)",
        "port": 445,
        "banner": "SMB BANNER",
    },
    "tcp-3389": {"display_name": "unknown(TCP)", "port": 3389, "banner": ""},
}

dot_3_services = {
    "tcp-22": {"name": "SSH", "display_name": "unknown(TCP)", "port": 22, "banner": "SSH BANNER"},
    "tcp-80": {"name": "http", "data": ("SERVER_HEADERS", False)},
    "tcp-443": {
        "name": "http",
        "display_name": "unknown(TCP)",
        "port": 443,
        "banner": "HTTPS BANNER",
        "data": ("SERVER_HEADERS_2", True),
    },
}


@pytest.fixture
def mock_ip_scanner():
    def scan(adresses_to_scan, _, results_callback, stop):
        for address in adresses_to_scan:
            if address.ip.endswith(".1"):
                results_callback(address, dot_1_scan_results)
            elif address.ip.endswith(".3"):
                results_callback(address, dot_3_scan_results)
            else:
                results_callback(address, dead_host_scan_results)

    ip_scanner = MagicMock()
    ip_scanner.scan = MagicMock(side_effect=scan)

    return ip_scanner


class StubExploiter:
    def exploit_hosts(
        self, hosts_to_exploit, exploiter_config, results_callback, scan_completed, stop
    ):
        pass


def test_scan_result_processing(telemetry_messenger_spy, mock_ip_scanner, mock_victim_host_factory):
    p = Propagator(
        telemetry_messenger_spy, mock_ip_scanner, StubExploiter(), mock_victim_host_factory, []
    )
    p.propagate(
        {
            "targets": {
                "subnet_scan_list": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                "local_network_scan": False,
                "inaccessible_subnets": [],
                "blocked_ips": [],
            },
            "network_scan": {},  # This is empty since MockIPscanner ignores it
            "exploiters": {},  # This is empty since StubExploiter ignores it
        },
        Event(),
    )

    assert len(telemetry_messenger_spy.telemetries) == 3

    for t in telemetry_messenger_spy.telemetries:
        data = t.get_data()
        ip = data["machine"]["ip_addr"]

        if ip.endswith(".1"):
            assert data["service_count"] == 2
            assert data["machine"]["os"]["type"] == "windows"
            assert data["machine"]["os"]["version"] == "vista"
            assert data["machine"]["services"] == dot_1_services
            assert data["machine"]["icmp"] is True
        elif ip.endswith(".3"):
            assert data["service_count"] == 3
            assert data["machine"]["os"]["type"] == "linux"
            assert data["machine"]["os"]["version"] == "ubuntu"
            assert data["machine"]["services"] == dot_3_services
            assert data["machine"]["icmp"] is True
        else:
            assert data["service_count"] == 0
            assert data["machine"]["os"] == {}
            assert data["machine"]["services"] == {}
            assert data["machine"]["icmp"] is False


class MockExploiter:
    def exploit_hosts(
        self, exploiter_config, hosts_to_exploit, results_callback, scan_completed, stop
    ):
        scan_completed.wait()
        hte = []
        for _ in range(0, 2):
            hte.append(hosts_to_exploit.get())

        assert hosts_to_exploit.empty()

        for host in hte:
            if host.ip_addr.endswith(".1"):
                results_callback(
                    "PowerShellExploiter",
                    host,
                    ExploiterResultData(True, {}, {}, None),
                )
                results_callback(
                    "SSHExploiter",
                    host,
                    ExploiterResultData(False, {}, {}, "SSH FAILED for .1"),
                )
            elif host.ip_addr.endswith(".2"):
                results_callback(
                    "PowerShellExploiter",
                    host,
                    ExploiterResultData(False, {}, {}, "POWERSHELL FAILED for .2"),
                )
                results_callback(
                    "SSHExploiter",
                    host,
                    ExploiterResultData(False, {}, {}, "SSH FAILED for .2"),
                )
            elif host.ip_addr.endswith(".3"):
                results_callback(
                    "PowerShellExploiter",
                    host,
                    ExploiterResultData(False, {}, {}, "POWERSHELL FAILED for .3"),
                )
                results_callback(
                    "SSHExploiter",
                    host,
                    ExploiterResultData(True, {}, {}, None),
                )


def test_exploiter_result_processing(
    telemetry_messenger_spy, mock_ip_scanner, mock_victim_host_factory
):
    p = Propagator(
        telemetry_messenger_spy, mock_ip_scanner, MockExploiter(), mock_victim_host_factory, []
    )
    p.propagate(
        {
            "targets": {
                "subnet_scan_list": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                "local_network_scan": False,
                "inaccessible_subnets": [],
                "blocked_ips": [],
            },
            "network_scan": {},  # This is empty since MockIPscanner ignores it
            "exploiters": {},  # This is empty since MockExploiter ignores it
        },
        Event(),
    )

    exploit_telems = [t for t in telemetry_messenger_spy.telemetries if isinstance(t, ExploitTelem)]
    assert len(exploit_telems) == 4

    for t in exploit_telems:
        data = t.get_data()
        ip = data["machine"]["ip_addr"]

        assert ip.endswith(".1") or ip.endswith(".3")

        if ip.endswith(".1"):
            if data["exploiter"].startswith("PowerShell"):
                assert data["result"]
            else:
                assert not data["result"]
        elif ip.endswith(".3"):
            if data["exploiter"].startswith("PowerShell"):
                assert not data["result"]
            else:
                assert data["result"]


def test_scan_target_generation(telemetry_messenger_spy, mock_ip_scanner, mock_victim_host_factory):
    local_network_interfaces = [NetworkInterface("10.0.0.9", "/29")]
    p = Propagator(
        telemetry_messenger_spy,
        mock_ip_scanner,
        StubExploiter(),
        mock_victim_host_factory,
        local_network_interfaces,
    )
    p.propagate(
        {
            "targets": {
                "subnet_scan_list": ["10.0.0.0/29", "172.10.20.30"],
                "local_network_scan": True,
                "blocked_ips": ["10.0.0.3"],
                "inaccessible_subnets": ["10.0.0.128/30", "10.0.0.8/29"],
            },
            "network_scan": {},  # This is empty since MockIPscanner ignores it
            "exploiters": {},  # This is empty since MockExploiter ignores it
        },
        Event(),
    )
    expected_ip_scan_list = [
        "10.0.0.0",
        "10.0.0.1",
        "10.0.0.2",
        "10.0.0.4",
        "10.0.0.5",
        "10.0.0.6",
        "10.0.0.8",
        "10.0.0.10",
        "10.0.0.11",
        "10.0.0.12",
        "10.0.0.13",
        "10.0.0.14",
        "10.0.0.128",
        "10.0.0.129",
        "10.0.0.130",
        "172.10.20.30",
    ]

    actual_ip_scan_list = [address.ip for address in mock_ip_scanner.scan.call_args_list[0][0][0]]
    assert actual_ip_scan_list == expected_ip_scan_list
