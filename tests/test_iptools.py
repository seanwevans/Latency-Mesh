import ipaddress
from unittest import mock

import pytest

from latencymesh import iptools


class TestIpAngle:
    def test_ip_angle_is_deterministic_and_in_range(self):
        ip = iptools.IPAddress("192.0.2.1")
        angle_first = iptools.ip_angle(ip)
        angle_second = iptools.ip_angle(ip)
        assert angle_first == angle_second
        assert 0.0 <= angle_first < 2 * iptools.math.pi


class TestGenerateLocalPool:
    def test_skips_invalid_addresses_and_generates_hosts(self):
        seed_ips = ["not-an-ip", "192.0.2.1"]
        with mock.patch("latencymesh.iptools.random.shuffle", lambda seq: None):
            pool = iptools.generate_local_pool(
                seed_ips, prefix_len=30, max_per_seed=None
            )
        # /30 network should provide two host addresses
        assert pool == [
            iptools.IPAddress("192.0.2.1"),
            iptools.IPAddress("192.0.2.2"),
        ]

    def test_limits_addresses_per_seed(self):
        seed_ips = ["198.51.100.5"]
        fake_sample = [ipaddress.ip_address("198.51.100.5")]

        with (
            mock.patch("latencymesh.iptools.random.sample", return_value=fake_sample),
            mock.patch("latencymesh.iptools.random.shuffle", lambda seq: None),
        ):
            pool = iptools.generate_local_pool(seed_ips, prefix_len=24, max_per_seed=1)

        assert pool == [iptools.IPAddress("198.51.100.5")]
