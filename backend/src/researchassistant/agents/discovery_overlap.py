"""Join the durable first-page handoff with the completed search round."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from queue import SimpleQueue
from threading import Event
from typing import TypeVar

from researchassistant.agents.v2_discovery import (
    ScoutHandoff,
    V2DiscoveryResponse,
    V2DiscoveryScoutRunResult,
)

_SearchResult = TypeVar("_SearchResult")
DiscoveryResponses = tuple[V2DiscoveryResponse, ...]
FirstPass = Callable[[DiscoveryResponses], None]
ScoutSearchPool = Callable[
    [
        DiscoveryResponses,
        ScoutHandoff | None,
        Callable[[], bool],
        bool,
        V2DiscoveryScoutRunResult | None,
    ],
    V2DiscoveryScoutRunResult,
]


def scout_during_search(
    *,
    execute: Callable[[FirstPass | None, Callable[[], bool]], _SearchResult],
    responses: Callable[[_SearchResult], DiscoveryResponses],
    scout: ScoutSearchPool,
    on_batch: ScoutHandoff | None,
    cancelled: Callable[[], bool],
    progressive: bool,
) -> tuple[_SearchResult, V2DiscoveryScoutRunResult]:
    if not progressive:
        search = execute(None, cancelled)
        return search, scout(responses(search), on_batch, cancelled, False, None)

    received: SimpleQueue[DiscoveryResponses | None] = SimpleQueue()
    stop = Event()

    def stopped() -> bool:
        return stop.is_set() or cancelled()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="deeper-search") as worker:
        search_work = worker.submit(copy_context().run, execute, received.put, stopped)
        search_work.add_done_callback(lambda _future: received.put(None))
        try:
            first = received.get()
            prefix = scout(first, on_batch, stopped, True, None) if first else None
            if (
                prefix is not None
                and prefix.resumed
                and prefix.ranking_artifact is not None
                and on_batch is not None
            ):
                on_batch(prefix.output, prefix.ranking_artifact, (), True)
            search = search_work.result()
            return search, scout(responses(search), on_batch, stopped, False, prefix)
        finally:
            stop.set()
