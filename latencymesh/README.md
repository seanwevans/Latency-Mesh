# 🕸️ LatencyMesh (`lm`)

**LatencyMesh** continuously performs asynchronous traceroutes to map the topology of your surrounding Internet in real time.  
It constructs a **weighted mesh** where each edge corresponds to a hop and its latency.  
Over time, it reveals the structure of your network neighborhood.

---

## ✨ Features

- 🧠 **Async multi-worker engine** — hundreds of concurrent traceroutes with asyncio.  
- 🕹️ **Live visualization** — redraw in real-time or after N successful traces.  
- 🧩 **Configurable scope** — map local /16s, ISP backbones, or public DNS infrastructure.  
- 💾 **Persistent graphs** — automatically save `.json` (NetworkX) and `.gexf` (Gephi) files.  
- 🧭 **Graceful shutdown** — single `Ctrl+C` exits cleanly and saves state.
- ⚙️ **CLI-first design** — `lm` behaves like a normal UNIX tool.

---

## 🚀 Quickstart

### Installation

```bash
git clone https://github.com/seanwevans/latencymesh.git
cd latencymesh
pip install -e .
```

### Basic Mapping

Map your local network or a known public subnet:

```bash
lm map --prefix 192.168.1.0/16 --workers 8
```

or explore global DNS nodes:

```bash
lm map 1.1.1.1 8.8.8.8 9.9.9.9 --prefix 16
```

Run headless (no display window):

```bash
lm map --no-display --prefix 8.8.0.0/16
```

Control concurrency and rate:

```bash
lm map --workers 16 --pps 2.5
```

---

## 🧭 Command Reference

### 🗺️ `lm map`

Continuously traceroutes all addresses within a prefix or seed list, building a weighted mesh.

```bash
lm map [OPTIONS] [SEEDS...]
```

**Options:**

| Flag | Description |
|------|--------------|
| `--prefix <N>` | Expand each seed IP to a `/N` network (default `/16`) |
| `--max-per-seed <N>` | Limit sampled IPs per seed (default 4096) |
| `--workers <N>` | Number of concurrent traceroute workers |
| `--pps <FLOAT>` | Rate limit: traceroutes per second per worker |
| `--timeout <FLOAT>` | Per-hop timeout in seconds |
| `--max-hops <N>` | Maximum hops per traceroute (default 30) |
| `--save-base <PATH>` | Base name for output files (default `internet_map`) |
| `--no-display` | Run headless (no live plot) |
| `--update-mode <fixed|dynamic>` | Redraw mode: `fixed` interval or after `N` successful traces |
| `--update-interval <S>` | Seconds between redraws (fixed mode) |
| `--update-count <N>` | Redraw after N traceroutes (dynamic mode) |

---

### ⚡ `lm init`

Initialize a workspace with configuration, seeds, and directories.

```bash
lm init
```

Creates:

```
latencymesh/
├── data/
├── logs/
├── results/
└── config.yaml
```

---

### 🔭 `lm serve`

Launch a lightweight web dashboard to view the evolving mesh in real time.

```bash
lm serve --port 8080
```

Displays interactive latency map (requires `latencymesh[web]` optional extras).

---

### 🧩 `lm merge`

Merge multiple `.json` graph dumps into a unified mesh.

```bash
lm merge results/*.json -o merged.json
```

---

### 🧠 `lm replay`

Replay a previous session’s `.json` file and render as a time-lapse.

```bash
lm replay internet_map.json
```

---

## 🕹️ Example Workflows

Map your Wi-Fi network:
```bash
lm map --prefix 192.168.1.0/24 --workers 4
```

Map everything between your ISP and Google:
```bash
lm map 8.8.8.8 --max-hops 20 --workers 2
```

Automate hourly snapshots:
```bash
watch -n 3600 "lm map --no-display --update-count 100 --save-base results/lm_$(date +%H%M)"
```

Merge and visualize:
```bash
lm merge results/*.json -o all_time.json
lm replay all_time.json
```
