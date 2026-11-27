"""Low-overhead queue, stage, and optional GPU metrics for person tracking."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TrackingTelemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queued_frames = 0
        self._peak_queued_frames = 0
        self._decoded_frames = 0
        self._decode_seconds = 0.0
        self._detector_preprocess_seconds = 0.0
        self._tracked_frames = 0
        self._bytetrack_seconds = 0.0
        self._crop_write_seconds = 0.0
        self._lanes = {
            name: {
                "waiting_batches": 0, "waiting_frames": 0, "peak_waiting_batches": 0,
                "calls": 0, "frames": 0, "wait_seconds": 0.0,
                "inference_seconds": 0.0, "idle_seconds": 0.0, "last_end": None,
            }
            for name in ("rfdetr", "retinaface")
        }
        self._gpu_status = "not_started"
        self._gpu_samples: list[float] = []
        self._gpu_stop = threading.Event()
        self._gpu_thread: threading.Thread | None = None

    def frame_enqueued(self) -> None:
        with self._lock:
            self._queued_frames += 1
            self._peak_queued_frames = max(self._peak_queued_frames, self._queued_frames)

    def frame_dequeued(self) -> None:
        with self._lock:
            self._queued_frames = max(0, self._queued_frames - 1)

    def record_decoded_frame(self, elapsed: float) -> None:
        with self._lock:
            self._decoded_frames += 1
            self._decode_seconds += elapsed

    def record_detector_preprocess(self, elapsed: float) -> None:
        with self._lock:
            self._detector_preprocess_seconds += elapsed

    def record_tracker_update(self, elapsed: float) -> None:
        with self._lock:
            self._tracked_frames += 1
            self._bytetrack_seconds += elapsed

    def record_crop_write(self, elapsed: float) -> None:
        with self._lock:
            self._crop_write_seconds += elapsed

    def run_inference(self, lane_name: str, lane_lock, frame_count: int, call: Callable,
                      cancel_token=None):
        lane = self._lanes[lane_name]
        queued_at = time.perf_counter()
        with self._lock:
            lane["waiting_batches"] += 1
            lane["waiting_frames"] += frame_count
            lane["peak_waiting_batches"] = max(lane["peak_waiting_batches"], lane["waiting_batches"])

        acquired = False
        still_queued = True
        try:
            while not acquired:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                acquired = lane_lock.acquire(timeout=0.1)
            started = time.perf_counter()
            with self._lock:
                lane["waiting_batches"] -= 1
                lane["waiting_frames"] -= frame_count
                lane["wait_seconds"] += started - queued_at
                still_queued = False
                if lane["last_end"] is not None:
                    lane["idle_seconds"] += max(0.0, started - lane["last_end"])
            try:
                return call()
            finally:
                finished = time.perf_counter()
                lane_lock.release()
                acquired = False
                with self._lock:
                    lane["calls"] += 1
                    lane["frames"] += frame_count
                    lane["inference_seconds"] += finished - started
                    lane["last_end"] = finished
        finally:
            if acquired:
                lane_lock.release()
            if still_queued:
                with self._lock:
                    lane["waiting_batches"] = max(0, lane["waiting_batches"] - 1)
                    lane["waiting_frames"] = max(0, lane["waiting_frames"] - frame_count)

    def start_gpu_sampling(self, enabled: bool) -> None:
        if not enabled:
            with self._lock:
                self._gpu_status = "model_on_cpu"
            return
        self._gpu_stop.clear()
        self._gpu_thread = threading.Thread(target=self._sample_gpu, name="tracking-gpu-metrics", daemon=True)
        self._gpu_thread.start()

    def _sample_gpu(self) -> None:
        try:
            import torch
            if not torch.cuda.is_available():
                with self._lock:
                    self._gpu_status = "cuda_unavailable"
                return
            with self._lock:
                self._gpu_status = "sampling"
            while not self._gpu_stop.is_set():
                try:
                    utilization = float(torch.cuda.utilization())
                except Exception as exc:
                    with self._lock:
                        self._gpu_status = f"unavailable:{type(exc).__name__}"
                    return
                with self._lock:
                    self._gpu_samples.append(utilization)
                    self._gpu_status = "available"
                if self._gpu_stop.wait(1.0):
                    return
        except Exception as exc:
            with self._lock:
                self._gpu_status = f"unavailable:{type(exc).__name__}"

    def stop_gpu_sampling(self) -> None:
        self._gpu_stop.set()
        if self._gpu_thread is not None:
            self._gpu_thread.join(timeout=2.0)
            self._gpu_thread = None

    def snapshot(self) -> dict:
        with self._lock:
            values = {
                "queued_frames": self._queued_frames,
                "peak_queued_frames": self._peak_queued_frames,
                "decoded_frames": self._decoded_frames,
                "decode_seconds": self._decode_seconds,
                "detector_preprocess_seconds": self._detector_preprocess_seconds,
                "tracked_frames": self._tracked_frames,
                "bytetrack_seconds": self._bytetrack_seconds,
                "crop_write_seconds": self._crop_write_seconds,
                "gpu_utilization_status": self._gpu_status,
            }
            for name, lane in self._lanes.items():
                values.update({
                    f"{name}_waiting_batches": lane["waiting_batches"],
                    f"{name}_waiting_frames": lane["waiting_frames"],
                    f"{name}_peak_waiting_batches": lane["peak_waiting_batches"],
                    f"{name}_calls": lane["calls"],
                    f"{name}_frames": lane["frames"],
                    f"{name}_average_batch_size": lane["frames"] / lane["calls"] if lane["calls"] else 0.0,
                    f"{name}_queue_wait_seconds": lane["wait_seconds"],
                    f"{name}_inference_seconds": lane["inference_seconds"],
                    f"{name}_lane_idle_seconds": lane["idle_seconds"],
                })
            samples = list(self._gpu_samples)
        values["gpu_utilization_samples"] = len(samples)
        values["gpu_utilization_average_pct"] = sum(samples) / len(samples) if samples else None
        values["gpu_utilization_latest_pct"] = samples[-1] if samples else None
        values["gpu_low_utilization_samples_pct"] = (
            100.0 * sum(value < 20.0 for value in samples) / len(samples) if samples else None
        )
        return {key: round(value, 2) if isinstance(value, float) else value for key, value in values.items()}
