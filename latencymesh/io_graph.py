import json, os, networkx as nx
from typing import Any, Dict


def load_graph(save_base: str) -> nx.Graph:
    if os.path.exists(f"{save_base}.json"):
        with open(f"{save_base}.json", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
        G = nx.node_link_graph(data)
        print(f"[load] loaded {len(G)} nodes from previous session")
        return G
    return nx.Graph()


def save_graph(G: nx.Graph, save_base: str) -> None:
    data: Dict[str, Any] = nx.node_link_data(G)
    with open(f"{save_base}.json", "w", encoding="utf-8") as f:
        json.dump(data, f)
    nx.write_gexf(G, f"{save_base}.gexf")
    print(f"[save] graph saved ({len(G)} nodes, {len(G.edges())} edges)")
