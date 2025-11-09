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
        pool = iptools.generate_local_pool(seed_ips, prefix_len=30, max_per_seed=None)
        # /30 network should provide two host addresses
        assert set(pool) == {
            iptools.IPAddress("192.0.2.1"),
            iptools.IPAddress("192.0.2.2"),
        }

    def test_limits_addresses_per_seed(self):
        seed_ips = ["198.51.100.5"]
        pool_first = iptools.generate_local_pool(
            seed_ips, prefix_len=24, max_per_seed=1
        )
        pool_second = iptools.generate_local_pool(
            seed_ips, prefix_len=24, max_per_seed=1
        )

        assert pool_first == pool_second
        assert len(pool_first) == 1
        network = ipaddress.ip_network("198.51.100.5/24", strict=False)
        assert pool_first[0] in {iptools.IPAddress(str(a)) for a in network}

        with mock.patch("latencymesh.iptools.random.shuffle", lambda seq: None):
            pool = iptools.generate_local_pool(seed_ips, prefix_len=24, max_per_seed=1)

        assert pool == [iptools.IPAddress("198.51.100.1")]

    def test_handles_large_ipv6_prefix_quickly(self):
        seed_ips = ["2001:db8::1"]

        with mock.patch("latencymesh.iptools.random.shuffle", lambda seq: None):
            pool = iptools.generate_local_pool(seed_ips, prefix_len=64, max_per_seed=5)

        assert pool == [
            iptools.IPAddress("2001:db8::1"),
            iptools.IPAddress("2001:db8::2"),
            iptools.IPAddress("2001:db8::3"),
            iptools.IPAddress("2001:db8::4"),
            iptools.IPAddress("2001:db8::5"),
        ]
