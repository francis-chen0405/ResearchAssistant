"""Run-owned scheduling policy and physical model capacity, independent of identity."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Condition, Event, Semaphore
from time import monotonic

import httpx

from researchassistant.providers.llm import V2CancellationRequested


@dataclass(frozen=True)
class StagePolicy:
    initial: int
    maximum: int
    expansion_seconds: float
    downstream_threshold: int | None


@dataclass(frozen=True)
class SchedulingPolicy:
    scout: StagePolicy = StagePolicy(4, 6, 25, 8)
    capture: StagePolicy = StagePolicy(4, 6, 5, 8)
    extraction: StagePolicy = StagePolicy(4, 6, 7, 10)
    analysis: StagePolicy = StagePolicy(5, 8, 13, None)
    model_capacity: int = 10
    transport_capacity: int = 6
    scout_batch_size: int = 6
    tick_seconds: float = 2
    shrink_seconds: float = 30
    provider_cooldown_seconds: float = 30


POLICY = SchedulingPolicy()


@dataclass
class StageControl:
    policy: StagePolicy
    limit: int = 0
    ready: int = 0
    running: int = 0
    busy_since: float | None = None
    low_since: float | None = None
    reason: str = "initial"

    def __post_init__(self) -> None:
        self.limit = self.policy.initial

    def update(
        self,
        *,
        ready: int,
        running: int,
        now: float,
        downstream: int = 0,
        capacity: bool = True,
        reservable: bool = True,
    ) -> int:
        self.ready, self.running = ready, running
        demand = ready + running
        qualifies = (
            running >= self.limit
            and ready >= 2
            and (
                self.policy.downstream_threshold is None
                or downstream < self.policy.downstream_threshold
            )
            and capacity
            and reservable
            and self.limit < self.policy.maximum
        )
        if qualifies:
            if self.busy_since is None:
                self.busy_since = now
            elif now - self.busy_since >= self.policy.expansion_seconds:
                self.limit += 1
                self.busy_since = None
                self.reason = "sustained_ready_work"
        else:
            self.busy_since = None
        if demand < self.limit:
            if self.low_since is None:
                self.low_since = now
            elif now - self.low_since >= POLICY.shrink_seconds:
                self.limit = min(self.limit, max(self.policy.initial, demand))
                self.low_since = None
                self.reason = "low_demand"
        else:
            self.low_since = None
        return min(demand, self.limit)


@dataclass
class ProviderControl:
    configured: int
    limit: int
    running: int = 0
    blocked_until: float = 0
    growth_after: float = 0
    successful_since: float | None = None


@dataclass(eq=False, frozen=True)
class ModelWaiter:
    stage: str
    provider: str


class RunScheduler:
    """One shared owner: decision priority, then rotating eligible model stages."""

    def __init__(
        self,
        cancelled: Callable[[], bool] | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.clock = clock
        self.cancelled = cancelled
        self.condition = Condition()
        self.stopped = Event()
        self.changed = Event()
        self.wake_callbacks: list[Callable[[], None]] = []
        self.stages = {
            name: StageControl(getattr(POLICY, name))
            for name in ("scout", "capture", "extraction", "analysis")
        }
        self.providers: dict[str, ProviderControl] = {}
        self.waiters: list[ModelWaiter] = []
        self.rotation: deque[str] = deque()
        self.model_running = 0
        self.physical_running = 0
        self.physical_stages: dict[str, int] = {}
        self.transport_running = 0
        self.transport_slots = TransportSlots(self._transport_changed)

    @contextmanager
    def stage_scope(self, *names: str) -> Iterator[None]:
        """Retire stage demand after inner executors and durable writes have drained."""
        try:
            yield
        finally:
            for name in names:
                self.update_stage(name, ready=0, running=0)

    def notify(self) -> None:
        with self.condition:
            self.changed.set()
            self.condition.notify_all()
            for callback in self.wake_callbacks:
                callback()

    def wait_for_change(self) -> None:
        self.changed.wait(timeout=POLICY.tick_seconds)
        self.changed.clear()
        self.check_cancelled()

    def add_wake(self, callback: Callable[[], None]) -> None:
        with self.condition:
            self.wake_callbacks.append(callback)

    def remove_wake(self, callback: Callable[[], None]) -> None:
        with self.condition:
            self.wake_callbacks.remove(callback)

    def _transport_changed(self, delta: int) -> None:
        with self.condition:
            self.transport_running += delta
            self.notify()

    def check_cancelled(self) -> None:
        if self.stopped.is_set() or (self.cancelled is not None and self.cancelled()):
            raise V2CancellationRequested("cancelled while waiting for run capacity")

    def stop_admission(self) -> None:
        self.stopped.set()
        with self.condition:
            self.notify()

    def provider(self, key: str, configured: int = POLICY.model_capacity) -> ProviderControl:
        return self.providers.setdefault(key, ProviderControl(configured, configured))

    def capacity_available(self, key: str) -> bool:
        with self.condition:
            control = self.provider(key)
            return (
                self.clock() >= max(control.blocked_until, control.growth_after)
                and control.running < control.limit
                and self.model_running < POLICY.model_capacity
            )

    def update_stage(
        self,
        name: str,
        *,
        ready: int,
        running: int,
        downstream: int = 0,
        capacity: bool = True,
        reservable: bool = True,
    ) -> int:
        with self.condition:
            physical_stage = {"extraction": "extractor", "analysis": "analyst"}.get(name, name)
            waiting = sum(item.stage == physical_stage for item in self.waiters)
            ready += waiting
            running = max(0, running - waiting)
            control = self.stages[name]
            before = (control.ready, control.running, control.limit)
            target = control.update(
                ready=ready,
                running=running,
                now=self.clock(),
                downstream=downstream,
                capacity=capacity,
                reservable=reservable,
            )
            if before != (control.ready, control.running, control.limit):
                self.notify()
            return target

    def model_waiting(self, stage: str) -> int:
        """Capacity waiters are downstream demand, even inside admitted source tasks."""
        with self.condition:
            return sum(waiter.stage == stage for waiter in self.waiters)

    def _eligible(self, waiter: ModelWaiter) -> bool:
        control = self.provider(waiter.provider)
        return self.clock() >= control.blocked_until and control.running < control.limit

    def _next(self) -> ModelWaiter | None:
        if self.model_running >= POLICY.model_capacity:
            return None
        eligible = [waiter for waiter in self.waiters if self._eligible(waiter)]
        decisions = [item for item in eligible if item.stage in {"planner", "gap_analysis"}]
        if decisions:
            return decisions[0]
        for stage in self.rotation:
            for waiter in eligible:
                if waiter.stage == stage:
                    return waiter
        return None

    @contextmanager
    def model_slot(self, stage: str, key: str) -> Iterator[Callable[[], None]]:
        waiter = ModelWaiter(stage, key)
        with self.condition:
            self.waiters.append(waiter)
            self.notify()
            if stage not in self.rotation:
                self.rotation.append(stage)
            try:
                while True:
                    self.check_cancelled()
                    if self._next() is waiter:
                        self.waiters.remove(waiter)
                        self.model_running += 1
                        self.provider(key).running += 1
                        while self.rotation[0] != stage:
                            self.rotation.rotate(-1)
                        self.rotation.rotate(-1)
                        break
                    self.condition.wait(timeout=0.1)
            except BaseException:
                self.waiters.remove(waiter)
                self.notify()
                raise
        released = False

        def release() -> None:
            nonlocal released
            with self.condition:
                if not released:
                    released = True
                    self.model_running -= 1
                    self.provider(key).running -= 1
                    self.notify()

        try:
            yield release
        finally:
            release()

    @contextmanager
    def physical_request(self, stage: str) -> Iterator[None]:
        with self.condition:
            self.physical_running += 1
            self.physical_stages[stage] = self.physical_stages.get(stage, 0) + 1
        try:
            yield
        finally:
            with self.condition:
                self.physical_running -= 1
                self.physical_stages[stage] -= 1
                self.notify()

    @contextmanager
    def service_slot(self, key: str, park: Callable[[], None]) -> Iterator[None]:
        """Capture services have provider capacity, separate from model requests."""
        with self.condition:
            control = self.provider(key, POLICY.transport_capacity)
            while True:
                self.check_cancelled()
                if self.clock() >= control.blocked_until and control.running < control.limit:
                    control.running += 1
                    break
                park()
                self.condition.wait(timeout=0.1)
        try:
            yield
        finally:
            with self.condition:
                control.running -= 1
                self.notify()

    def capture_growth_available(self) -> bool:
        with self.condition:
            return all(
                self.clock() >= max(control.blocked_until, control.growth_after)
                for key, control in self.providers.items()
                if key.startswith("capture:")
            )

    def overload(self, key: str, retry_after: float = 0) -> None:
        with self.condition:
            control = self.provider(key)
            now = self.clock()
            control.limit = max(1, control.limit // 2)
            control.blocked_until = max(
                control.blocked_until, now + max(POLICY.provider_cooldown_seconds, retry_after)
            )
            control.growth_after = now + POLICY.provider_cooldown_seconds
            control.successful_since = None
            self.notify()

    def success(self, key: str) -> None:
        with self.condition:
            control = self.provider(key)
            now = self.clock()
            if now < max(control.growth_after, control.blocked_until):
                return
            if control.successful_since is None:
                control.successful_since = now
            elif now - control.successful_since >= POLICY.provider_cooldown_seconds:
                control.limit = min(control.configured, control.limit + 1)
                control.successful_since = now
            self.notify()

    def failure(self, key: str) -> None:
        with self.condition:
            self.provider(key).successful_since = None

    def snapshot(self) -> dict[str, object]:
        with self.condition:
            return {
                "admission_closed": self.stopped.is_set(),
                "model_running": self.physical_running,
                "model_admitted": self.model_running,
                "model_waiting": len(self.waiters),
                "physical_stages": dict(self.physical_stages),
                "transport_running": self.transport_running,
                "stages": {
                    name: {
                        "ready": value.ready,
                        "running": value.running,
                        "limit": value.limit,
                        "reason": value.reason,
                    }
                    for name, value in self.stages.items()
                },
                "providers": {
                    key: {
                        "running": value.running,
                        "limit": value.limit,
                        "backoff": self.clock() < max(value.blocked_until, value.growth_after),
                    }
                    for key, value in self.providers.items()
                },
            }


class TransportSlots(Semaphore):
    """Shared transport ceiling with actual leases, not parked capture tasks."""

    def __init__(self, changed: Callable[[int], None]) -> None:
        super().__init__(POLICY.transport_capacity)
        self.changed = changed

    def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        acquired = super().acquire(blocking=blocking, timeout=timeout)
        if acquired:
            self.changed(1)
        return acquired

    def release(self, n: int = 1) -> None:
        self.changed(-n)
        super().release(n)


def retry_after_delay(value: str | None) -> float | None:
    """Parse a server delay; use monotonic deadlines after conversion at receipt."""
    import math
    from datetime import UTC, datetime
    from email.utils import parsedate_to_datetime

    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def explicit_overload_response(response: httpx.Response) -> bool:
    if response.status_code in {429, 529}:
        return True
    try:
        body = response.json()
    except (ValueError, UnicodeError):
        return False
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return False
    return any(
        error.get(key)
        in {
            "overloaded",
            "overloaded_error",
            "server_overloaded",
            "server_overload",
            "rate_limit_exceeded",
            "rate_limit_error",
            "RESOURCE_EXHAUSTED",
        }
        for key in ("code", "type", "status")
        if isinstance(error.get(key), str)
    )
