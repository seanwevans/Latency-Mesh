import asyncio
import io
import logging

import pytest

import latencymesh.logging_async as logging_async_mod
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


def test_async_queue_handler_handles_format_errors():
    queue: asyncio.Queue = asyncio.Queue()
    handler = AsyncQueueHandler(queue)

    record = logging.LogRecord("test", logging.INFO, __file__, 0, "message", None, None)
    captured: list[logging.LogRecord] = []

    handler.handleError = lambda r: captured.append(r)  # type: ignore[assignment]

    def broken_format(_record):
        raise RuntimeError("format failure")

    handler.format = broken_format  # type: ignore[assignment]
    handler.emit(record)

    assert captured == [record]
    assert queue.empty()


def test_log_worker_reports_errors_and_flushes(monkeypatch):
    async def runner():
        queue: asyncio.Queue = asyncio.Queue()
        stop_event = asyncio.Event()

        await queue.put((logging.INFO, "first"))
        await queue.put((logging.INFO, "second"))

        original_cls = logging.StreamHandler

        class InstrumentedHandler(original_cls):
            def __init__(self, stream=None):
                super().__init__(stream)
                self.emit_calls = 0
                self.flush_called = False

            def emit(self, record):  # type: ignore[override]
                self.emit_calls += 1
                if self.emit_calls == 1:
                    raise RuntimeError("emit failure")
                super().emit(record)

            def flush(self):  # type: ignore[override]
                self.flush_called = True
                super().flush()

        handlers: list[InstrumentedHandler] = []

        def fake_stream_handler(stream):
            handler = InstrumentedHandler(stream)
            handlers.append(handler)
            return handler

        monkeypatch.setattr(
            logging_async_mod.logging, "StreamHandler", fake_stream_handler
        )

        stderr_buffer = io.StringIO()
        monkeypatch.setattr(logging_async_mod.sys, "stderr", stderr_buffer)

        worker = asyncio.create_task(logging_async_mod.log_worker(queue, stop_event))

        # Allow the worker to process queued messages, including the failure path.
        await asyncio.sleep(0.1)
        stop_event.set()
        await worker

        assert "log_worker error" in stderr_buffer.getvalue()
        assert handlers and handlers[0].flush_called

    asyncio.run(runner())
