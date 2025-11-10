import asyncio, random, re, ipaddress
from .graph_ops import add_trace


async def run_traceroute(host, timeout, max_hops, logger):
    cmd = [
        "traceroute",
        "-n",
        "-q",
        "1",
        "-w",
        str(timeout),
        "-m",
        str(max_hops),
        str(host),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    hops = []
    assert proc.stdout
    async for raw in proc.stdout:
        m = re.match(r"\s*\d+\s+(\S+)\s+([\d\.]+)\s+ms", raw.decode().strip())
        if m:
            ip, latency = m.groups()
            if ip == "*":
                continue
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                continue
            logger.debug(f"[trace:{host}] {ip} {latency}ms")
            hops.append((ip, float(latency)))
    await proc.wait()
    return hops


async def traceroute_worker(
    worker_id,
    G,
    queue,
    params,
    seen_ips,
    pending_ips,
    stop_event,
    success_counter,
    counter_lock,
    logger,
):
    pps = max(0.001, float(params.pps))
    delay_between = 1.0 / pps
    while not stop_event.is_set():
        try:
            host = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        if host is None:
            queue.task_done()
            break
        try:
            hops = await run_traceroute(host, params.timeout, params.max_hops, logger)
        except Exception as e:
            logger.warning(f"[worker-{worker_id}] traceroute error {host}: {e}")
            queue.task_done()
            await asyncio.sleep(delay_between)
            continue
        if hops:
            add_trace(G, hops)
            total_now = None
            async with counter_lock:
                success_counter["since_last_draw"] = (
                    success_counter.get("since_last_draw", 0) + 1
                )
                if "total" in success_counter:
                    success_counter["total"] = success_counter.get("total", 0) + 1
                    total_now = success_counter["total"]
            if total_now is not None:
                limit = getattr(params, "max_traces", None)
                if limit is not None and limit > 0 and total_now >= limit:
                    stop_event.set()
            if "notify" in success_counter:
                success_counter["notify"]()
            for ip, _ in hops:
                if ip not in seen_ips:
                    seen_ips.add(ip)
                    if ip not in pending_ips:
                        await queue.put(ip)
                        pending_ips.add(ip)
                elif ip not in pending_ips and random.random() < 0.02:
                    await queue.put(ip)
                    pending_ips.add(ip)
        pending_ips.discard(host)
        queue.task_done()
        await asyncio.sleep(delay_between * (0.8 + 0.4 * random.random()))
