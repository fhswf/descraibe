from backend.pipeline.image_extraction import MidframeExtractor


class _FakeTimecode:
    def __init__(self, seconds):
        self._seconds = seconds

    def get_seconds(self):
        return self._seconds


class _FakeSceneManager:
    def add_detector(self, _detector):
        pass

    def detect_scenes(self, _video):
        for frame_num in (0, 10, 500, 1000):
            self._process_frame(frame_num, None)

    def _process_frame(self, _frame_num, _frame_im, _callback=None):
        return False

    def get_scene_list(self):
        return [
            (_FakeTimecode(1.0), _FakeTimecode(3.0)),
            (_FakeTimecode(3.0), _FakeTimecode(7.5)),
        ]


class _FakeContentDetector:
    def __init__(self, **_kwargs):
        pass


def test_detect_scenes_reports_frame_progress(monkeypatch, tmp_path):
    import scenedetect
    import scenedetect.detectors
    from backend.pipeline import image_extraction

    monkeypatch.setattr(image_extraction, "_video_frame_count", lambda _path: 1000)
    monkeypatch.setattr(scenedetect, "open_video", lambda _path: object())
    monkeypatch.setattr(scenedetect, "SceneManager", _FakeSceneManager)
    monkeypatch.setattr(scenedetect.detectors, "ContentDetector", _FakeContentDetector)

    progress = []
    extractor = MidframeExtractor(output_dir=str(tmp_path / "frames"))

    scenes = extractor.detect_scenes("video.mp4", progress_cb=lambda *args: progress.append(args))

    assert scenes == [(1.0, 3.0), (3.0, 7.5)]
    assert ("Detecting scenes…", 0, 1000) in progress
    assert ("Detecting scenes… frame 500/1000", 500, 1000) in progress
    assert ("Scene detection complete: found 2 scenes.", 1000, 1000) in progress
