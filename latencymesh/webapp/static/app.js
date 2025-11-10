const svg = d3.select("#graph");
const [, , viewWidth, viewHeight] = svg
  .attr("viewBox")
  .split(" ")
  .map(Number);

const linkLayer = svg.append("g").attr("class", "links");
const nodeLayer = svg.append("g").attr("class", "nodes");

const simulation = d3
  .forceSimulation()
  .force(
    "link",
    d3
      .forceLink()
      .id((d) => d.id)
      .distance(80)
      .strength(0.1)
  )
  .force("charge", d3.forceManyBody().strength(-60))
  .force("center", d3.forceCenter(viewWidth / 2, viewHeight / 2))
  .force(
    "collide",
    d3
      .forceCollide()
      .radius((d) => 12)
      .iterations(2)
  );

function updateStats(snapshot) {
  const nodes = snapshot.nodes.length;
  const edges = snapshot.links.length;
  const avgDegree = nodes > 0 ? (edges * 2) / nodes : 0;
  const latencies = snapshot.nodes
    .map((node) => Number.parseFloat(node.rtt))
    .filter((value) => Number.isFinite(value));
  const avgLatency =
    latencies.length > 0
      ? latencies.reduce((sum, value) => sum + value, 0) / latencies.length
      : 0;

  document.querySelector("#stat-nodes").textContent = nodes;
  document.querySelector("#stat-edges").textContent = edges;
  document.querySelector("#stat-degree").textContent = avgDegree.toFixed(2);
  document.querySelector("#stat-latency").textContent = `${avgLatency.toFixed(
    1
  )} ms`;
  document.querySelector("#stat-updated").textContent = new Date(
    snapshot.generated_at
  ).toLocaleTimeString();
}

function renderGraph(snapshot) {
  updateStats(snapshot);

  const linkSelection = linkLayer
    .selectAll("line")
    .data(snapshot.links, (d) => `${d.source}-${d.target}`);

  const linkEnter = linkSelection
    .enter()
    .append("line")
    .attr("stroke", "#4dd0e1")
    .attr("stroke-opacity", 0.35)
    .attr("stroke-width", 1.5);

  linkSelection.exit().remove();

  const nodeSelection = nodeLayer
    .selectAll("circle")
    .data(snapshot.nodes, (d) => d.id);

  const nodeEnter = nodeSelection
    .enter()
    .append("circle")
    .attr("r", 5)
    .attr("fill", "#ffca28")
    .attr("stroke", "#263238")
    .attr("stroke-width", 1.5)
    .call(
      d3
        .drag()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
    );

  nodeEnter.append("title").text((d) => `${d.id}${d.rtt ? `\n${d.rtt} ms` : ""}`);

  nodeSelection.exit().remove();

  const mergedNodes = nodeEnter.merge(nodeSelection);
  const mergedLinks = linkEnter.merge(linkSelection);

  simulation.nodes(snapshot.nodes).on("tick", () => {
    mergedLinks
      .attr("x1", (d) => d.source.x)
      .attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x)
      .attr("y2", (d) => d.target.y);

    mergedNodes.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
  });

  simulation.force("link").links(snapshot.links);
  simulation.alpha(0.9).restart();
}

async function fetchInitialGraph() {
  try {
    const response = await fetch("/api/graph");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const snapshot = await response.json();
    renderGraph(snapshot);
  } catch (error) {
    console.error("Failed to load initial graph", error);
  }
}

function connectStream() {
  const source = new EventSource("/api/stream");

  source.onmessage = (event) => {
    try {
      const snapshot = JSON.parse(event.data);
      renderGraph(snapshot);
    } catch (error) {
      console.error("Failed to parse snapshot", error);
    }
  };

  source.addEventListener("shutdown", () => {
    source.close();
  });

  source.onerror = () => {
    source.close();
    setTimeout(connectStream, 3000);
  };
}

fetchInitialGraph().then(connectStream);
