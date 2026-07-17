"""
Regression tests for the VAD pipeline dependencies. Audio is read with
soundfile, so VAD must not require torchaudio to be installed.

Run with:
    uv run --no-sync pytest tests/test_vad_deps.py -v
"""


class TestVadDependencies:
    def test_torch_importable(self):
        """torch must be importable (required by Silero VAD model loading)."""
        import torch  # noqa: F401

    def test_soundfile_importable(self):
        """soundfile reads extracted WAV audio for the VAD step."""
        import soundfile  # noqa: F401

    def test_vad_module_importable(self):
        """The vad_pauses pipeline module itself must import without errors."""
        from backend.pipeline import vad_pauses  # noqa: F401

    def test_moviepy_importable(self):
        """moviepy is used to extract audio from the video before VAD."""
        from moviepy import VideoFileClip  # noqa: F401
