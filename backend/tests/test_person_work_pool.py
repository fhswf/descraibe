from __future__ import annotations

import threading
import time

import pytest

from backend.pipeline.persons import work_pool


def test_map_bounded_preserves_input_order_and_caps_active_work():
    lock = threading.Lock()
    active = 0
    peak = 0

    def work(value):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep((8 - value) * 0.002)
        with lock:
            active -= 1
        return value * 2

    assert work_pool.map_bounded(range(9), work) == [value * 2 for value in range(9)]
    assert peak <= work_pool.worker_count()
    assert peak <= work_pool.MAX_WORKERS + work_pool.MAX_OUTSTANDING


def test_map_bounded_can_stream_results_without_retaining_them():
    seen = []
    result = work_pool.map_bounded(
        range(12), lambda value: value * 3,
        on_result=lambda item, value: seen.append((item, value)),
        collect_results=False,
    )
    assert result == []
    assert sorted(seen) == [(value, value * 3) for value in range(12)]


def test_map_bounded_waits_for_running_tasks_before_raising():
    lock = threading.Lock()
    active = 0

    def work(value):
        nonlocal active
        with lock:
            active += 1
        try:
            if value == 0:
                raise ValueError("controlled failure")
            time.sleep(0.01)
            return value
        finally:
            with lock:
                active -= 1

    with pytest.raises(ValueError, match="controlled failure"):
        work_pool.map_bounded(range(40), work)
    assert active == 0


def test_stage_coordinator_queue_is_bounded():
    release = threading.Event()
    futures = []
    capacity = work_pool.STAGE_WORKERS + work_pool.STAGE_PENDING
    try:
        for _ in range(capacity):
            future = work_pool.submit_stage(lambda: release.wait(timeout=2))
            assert future is not None
            futures.append(future)
        assert work_pool.submit_stage(lambda: None) is None
    finally:
        release.set()
        for future in futures:
            future.result(timeout=3)


def test_progress_payload_keeps_legacy_fields_and_adds_worker_details():
    from backend.app import _progress_payload

    payload = _progress_payload("tracking", "Scene 2", 12, 20, {
        "phase": "scenes",
        "run_id": "run-1",
        "workers": {"queued": 1, "running": 2, "completed": 3, "failed": 0},
    })
    assert payload["step"] == "tracking"
    assert payload["current"] == 12 and payload["total"] == 20
    assert payload["schema_version"] == 2
    assert payload["phase"] == "scenes"
    assert payload["workers"]["running"] == 2
