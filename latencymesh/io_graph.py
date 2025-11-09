import json
import os
from typing import Any, Dict

import networkx as nx


def resolve_graph_path(path_or_base: str) -> str:
    path = os.path.expanduser(path_or_base)
    if os.path.isdir(path):
        raise IsADirectoryError(path)
    if os.path.exists(path):
        return path
    if path.endswith(".json"):
        return path
    return f"{path}.json"


def load_graph(path_or_base: str) -> nx.Graph:
    path = resolve_graph_path(path_or_base)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
        G = nx.node_link_graph(data)
        print(f"[load] loaded {len(G)} nodes from previous session")
        return G
    return nx.Graph()


def save_graph(G: nx.Graph, save_base: str) -> None:
    base = os.path.expanduser(save_base)
    if base.endswith(".json"):
        base = base[: -len(".json")]
    data: Dict[str, Any] = nx.node_link_data(G)
    json_path = f"{base}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    nx.write_gexf(G, f"{base}.gexf")
    print(f"[save] graph saved ({len(G)} nodes, {len(G.edges())} edges)")
