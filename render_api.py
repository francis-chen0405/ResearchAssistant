"""Render entry point for the free staging FastAPI service."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI

from frontend.hosted_api import create_hosted_app
from hosted_worker import build_worker, run_worker_loop


@asynccontextmanager
async def embedded_worker_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run the durable hosted worker beside the API on a single free web instance."""
    if os.environ.get("HOSTED_EMBEDDED_WORKER", "").casefold() != "true":
        yield
        return
    stop_event = Event()
    worker = build_worker()
    worker_thread = Thread(
        target=run_worker_loop,
        kwargs={"worker": worker, "stop_event": stop_event},
        name="hosted-embedded-worker",
        daemon=True,
    )
    worker_thread.start()
    try:
        yield
    finally:
        stop_event.set()
        worker_thread.join(timeout=15)


app = create_hosted_app(lifespan=embedded_worker_lifespan)
