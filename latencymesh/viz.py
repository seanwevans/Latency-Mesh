from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
import networkx as nx

from .graph_ops import compute_positions


def _layout_positions(G: nx.Graph, layout: str):
    if layout == "spring":
        return nx.spring_layout(G, seed=42)
    if layout == "planar":
        try:
            return nx.planar_layout(G)
        except nx.NetworkXException:
            return nx.spring_layout(G, seed=42)
    return compute_positions(G)


def draw_map(G, save_base, ax, *, layout: str = "radial", output_path: Optional[str] = None):
    pos = _layout_positions(G, layout)
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 8))
    ax.clear()
    ax.set_title("LatencyMesh (Live)")
    ax.axis("equal")
    ax.axis("off")
    nx.draw_networkx_edges(G, pos, alpha=0.3, width=0.4, ax=ax)
    nx.draw_networkx_nodes(G, pos, node_size=8, ax=ax)
    ax.scatter(0, 0, s=60, c="red", marker="x")
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    ax.text(
        0.02,
        0.02,
        f"{len(G.nodes())} nodes\n{ts}",
        transform=ax.transAxes,
        fontsize=8,
        ha="left",
        va="bottom",
    )
    plt.tight_layout()
    target = output_path or (f"{save_base}.svg" if save_base else None)
    if target:
        plt.savefig(target)
    plt.pause(0.001)
