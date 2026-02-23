"""transcription.py – faster-whisper transcription (Step 04).

Fidelity notes (aligned with FINAL notebook step 04):
- Uses a double-VAD pass: faster-whisper built-in VAD (FW-VAD) AND a
  Silero-gate VAD whose intervals are passed as clip_timestamps so Whisper
  only decodes confirmed speech windows.
- Each decoded segment's timestamps are clamped to the nearest Silero interval
  to prevent timestamp bleed into pauses.
- The WhisperModel is cached at module level to avoid reloading the model
  (which is multi-GB) on every request.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd


# ── SRT time helper ────────────────────────────────────────────────────────────

def _srt_time(seconds: float) -> str:
    s = max(0.0, float(seconds))
    ms = int(round(s * 1000))
    hh, rem = divmod(ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1_000)
    return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"


# ── Module-level Whisper model cache (P1-B) ────────────────────────────────────

_MODEL_CACHE: dict[str, object] = {}
_MODEL_LOCK = threading.Lock()


def _get_model(model_size: str, device: str = "cpu", compute_type: str = "int8"):
    """Return a cached WhisperModel, loading it on first use."""
    from faster_whisper import WhisperModel
    key = f"{model_size}_{device}_{compute_type}"
    if key not in _MODEL_CACHE:
        with _MODEL_LOCK:
            if key not in _MODEL_CACHE:
                _MODEL_CACHE[key] = WhisperModel(
                    model_size, device=device, compute_type=compute_type
                )
    return _MODEL_CACHE[key]


# ── Silero VAD helpers (P1-A) ──────────────────────────────────────────────────

def _load_silero_model():
    """Load silero-vad model from torch.hub (cached after first load)."""
    import torch
    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
    )
    return model, utils


def get_silero_vad_intervals(
    audio_path: str,
    *,
    threshold: float = 0.70,
    min_speech_s: float = 0.45,
    min_silence_s: float = 0.55,
    merge_gap_s: float = 0.35,
    drop_short_s: float = 0.35,
    sample_rate: int = 16000,
) -> list[tuple[float, float]]:
    """Run Silero VAD and return a list of (start_s, end_s) speech intervals.

    Parameters match the FINAL notebook's transcription Silero-gate defaults.
    """
    import torch
    import soundfile as sf

    model, utils = _load_silero_model()
    get_speech_timestamps = utils[0]

    audio, sr = sf.read(audio_path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != sample_rate:
        # Simple linear resampling via numpy if scipy not available
        try:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(sample_rate, sr)
            audio = resample_poly(audio, sample_rate // g, sr // g)
        except ImportError:
            n_target = int(len(audio) * sample_rate / sr)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, n_target),
                np.arange(len(audio)),
                audio,
            )

    audio_tensor = torch.from_numpy(audio.astype("float32"))

    raw = get_speech_timestamps(
        audio_tensor,
        model,
        threshold=float(threshold),
        min_speech_duration_ms=int(min_speech_s * 1000),
        min_silence_duration_ms=int(min_silence_s * 1000),
        speech_pad_ms=0,
        return_seconds=True,
    )

    intervals: list[tuple[float, float]] = [
        (float(seg["start"]), float(seg["end"])) for seg in raw
    ]

    # Merge gaps smaller than merge_gap_s
    if merge_gap_s > 0 and len(intervals) > 1:
        merged: list[tuple[float, float]] = [intervals[0]]
        for s, e in intervals[1:]:
            prev_s, prev_e = merged[-1]
            if s - prev_e <= merge_gap_s:
                merged[-1] = (prev_s, e)
            else:
                merged.append((s, e))
        intervals = merged

    # Drop intervals shorter than drop_short_s
    if drop_short_s > 0:
        intervals = [(s, e) for s, e in intervals if e - s >= drop_short_s]

    return intervals


def _clamp_to_intervals(
    t0: float,
    t1: float,
    intervals: list[tuple[float, float]],
) -> tuple[float, float]:
    """Clamp (t0, t1) to the nearest Silero speech interval."""
    t0, t1 = float(t0), float(t1)
    if t1 < t0:
        t1 = t0

    for s, e in intervals:
        if s <= t0 <= e:
            return (max(t0, s), min(t1, e))

    after = [(s, e) for s, e in intervals if s > t0]
    if after:
        s, e = after[0]
        return (max(t0, s), min(max(t1, s), e))

    if intervals:
        s, e = intervals[-1]
        return (max(t0, s), min(t1, e))

    return (t0, t1)


# ── Transcript upload helpers ──────────────────────────────────────────────────

def _parse_srt_time(t: str) -> float:
    """Parse 'HH:MM:SS,mmm' or 'HH:MM:SS.mmm' → float seconds."""
    t = t.strip().replace(",", ".")
    parts = t.split(":")
    hh, mm, rest = int(parts[0]), int(parts[1]), float(parts[2])
    return hh * 3600 + mm * 60 + rest


def load_srt_as_df(srt_path: str) -> pd.DataFrame:
    """Parse an SRT file into a DataFrame with columns index/start_s/end_s/dur_s/text."""
    text = Path(srt_path).read_text(encoding="utf-8")
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]
    rows = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
            timeline = lines[1]
            start_str, end_str = timeline.split("-->")
            start_s = _parse_srt_time(start_str)
            end_s = _parse_srt_time(end_str)
            body = " ".join(l.strip() for l in lines[2:] if l.strip())
            rows.append({
                "index": idx,
                "start_s": start_s,
                "end_s": end_s,
                "dur_s": max(0.0, end_s - start_s),
                "text": body,
            })
        except Exception:
            continue
    return pd.DataFrame(rows, columns=["index", "start_s", "end_s", "dur_s", "text"])


# ── Core transcription ─────────────────────────────────────────────────────────

def transcribe(
    audio_path: str,
    *,
    model_size: str = "large-v3",
    language: str = "de",
    beam_size: int = 5,
    compute_type: str = "int8",
    # FW-VAD
    use_fw_vad: bool = True,
    vad_min_silence_ms: int = 350,
    vad_speech_pad_ms: int = 80,
    # Silero gate (P1-A)
    use_silero_gate: bool = True,
    silero_threshold: float = 0.70,
    silero_min_speech_s: float = 0.45,
    silero_min_silence_s: float = 0.55,
    silero_merge_gap_s: float = 0.35,
    silero_drop_short_s: float = 0.35,
    clamp_to_vad: bool = True,
    # word timestamps
    word_timestamps: bool = True,
    # time window (optional)
    time_window: str = "full",       # "full" | "custom"
    start_s: Optional[float] = None,
    end_s: Optional[float] = None,
    # callbacks
    progress_cb: Optional[Callable[[str, Optional[float], Optional[float]], None]] = None,
    total_duration_s: float = 0.0,
) -> tuple[pd.DataFrame, str, dict]:
    """Transcribe audio using faster-whisper with optional Silero-gate.

    Returns:
        df:      DataFrame with columns [index, start_s, end_s, dur_s, text,
                                         avg_logprob, no_speech_prob]
        srt_str: SRT-format string
        meta:    dict of transcription metadata
    """
    p = Path(audio_path)
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {p}")

    if time_window == "custom":
        win_start = float(start_s) if start_s is not None else 0.0
        win_end = float(end_s) if end_s is not None else None
        if win_start < 0:
            raise ValueError("start_s must be >= 0")
        if win_end is not None and win_end <= win_start:
            raise ValueError("end_s must be > start_s")
    else:
        win_start, win_end = None, None

    if progress_cb:
        progress_cb("Loading Whisper model…")
        
    # Dynamically select GPU if available
    try:
        import torch
        if torch.cuda.is_available():
            hw_device = "cuda"
            hw_compute = "float16"
        else:
            hw_device = "cpu"
            hw_compute = compute_type
    except ImportError:
        hw_device = "cpu"
        hw_compute = compute_type

    model = _get_model(model_size, device=hw_device, compute_type=hw_compute)

    # ── Silero gate (P1-A) ────────────────────────────────────────────────
    silero_intervals: list[tuple[float, float]] = []
    if use_silero_gate:
        if progress_cb:
            progress_cb("Running Silero VAD gate…")
        silero_intervals = get_silero_vad_intervals(
            str(p),
            threshold=silero_threshold,
            min_speech_s=silero_min_speech_s,
            min_silence_s=silero_min_silence_s,
            merge_gap_s=silero_merge_gap_s,
            drop_short_s=silero_drop_short_s,
        )
        # Clip to time window
        if win_start is not None or win_end is not None:
            ws = win_start or 0.0
            we = win_end or 1e18
            silero_intervals = [
                (max(s, ws), min(e, we))
                for s, e in silero_intervals
                if not (e < ws or s > we)
            ]

    # ── faster-whisper kwargs ─────────────────────────────────────────────
    vad_params = None
    if use_fw_vad:
        vad_params = {
            "min_silence_duration_ms": int(vad_min_silence_ms),
            "speech_pad_ms": int(vad_speech_pad_ms),
        }

    kwargs: dict = dict(
        language=language,
        beam_size=int(beam_size),
        vad_filter=bool(use_fw_vad),
        vad_parameters=vad_params,
        word_timestamps=bool(word_timestamps),
    )

    # Pass Silero intervals as clip_timestamps (flattened [s1,e1,s2,e2,…])
    if silero_intervals:
        flat = [v for iv in silero_intervals for v in iv]
        kwargs["clip_timestamps"] = flat
    elif win_start is not None and win_end is not None:
        kwargs["clip_timestamps"] = [win_start, win_end]

    if progress_cb:
        progress_cb("Transcribing…")

    try:
        segments, info = model.transcribe(str(p), **kwargs)
    except TypeError as exc:
        # Some faster-whisper versions expect clip_timestamps as list of tuples
        if "clip_timestamps" in kwargs and "tuple" in str(exc).lower():
            if silero_intervals:
                kwargs["clip_timestamps"] = silero_intervals
            elif win_start is not None and win_end is not None:
                kwargs["clip_timestamps"] = [(win_start, win_end)]
            else:
                kwargs.pop("clip_timestamps", None)
            segments, info = model.transcribe(str(p), **kwargs)
        else:
            raise

    # ── Collect rows ──────────────────────────────────────────────────────
    rows = []
    out_idx = 1
    
    # We want to report progress during generation
    total_duration_s = max(total_duration_s, 0.1) # Avoid div-by-zero
    last_reported_s = -1.0
    
    for seg in segments:
        text = (getattr(seg, "text", "") or "").strip()
        if not text:
            continue

        seg_start = float(getattr(seg, "start", 0.0) or 0.0)
        seg_end = float(getattr(seg, "end", seg_start) or seg_start)

        # Prefer word-level timestamps for tighter bounds
        words = getattr(seg, "words", None)
        if words:
            try:
                seg_start = float(getattr(words[0], "start", seg_start) or seg_start)
                seg_end = float(getattr(words[-1], "end", seg_end) or seg_end)
            except Exception:
                pass

        if seg_end < seg_start:
            seg_end = seg_start

        # Clamp to Silero intervals (P1-A)
        if clamp_to_vad and silero_intervals:
            seg_start, seg_end = _clamp_to_intervals(seg_start, seg_end, silero_intervals)

        avg_lp = getattr(seg, "avg_logprob", None)
        nsp = getattr(seg, "no_speech_prob", None)

        rows.append({
            "index": out_idx,
            "start_s": seg_start,
            "end_s": seg_end,
            "dur_s": max(0.0, seg_end - seg_start),
            "text": text,
            "avg_logprob": float(avg_lp) if avg_lp is not None else None,
            "no_speech_prob": float(nsp) if nsp is not None else None,
        })
        out_idx += 1
        
        # Report progress if 1 second has passed since last report to avoid spamming the frontend
        if progress_cb and (seg_end - last_reported_s >= 1.0 or seg_end >= total_duration_s):
             # Format mm:ss
             def fmt(secs):
                 secs = int(max(0, secs))
                 return f"{secs//60:02}:{secs%60:02}"
             
             capped_end = min(seg_end, total_duration_s)
             msg = f"Transcribing… {fmt(capped_end)} / {fmt(total_duration_s)}"
             progress_cb(msg, capped_end, total_duration_s)
             last_reported_s = seg_end

    cols = ["index", "start_s", "end_s", "dur_s", "text", "avg_logprob", "no_speech_prob"]
    df = pd.DataFrame(rows, columns=cols)

    # Normalise numeric columns
    for col in ["start_s", "end_s", "dur_s"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["start_s", "end_s"]).copy()
    df = df[df["end_s"] >= df["start_s"]].copy()

    # Apply custom time window filter
    if time_window == "custom" and not df.empty:
        ws = float(win_start or 0.0)
        df = df[df["end_s"] > ws].copy()
        df["start_s"] = df["start_s"].clip(lower=ws)
        if win_end is not None:
            we = float(win_end)
            df = df[df["start_s"] < we].copy()
            df["end_s"] = df["end_s"].clip(upper=we)
        df["dur_s"] = (df["end_s"] - df["start_s"]).clip(lower=0.0)
        df = df.reset_index(drop=True)
        df["index"] = range(1, len(df) + 1)

    # ── Build SRT ─────────────────────────────────────────────────────────
    lines: list[str] = []
    for _, r in df.iterrows():
        lines.append(str(int(r["index"])))
        lines.append(f"{_srt_time(r['start_s'])} --> {_srt_time(r['end_s'])}")
        lines.append(str(r["text"]).strip())
        lines.append("")
    srt_str = ("\n".join(lines).strip() + "\n") if lines else ""

    meta = {
        "model_size": model_size,
        "beam_size": int(beam_size),
        "fw_vad": bool(use_fw_vad),
        "word_timestamps": bool(word_timestamps),
        "silero_gate": bool(use_silero_gate),
        "silero_intervals_count": len(silero_intervals),
        "time_window": time_window,
        "segments": int(len(df)),
    }

    return df, srt_str, meta
