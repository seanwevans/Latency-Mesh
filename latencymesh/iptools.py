import hashlib, ipaddress, math, random
from typing import List, NewType, Optional

IPAddress = NewType("IPAddress", str)


def ip_angle(ip: IPAddress) -> float:
    h = int(hashlib.sha1(ip.encode()).hexdigest(), 16)
    return (h % 10000) / 10000 * 2 * math.pi


def generate_local_pool(
    seed_ips: List[str], prefix_len: int, max_per_seed: Optional[int]
) -> List[IPAddress]:
    pool: List[IPAddress] = []
    for s in seed_ips:
        try:
            ip = ipaddress.ip_address(s)
        except Exception:
            continue
        net = ipaddress.ip_network(f"{ip}/{prefix_len}", strict=False)
        addrs = list(net.hosts()) if net.num_addresses > 2 else list(net)
        if max_per_seed and len(addrs) > max_per_seed:
            random.seed(hash(s))
            addrs = random.sample(addrs, max_per_seed)
        pool.extend([IPAddress(str(a)) for a in addrs])
    random.shuffle(pool)
    return pool
