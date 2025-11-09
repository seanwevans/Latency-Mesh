import matplotlib.pyplot as plt, networkx as nx
from datetime import datetime
from .graph_ops import compute_positions


def draw_map(G, save_base, ax):
    pos = compute_positions(G)
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
    plt.savefig(f"{save_base}.svg", format="svg")
    plt.pause(0.001)
