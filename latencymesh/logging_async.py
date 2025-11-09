import asyncio, logging, sys


class AsyncQueueHandler(logging.Handler):
    """Non-blocking async-safe handler that enqueues records."""

    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.queue.put_nowait((record.levelno, msg))
        except Exception:
            self.handleError(record)


async def log_worker(
    queue: asyncio.Queue, stop_event: asyncio.Event, level=logging.INFO
) -> None:
    base_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s> %(message)s", "%H:%M:%S"
    )
    base_handler.setFormatter(formatter)
    logger = logging.getLogger("async_logger")
    logger.setLevel(level)
    logger.addHandler(base_handler)

    while not stop_event.is_set() or not queue.empty():
        try:
            lvl, msg = await asyncio.wait_for(queue.get(), timeout=0.5)
            record = logging.LogRecord("async_logger", lvl, "", 0, msg, None, None)
            base_handler.emit(record)
            queue.task_done()
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            sys.stderr.write(f"[log_worker error] {e}\n")

    base_handler.flush()


def get_logger(queue: asyncio.Queue, name: str = "LatencyMesh") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = AsyncQueueHandler(queue)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
