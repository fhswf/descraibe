"""vad_pauses.py – Silero VAD speech-pause detection (Step 02)."""
from __future__ import annotations

import logging
import os
import select
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _emit_progress(progress_cb, message: str, current: int | float | None = None, total: int | float | None = None) -> None:
    if not progress_cb:
        return
    try:
        if current is None and total is None:
            progress_cb(message)
        else:
            progress_cb(message, current, total)
    except TypeError:
        progress_cb(message)


def extract_audio(
    video_path: str,
    wav_path: str,
    *,
    sample_rate_hz: int,
    total_duration_s: float = 0.0,
    progress_cb=None,
    reuse_existing: bool = True,
) -> float:
    """Extract mono PCM WAV audio for VAD/transcription and return duration."""
    wav = Path(wav_path)
    if reuse_existing and wav.exists() and wav.stat().st_size > 0:
        _emit_progress(progress_cb, "Using cached audio…", 40, 100)
        return total_duration_s

    try:
        _extract_audio_ffmpeg(
            str(video_path),
            str(wav),
            sample_rate_hz=sample_rate_hz,
            total_duration_s=total_duration_s,
            progress_cb=progress_cb,
        )
    except Exception as exc:
        logger.warning("ffmpeg audio extraction failed, falling back to MoviePy: %s", exc)
        _emit_progress(progress_cb, f"ffmpeg extraction failed; falling back to MoviePy: {exc}", 1, 100)
        total_duration_s = _extract_audio_moviepy_fallback(
            str(video_path),
            str(wav),
            sample_rate_hz=sample_rate_hz,
            progress_cb=progress_cb,
        )

    return total_duration_s


