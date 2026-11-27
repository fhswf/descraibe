"""Bounded, process-local worker resources for person-analysis stages."""
from __future__ import annotations

import os
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def _positive_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer.") from exc
    if parsed < 1:
        raise RuntimeError(f"{name} must be a positive integer.")
    return parsed


# Keep concurrency opt-in until representative deployment benchmarks confirm
# the memory and throughput trade-off for each configured model stack.
_DEFAULT_WORKERS = 1
MAX_WORKERS = _positive_env("AD_PERSON_CPU_WORKERS", _DEFAULT_WORKERS)
MAX_OUTSTANDING = _positive_env("AD_PERSON_MAX_PENDING", MAX_WORKERS * 2)
RFDETR_BATCH_SIZE = _positive_env("AD_PERSON_RFDETR_BATCH_SIZE", 8)
if RFDETR_BATCH_SIZE > 16:
    raise RuntimeError("AD_PERSON_RFDETR_BATCH_SIZE must be between 1 and 16.")
MODEL_SLOTS = _positive_env("AD_PERSON_MODEL_SLOTS", 1)
STAGE_WORKERS = _positive_env("AD_PERSON_STAGE_WORKERS", 2)
STAGE_PENDING = _positive_env("AD_PERSON_STAGE_PENDING", 4)

_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="person-task")
_stage_executor = ThreadPoolExecutor(max_workers=STAGE_WORKERS, thread_name_prefix="person-stage")
_outstanding = threading.BoundedSemaphore(MAX_WORKERS + MAX_OUTSTANDING)
_stage_admission = threading.BoundedSemaphore(STAGE_WORKERS + STAGE_PENDING)
_model_slots = threading.BoundedSemaphore(MODEL_SLOTS)


class WorkCancelled(Exception):
    """Raised when a person-analysis stage is cancelled before publication."""


class CancellationToken:
    """Cooperative cancellation with a one-way transition into publication."""

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._commit_started = False

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def commit_started(self) -> bool:
        with self._lock:
            return self._commit_started

    def request_cancel(self) -> bool:
        """Request cancellation, returning false once publication has begun."""
        with self._lock:
            if self._commit_started:
                return False
            self._event.set()
            return True

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise WorkCancelled("Personenschritt wurde abgebrochen.")

    def begin_commit(self) -> None:
        """Atomically close the cancellation window before writing final state."""
        with self._lock:
            if self._event.is_set():
                raise WorkCancelled("Personenschritt wurde abgebrochen.")
            self._commit_started = True


def worker_count() -> int:
    return MAX_WORKERS


def submit_stage(function: Callable[[], R]) -> Future[R] | None:
    """Submit a stage coordinator without allowing an unbounded stage queue."""
    if not _stage_admission.acquire(blocking=False):
        return None
    try:
        future = _stage_executor.submit(function)
    except BaseException:
        _stage_admission.release()
        raise
    future.add_done_callback(lambda _future: _stage_admission.release())
    return future


@contextmanager
def model_slot(cancel_token: CancellationToken | None = None):
    """Limit concurrently loaded person-analysis model sets across jobs."""
    acquired = False
    while not acquired:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        acquired = _model_slots.acquire(timeout=0.1)
    try:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        yield
    finally:
        _model_slots.release()


def _notify(callback, event: str, item) -> None:
    if callback is None:
        return
    try:
        callback(event, item)
    except Exception:
        # Progress accounting must not turn a successful unit of work into a
        # failed stage.
        return


def map_bounded(
    items: Iterable[T],
    function: Callable[[T], R],
    *,
    on_task_event: Callable[[str, T], None] | None = None,
    on_result: Callable[[T, R], None] | None = None,
    collect_results: bool = True,
    cancel_token: CancellationToken | None = None,
) -> list[R]:
    """Map an iterable with a globally bounded number of submitted tasks.

    Results are returned in input order even though work completes out of
    order. At most ``MAX_WORKERS + MAX_OUTSTANDING`` futures from all person
    stages can exist at once. A failure stops new submissions, cancels queued
    work, and waits for already-running tasks before the caller cleans staging
    files.
    """
    iterator = iter(items)
    pending: dict[Future, tuple[int, T]] = {}
    results: dict[int, R] = {}
    next_index = 0
    exhausted = False
    first_error: BaseException | None = None

    def invoke(item: T) -> R:
        if cancel_token is not None and cancel_token.cancelled:
            _notify(on_task_event, "cancelled", item)
            raise WorkCancelled("Personenschritt wurde abgebrochen.")
        _notify(on_task_event, "started", item)
        try:
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            result = function(item)
        except WorkCancelled:
            _notify(on_task_event, "cancelled_running", item)
            raise
        except BaseException:
            _notify(on_task_event, "failed", item)
            raise
        _notify(on_task_event, "completed", item)
        return result

    def submit_available() -> None:
        nonlocal next_index, exhausted
        while not exhausted and len(pending) < MAX_WORKERS + MAX_OUTSTANDING:
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            try:
                item = next(iterator)
            except StopIteration:
                exhausted = True
                return
            while not _outstanding.acquire(timeout=0.1):
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
            if cancel_token is not None and cancel_token.cancelled:
                _outstanding.release()
                cancel_token.raise_if_cancelled()
            _notify(on_task_event, "queued", item)
            try:
                future = _executor.submit(invoke, item)
            except BaseException:
                _outstanding.release()
                _notify(on_task_event, "failed", item)
                raise
            future.add_done_callback(lambda _future: _outstanding.release())
            pending[future] = (next_index, item)
            next_index += 1

    def cancel_pending() -> None:
        for future, (_index, item) in pending.items():
            if future.cancel():
                _notify(on_task_event, "cancelled", item)
        if pending:
            wait(pending)

    try:
        submit_available()
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                index, item = pending.pop(future)
                try:
                    result = future.result()
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
                else:
                    if collect_results:
                        results[index] = result
                    if on_result is not None:
                        on_result(item, result)

            if first_error is not None:
                cancel_pending()
                raise first_error
            submit_available()
    except BaseException:
        cancel_pending()
        raise

    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    return [results[index] for index in range(next_index)] if collect_results else []


def report_progress(progress_cb, message: str, current=None, total=None, details: dict | None = None) -> None:
    """Send structured progress when supported, preserving the legacy callback."""
    if progress_cb is None:
        return
    structured = getattr(progress_cb, "with_details", None)
    if details is not None and callable(structured):
        structured(message, current, total, details)
    else:
        progress_cb(message, current, total)
