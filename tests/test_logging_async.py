import asyncio
import logging

import pytest

from latencymesh.logging_async import AsyncQueueHandler, get_logger, log_worker


def test_async_queue_handler_and_worker():
    async def runner():
        queue: asyncio.Queue = asyncio.Queue()
        stop_event = asyncio.Event()

        handler = AsyncQueueHandler(queue)
        logger = logging.getLogger("test_async")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        task = asyncio.create_task(log_worker(queue, stop_event, level=logging.DEBUG))
        logger.info("hello world")

        # Allow the worker to process the message.
        await asyncio.sleep(0.1)
        stop_event.set()
        await queue.join()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(runner())


def test_get_logger_reuses_handler():
    queue: asyncio.Queue = asyncio.Queue()
    logger = get_logger(queue)
    logger.info("message")
    # Requesting the same logger should not add duplicate handlers.
    logger_again = get_logger(queue)
    assert logger_again.handlers == logger.handlers


def test_log_worker_timeout_cycle():
    async def runner():
        queue: asyncio.Queue = asyncio.Queue()
        stop_event = asyncio.Event()
        task = asyncio.create_task(log_worker(queue, stop_event))
        await asyncio.sleep(0.6)
        stop_event.set()
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(runner())
