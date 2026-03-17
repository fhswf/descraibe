"""vad_pauses.py – Silero VAD speech-pause detection (Step 02)."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


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
    from moviepy import VideoFileClip

    if progress_cb:
        progress_cb("Extracting audio…")

    # Extract audio to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name

    try:
        clip = VideoFileClip(str(video_path))
        clip.audio.write_audiofile(wav_path, fps=sample_rate_hz, nbytes=2,
                                   ffmpeg_params=["-ac", "1"], logger=None)
        clip.close()

        if progress_cb:
            progress_cb("Loading Silero VAD model…")

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
        audio = torch.from_numpy(wav_data)

        if progress_cb:
            progress_cb("Running VAD…")

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
        Path(wav_path).unlink(missing_ok=True)

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
    total_dur = float(clip.duration) if hasattr(clip, "duration") else (
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

    if progress_cb:
        progress_cb(f"Done – {len(pauses_df)} pauses detected.")

    return pauses_df, speech_df, srt_str