def _extract_audio_ffmpeg(
    video_path: str,
    wav_path: str,
    *,
    sample_rate_hz: int,
    total_duration_s: float,
    progress_cb=None,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg executable not found")

    no_progress_timeout_s = float(os.environ.get("AD_VAD_FFMPEG_NO_PROGRESS_TIMEOUT", "120"))
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate_hz),
        "-sample_fmt",
        "s16",
        "-progress",
        "pipe:1",
        "-nostats",
        wav_path,
    ]

    logger.info("Extracting VAD audio with ffmpeg: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    last_percent = 0
    last_progress_at = time.monotonic()
    try:
        assert proc.stdout is not None
        while True:
            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
            line = proc.stdout.readline() if ready else ""
            if line:
                key, _, value = line.strip().partition("=")
                if key in {"out_time_ms", "out_time_us"}:
                    try:
                        elapsed_s = float(value) / 1_000_000.0
                    except ValueError:
                        continue
                    if total_duration_s > 0:
                        fraction = max(0.0, min(elapsed_s / total_duration_s, 1.0))
                        percent = round(5 + fraction * 35)
                        if percent > last_percent:
                            last_percent = percent
                            _emit_progress(progress_cb, "Extracting audio…", percent, 100)
                            last_progress_at = time.monotonic()
                elif key == "progress":
                    last_progress_at = time.monotonic()

            if proc.poll() is not None:
                break

            if not line and time.monotonic() - last_progress_at > no_progress_timeout_s:
                proc.kill()
                raise RuntimeError(
                    f"ffmpeg audio extraction produced no progress for {int(no_progress_timeout_s)}s"
                )

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg audio extraction failed with exit code {proc.returncode}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def _extract_audio_moviepy_fallback(
    video_path: str,
    wav_path: str,
    *,
    sample_rate_hz: int,
    progress_cb=None,
) -> float:
    from moviepy import VideoFileClip
    from proglog import ProgressBarLogger

    class AudioExtractionLogger(ProgressBarLogger):
        def __init__(self):
            super().__init__()
            self.last_percent = 0

        def bars_callback(self, bar, attr, value, old_value=None):
            if attr != "index":
                return
            try:
                total = self.state.get("bars", {}).get(bar, {}).get("total") or 1
                fraction = max(0.0, min(float(value) / float(total), 1.0))
                percent = round(5 + fraction * 35)
                if percent > self.last_percent:
                    self.last_percent = percent
                    _emit_progress(progress_cb, "Extracting audio…", percent, 100)
            except Exception:
                pass

    clip = VideoFileClip(str(video_path))
    try:
        total_dur = float(clip.duration) if hasattr(clip, "duration") else 0.0
        clip.audio.write_audiofile(
            wav_path,
            fps=sample_rate_hz,
            nbytes=2,
            ffmpeg_params=["-ac", "1"],
            logger=AudioExtractionLogger(),
        )
        return total_dur
    finally:
        clip.close()


# ── SRT helpers ───────────────────────────────────────────────────────────────

def _srt_time(seconds: float) -> str:
    s = max(0.0, float(seconds))
    total_ms = int(round(s * 1000.0))
    hh, rem = divmod(total_ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1_000)
    return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"


# ── Core function ──────────────────────────────────────────────────────────────

def extract_pauses(
    video_path: str,
    *,
    audio_path: str | None = None,
    sample_rate_hz: int = 16000,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 200,        # notebook default: 200 ms
    min_silence_duration_ms: int = 400,
    speech_pad_ms: int = 50,
    min_pause_duration_s: float = 0.3,
    progress_cb=None,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Detect speech pauses via Silero VAD.

    Returns:
        pauses_df   – DataFrame(index, start_s, end_s, dur_s)
        speech_df   – DataFrame(start_s, end_s, dur_s)
        srt_str     – SRT string of pauses
    """
    logger.info(f"Extracting pauses from {video_path}")
    import torch
    import soundfile as sf

    last_percent = {"value": 0}

    def emit(message: str, current: int | float | None = None, total: int | float | None = None) -> None:
        if current is not None and total:
            current = max(float(current), float(last_percent["value"]))
            last_percent["value"] = current
        _emit_progress(progress_cb, message, current, total)

    emit("Extracting audio…", 0, 100)

    temp_wav_path = None
    if audio_path:
        wav_path = audio_path
    else:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        temp_wav_path = wav_path

    try:
        try:
            from pipeline import video_utils

            total_dur = float(video_utils.get_duration_s(str(video_path)) or 0.0)
        except Exception:
            total_dur = 0.0

        total_dur = extract_audio(
            str(video_path),
            wav_path,
            sample_rate_hz=sample_rate_hz,
            total_duration_s=total_dur,
            progress_cb=emit,
        )

        emit("Loading Silero VAD model…", 45, 100)

        # Load Silero VAD
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
        )
        (get_speech_timestamps, *_) = utils
        logger.info("Silero VAD model loaded.")

        # Read audio with soundfile instead of Silero's read_audio utility,
        # which relies on torchaudio.load() – broken in torchaudio >= 2.9
        # (requires torchcodec).  soundfile is already a project dependency.
        wav_data, sr = sf.read(wav_path, dtype="float32", always_2d=False)
        if sr != sample_rate_hz:
            raise RuntimeError(
                f"WAV sample rate {sr} != expected {sample_rate_hz}. "
                "Re-extract audio at the correct sample rate."
            )
        if not total_dur and sr:
            total_dur = float(len(wav_data)) / float(sr)
        audio = torch.from_numpy(wav_data)

        emit("Running VAD…", 70, 100)

        logger.info(f"Running VAD (SR={sample_rate_hz}, threshold={threshold}, min_speech={min_speech_duration_ms}ms, min_silence={min_silence_duration_ms}ms)")
        speech_ts = get_speech_timestamps(
            audio,
            model,
            sampling_rate=sample_rate_hz,
            threshold=threshold,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,
            speech_pad_ms=speech_pad_ms,
            return_seconds=True,
        )

    finally:
        if temp_wav_path:
            Path(temp_wav_path).unlink(missing_ok=True)

    emit("Building pause list…", 90, 100)

    # speech_df
    speech_rows = [
        {"start_s": float(t["start"]), "end_s": float(t["end"]),
         "dur_s": float(t["end"]) - float(t["start"])}
        for t in speech_ts
    ]
    speech_df = pd.DataFrame(
        speech_rows if speech_rows else [],
        columns=["start_s", "end_s", "dur_s"],
    )

    # pauses_df (gaps between speech segments)
    total_dur = total_dur or (
        speech_df["end_s"].max() if not speech_df.empty else 0.0
    )

    pause_rows = []
    prev_end = 0.0
    for _, row in speech_df.iterrows():
        gap_dur = row["start_s"] - prev_end
        if gap_dur >= min_pause_duration_s:
            pause_rows.append({
                "slot": len(pause_rows),
                "start_s": round(prev_end, 3),
                "end_s": round(row["start_s"], 3),
                "dur_s": round(gap_dur, 3),
            })
        prev_end = row["end_s"]

    # Final gap
    if total_dur - prev_end >= min_pause_duration_s:
        pause_rows.append({
            "slot": len(pause_rows),
            "start_s": round(prev_end, 3),
            "end_s": round(total_dur, 3),
            "dur_s": round(total_dur - prev_end, 3),
        })

    pauses_df = pd.DataFrame(
        pause_rows if pause_rows else [],
        columns=["slot", "start_s", "end_s", "dur_s"],
    )
    logger.info(f"VAD complete: detected {len(speech_rows)} speech segments and {len(pause_rows)} pauses.")

    # SRT string
    srt_lines = []
    for i, row in pauses_df.iterrows():
        srt_lines.append(
            f"{i + 1}\n{_srt_time(row['start_s'])} --> {_srt_time(row['end_s'])}\n"
            f"[PAUSE {row['dur_s']:.1f}s]\n"
        )
    srt_str = "\n".join(srt_lines)

    emit(f"Done – {len(pauses_df)} pauses detected.", 100, 100)

    return pauses_df, speech_df, srt_str
