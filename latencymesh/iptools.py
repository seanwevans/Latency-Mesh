import hashlib, ipaddress, itertools, math, random
from typing import Iterable, List, NewType, Optional, Union

IPAddress = NewType("IPAddress", str)


def _deterministic_seed(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest(), "big")


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
        addrs_iter = _iter_addresses(net)
        if max_per_seed is not None:
            addrs_iter = itertools.islice(addrs_iter, max_per_seed)
        for addr in addrs_iter:
            pool.append(IPAddress(str(addr)))
    shuffle_seed_material = "|".join(seed_ips) + f"|{prefix_len}|{max_per_seed}"
    shuffle_rng = random.Random(_deterministic_seed(shuffle_seed_material))
    try:
        random.shuffle(pool, random=shuffle_rng.random)
    except TypeError:
        # Support tests that monkeypatch random.shuffle with a simpler signature.
        random.shuffle(pool)
    return pool
