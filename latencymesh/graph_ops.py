import math, networkx as nx
from typing import Dict, Tuple
from .iptools import IPAddress, ip_angle

Hop = Tuple[IPAddress, float]
Position = Dict[IPAddress, Tuple[float, float]]


def add_trace(G: nx.Graph, hops: list[Hop]) -> None:
    for i, (ip, rtt) in enumerate(hops):
        if not G.has_node(ip):
            G.add_node(ip, rtt=rtt)
        else:
            G.nodes[ip]["rtt"] = min(G.nodes[ip].get("rtt", rtt), rtt)
        if i > 0:
            prev_ip, prev_rtt = hops[i - 1]
            delta = max(rtt - prev_rtt, 0.1)
            if not G.has_edge(prev_ip, ip):
                G.add_edge(prev_ip, ip, weight=delta)


def compute_positions(G: nx.Graph) -> Position:
    pos: Position = {}
    for node, data in G.nodes(data=True):
        r = float(data.get("rtt", 1))
        θ = ip_angle(IPAddress(node))
        pos[IPAddress(node)] = (r * math.cos(θ), r * math.sin(θ))
    return pos
