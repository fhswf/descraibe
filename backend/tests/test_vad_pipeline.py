# tests/test_vad_pipeline.py – functional tests for vad_pauses.extract_pauses()
"""
Tests the VAD pause-detection logic end-to-end using:
  - A synthetic WAV file (silence-speech-silence pattern via numpy+soundfile)
  - Mocked VideoFileClip (avoids needing a real video)
  - Mocked torch.hub.load (avoids Silero model download; returns predictable timestamps)

Run with:
    uv run --no-sync python -m pytest tests/test_vad_pipeline.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import soundfile as sf


# ── Helpers ───────────────────────────────────────────────────────────────────

SR = 16_000  # sample rate used throughout


def _make_synthetic_wav(path: str, duration_s: float = 10.0) -> None:
    """Write a WAV with three speech blocks and two silence gaps.

    Layout (seconds):
      0.0 – 1.0   silence  (pause)
      1.0 – 3.0   speech
      3.0 – 4.5   silence  (pause, ~1.5 s)
      4.5 – 7.0   speech
      7.0 – 10.0  silence  (pause, 3 s)
    """
    samples = int(duration_s * SR)
    audio = np.zeros(samples, dtype=np.float32)
    # Add tone in "speech" regions
    t = np.arange(samples) / SR
    speech_mask = ((t >= 1.0) & (t < 3.0)) | ((t >= 4.5) & (t < 7.0))
    audio[speech_mask] = 0.3 * np.sin(2 * np.pi * 440 * t[speech_mask])
    sf.write(path, audio, SR)


def _make_mock_silero(speech_timestamps_s: list[dict]) -> tuple:
    """Return a (model, utils) tuple that mimics the silero_vad API.

    speech_timestamps_s: list of {"start": float, "end": float} in seconds.
    get_speech_timestamps returns them unchanged (return_seconds=True path).
    """
    mock_model = MagicMock()

    def fake_get_speech_timestamps(audio, model, **kwargs):
        return speech_timestamps_s

    def fake_read_audio(wav_path, sampling_rate=16000):
        data, _ = sf.read(wav_path, dtype="float32")
        import torch
        return torch.from_numpy(data)

    utils = (
        fake_get_speech_timestamps,  # get_speech_timestamps
        None,                        # save_audio (unused)
        fake_read_audio,             # read_audio
    )
    return mock_model, utils


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_wav(tmp_path) -> Path:
    p = tmp_path / "test_audio.wav"
    _make_synthetic_wav(str(p))
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestExtractPausesUnit:
    """Unit tests: mock both moviepy and Silero, test pure Python logic."""

    SPEECH_TS = [
        {"start": 1.0, "end": 3.0},
        {"start": 4.5, "end": 7.0},
    ]
    TOTAL_DUR = 10.0

    def _run(self, synthetic_wav, **kwargs):
        """Patch moviepy + silero and run extract_pauses."""
        from backend.pipeline import vad_pauses

        mock_model, mock_utils = _make_mock_silero(self.SPEECH_TS)

        # VideoFileClip just needs to copy our synthetic wav into the temp path
        def fake_clip_ctor(video_path):
            clip = MagicMock()
            clip.duration = self.TOTAL_DUR

            def fake_write_audiofile(out_path, **kw):
                import shutil
                shutil.copy(str(synthetic_wav), out_path)

            clip.audio.write_audiofile.side_effect = fake_write_audiofile
            return clip

        with patch("moviepy.VideoFileClip", side_effect=fake_clip_ctor):
            with patch("torch.hub.load", return_value=(mock_model, mock_utils)):
                return vad_pauses.extract_pauses(
                    str(synthetic_wav),
                    sample_rate_hz=SR,
                    **kwargs,
                )

    def test_returns_three_dataframes_and_string(self, synthetic_wav):
        pauses_df, speech_df, srt_str = self._run(synthetic_wav)
        assert isinstance(pauses_df, pd.DataFrame)
        assert isinstance(speech_df, pd.DataFrame)
        assert isinstance(srt_str, str)

    def test_speech_df_matches_mock(self, synthetic_wav):
        _, speech_df, _ = self._run(synthetic_wav)
        assert len(speech_df) == 2
        assert pytest.approx(speech_df.iloc[0]["start_s"]) == 1.0
        assert pytest.approx(speech_df.iloc[0]["end_s"])   == 3.0
        assert pytest.approx(speech_df.iloc[1]["start_s"]) == 4.5
        assert pytest.approx(speech_df.iloc[1]["end_s"])   == 7.0

    def test_pause_between_speech_blocks(self, synthetic_wav):
        """Gap between 3.0 and 4.5 (1.5 s) must appear as a pause."""
        pauses_df, _, _ = self._run(synthetic_wav, min_pause_duration_s=0.3)
        mid_pauses = pauses_df[
            (pauses_df["start_s"] >= 2.9) & (pauses_df["end_s"] <= 4.6)
        ]
        assert len(mid_pauses) == 1, f"Expected 1 mid pause, got:\n{pauses_df}"
        assert pytest.approx(mid_pauses.iloc[0]["dur_s"], abs=0.01) == 1.5

    def test_trailing_silence_is_pause(self, synthetic_wav):
        """Silence after last speech (7.0 – 10.0 = 3 s) must be captured."""
        pauses_df, _, _ = self._run(synthetic_wav, min_pause_duration_s=0.3)
        trailing = pauses_df[pauses_df["start_s"] >= 6.9]
        assert len(trailing) == 1
        assert pytest.approx(trailing.iloc[0]["dur_s"], abs=0.05) == 3.0

    def test_min_pause_duration_filter(self, synthetic_wav):
        """With min_pause_duration_s=2.0 only the trailing 3-s silence qualifies."""
        pauses_df, _, _ = self._run(synthetic_wav, min_pause_duration_s=2.0)
        assert len(pauses_df) == 1
        assert pauses_df.iloc[0]["dur_s"] > 2.0

    def test_srt_contains_pause_marker(self, synthetic_wav):
        _, _, srt_str = self._run(synthetic_wav, min_pause_duration_s=0.3)
        assert "[PAUSE" in srt_str

    def test_pauses_df_columns(self, synthetic_wav):
        pauses_df, _, _ = self._run(synthetic_wav)
        for col in ("slot", "start_s", "end_s", "dur_s"):
            assert col in pauses_df.columns, f"Missing column: {col}"

    def test_speech_df_columns(self, synthetic_wav):
        _, speech_df, _ = self._run(synthetic_wav)
        for col in ("start_s", "end_s", "dur_s"):
            assert col in speech_df.columns, f"Missing column: {col}"

    def test_no_speech_returns_empty_speech_df(self, synthetic_wav):
        """If Silero finds no speech the function must return an empty speech_df."""
        from backend.pipeline import vad_pauses

        mock_model, mock_utils = _make_mock_silero([])  # no speech

        def fake_clip_ctor(video_path):
            clip = MagicMock()
            clip.duration = 5.0

            def fake_write_audiofile(out_path, **kw):
                import shutil
                shutil.copy(str(synthetic_wav), out_path)

            clip.audio.write_audiofile.side_effect = fake_write_audiofile
            return clip

        with patch("moviepy.VideoFileClip", side_effect=fake_clip_ctor):
            with patch("torch.hub.load", return_value=(mock_model, mock_utils)):
                pauses_df, speech_df, _ = vad_pauses.extract_pauses(
                    str(synthetic_wav), sample_rate_hz=SR
                )

        assert speech_df.empty
        # Entire duration should be one big pause
        assert len(pauses_df) == 1
