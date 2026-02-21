"""transcription.py – faster-whisper transcription (Step 04)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Callable

import pandas as pd


def _srt_time(seconds: float) -> str:
    s = max(0.0, float(seconds))
    ms = int(round(s * 1000))
    hh, rem = divmod(ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1_000)
    return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"


def transcribe(
    audio_path: str,
    *,
    model_size: str = "large-v3",
    language: str = "de",
    beam_size: int = 5,
    compute_type: str = "int8",
    word_timestamps: bool = True,
    use_fw_vad: bool = True,
    vad_min_silence_ms: int = 350,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> tuple[pd.DataFrame, str, dict]:
    """Transcribe audio with faster-whisper.

    Returns:
        segments_df – DataFrame(start_s, end_s, text, avg_logprob, no_speech_prob)
        srt_str     – SRT subtitle string
        metadata    – dict with model info and stats
    """
    from faster_whisper import WhisperModel

    if progress_cb:
        progress_cb(f"Loading Whisper model '{model_size}'…")

    model = WhisperModel(model_size, compute_type=compute_type)

    vad_params = None
    if use_fw_vad:
        vad_params = {
            "min_silence_duration_ms": vad_min_silence_ms,
        }

    if progress_cb:
        progress_cb("Transcribing…")

    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=beam_size,
        word_timestamps=word_timestamps,
        vad_filter=use_fw_vad,
        vad_parameters=vad_params,
    )

    rows = []
    srt_blocks = []
    for idx, seg in enumerate(segments_iter, start=1):
        rows.append({
            "start_s": round(seg.start, 3),
            "end_s": round(seg.end, 3),
            "text": seg.text.strip(),
            "avg_logprob": round(float(seg.avg_logprob), 4),
            "no_speech_prob": round(float(seg.no_speech_prob), 4),
        })
        srt_blocks.append(
            f"{idx}\n{_srt_time(seg.start)} --> {_srt_time(seg.end)}\n{seg.text.strip()}\n"
        )

    segments_df = pd.DataFrame(
        rows if rows else [],
        columns=["start_s", "end_s", "text", "avg_logprob", "no_speech_prob"],
    )

    srt_str = "\n".join(srt_blocks)

    metadata = {
        "model_size": model_size,
        "language": info.language,
        "language_prob": round(float(info.language_probability), 4),
        "duration_s": round(float(info.duration), 3),
        "segment_count": len(rows),
    }

    if progress_cb:
        progress_cb(f"Done – {len(rows)} segments transcribed.")

    return segments_df, srt_str, metadata


def load_srt_as_df(srt_path: str) -> pd.DataFrame:
    """Parse an SRT file into a DataFrame with start_s/end_s/text columns."""
    import re
    text = Path(srt_path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", text.strip())
    rows = []
    ts_re = re.compile(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
    )
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        m = ts_re.search(lines[1])
        if not m:
            continue
        def to_s(h, m, s, ms): return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000
        start_s = to_s(*m.group(1, 2, 3, 4))
        end_s = to_s(*m.group(5, 6, 7, 8))
        txt = " ".join(lines[2:]).strip()
        rows.append({"start_s": start_s, "end_s": end_s, "text": txt,
                     "avg_logprob": 0.0, "no_speech_prob": 0.0})
    return pd.DataFrame(rows, columns=["start_s", "end_s", "text", "avg_logprob", "no_speech_prob"])
