# tests/test_vad_deps.py – regression tests for VAD pipeline dependencies
"""
Regression test for: "No module named 'torchaudio'"
The Silero VAD read_audio() utility requires torchaudio to be installed.
This test ensures the required imports are available before any real video
processing takes place.

Run with:
    uv run --no-sync pytest tests/test_vad_deps.py -v
"""


class TestVadDependencies:
    def test_torch_importable(self):
        """torch must be importable (required by Silero VAD model loading)."""
        import torch  # noqa: F401

    def test_torchaudio_importable(self):
        """
        Regression: 'No module named torchaudio' broke the VAD step.
        Silero VAD's read_audio() utility internally imports torchaudio.
        """
        import torchaudio  # noqa: F401

    def test_torchaudio_version_present(self):
        """torchaudio must expose a __version__ attribute."""
        import torchaudio
        assert hasattr(torchaudio, "__version__"), "torchaudio has no __version__"
        assert torchaudio.__version__, "torchaudio.__version__ is empty"

    def test_soundfile_importable(self):
        """soundfile is used as a fallback audio reader in the VAD step."""
        import soundfile  # noqa: F401

    def test_vad_module_importable(self):
        """The vad_pauses pipeline module itself must import without errors."""
        from backend.pipeline import vad_pauses  # noqa: F401

    def test_moviepy_importable(self):
        """moviepy is used to extract audio from the video before VAD."""
        from moviepy import VideoFileClip  # noqa: F401
