import hashlib, ipaddress, itertools, math, random
from typing import Iterable, List, NewType, Optional, Union

IPAddress = NewType("IPAddress", str)


def ip_angle(ip: IPAddress) -> float:
    h = int(hashlib.sha1(ip.encode()).hexdigest(), 16)
    return (h % 10000) / 10000 * 2 * math.pi


def generate_local_pool(
    seed_ips: List[str], prefix_len: int, max_per_seed: Optional[int]
) -> List[IPAddress]:
    Network = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
    Address = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

    def _iter_addresses(net: Network) -> Iterable[Address]:
        if net.num_addresses > 2:
            return net.hosts()
        return iter(net)

    pool: List[IPAddress] = []
    for s in seed_ips:
        try:
            ip = ipaddress.ip_address(s)
        except Exception:
            continue
        net = ipaddress.ip_network(f"{ip}/{prefix_len}", strict=False)
        addrs: Iterable[Address] = _iter_addresses(net)
        if max_per_seed is not None:
            addrs = itertools.islice(addrs, max_per_seed)
        pool.extend(IPAddress(str(a)) for a in addrs)
    random.shuffle(pool)
    return pool
