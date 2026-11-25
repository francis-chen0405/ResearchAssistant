"""Thread-local durable-intent handoff to physical dispatch, outside saved identity."""

from collections.abc import Callable
from contextvars import ContextVar

_PENDING: ContextVar[Callable[[], None] | None] = ContextVar(
    "physical_dispatch_intent", default=None
)


def defer_intent(provider: object, write: Callable[[], None]) -> None:
    if getattr(provider, "defers_dispatch_intents", False):
        if _PENDING.get() is not None:
            raise RuntimeError("a physical dispatch already owns an unwritten intent")
        _PENDING.set(write)
    else:
        write()


def commit_intent() -> None:
    write = _PENDING.get()
    _PENDING.set(None)
    if write is not None:
        write()


def clear_intent() -> None:
    _PENDING.set(None)
