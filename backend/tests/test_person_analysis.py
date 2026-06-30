"""Tests for the person_analysis pipeline module."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest


class TestTimestampExtraction:
    """Tests for _extract_ts_from_filename function."""

    def test_extract_valid_timestamp(self):
        from backend.pipeline.person_analysis import _extract_ts_from_filename

        # Standard format: video_stem_00-05-30-000.jpg
        ts = _extract_ts_from_filename("test_video_00-05-30-000.jpg")
        assert ts == 5 * 60 + 30.0

    def test_extract_timestamp_with_gapfill(self):
        from backend.pipeline.person_analysis import _extract_ts_from_filename

        # Gapfill format: video_stem_slot_0001_gapfill_00-10-15-500.jpg
        ts = _extract_ts_from_filename("video_slot_0001_gapfill_00-10-15-500.jpg")
        assert ts == 10 * 60 + 15.5

    def test_extract_timestamp_invalid_format(self):
        from backend.pipeline.person_analysis import _extract_ts_from_filename

        ts = _extract_ts_from_filename("invalid_filename.jpg")
        assert ts is None

    def test_extract_timestamp_multiple_underscores(self):
        from backend.pipeline.person_analysis import _extract_ts_from_filename

        # Should find the last timestamp in the name
        ts = _extract_ts_from_filename("prefix_00-01-00-000_suffix.jpg")
        assert ts == 60.0


class TestIoU:
    """Tests for _compute_iou function."""

    def test_compute_iou_no_overlap(self):
        from backend.pipeline.person_analysis import _compute_iou

        bbox1 = {"x": 0, "y": 0, "w": 10, "h": 10}
        bbox2 = {"x": 20, "y": 20, "w": 10, "h": 10}
        iou = _compute_iou(bbox1, bbox2)
        assert iou == 0.0

    def test_compute_iou_full_overlap(self):
        from backend.pipeline.person_analysis import _compute_iou

        bbox1 = {"x": 0, "y": 0, "w": 10, "h": 10}
        bbox2 = {"x": 0, "y": 0, "w": 10, "h": 10}
        iou = _compute_iou(bbox1, bbox2)
        assert iou == 1.0

    def test_compute_iou_partial_overlap(self):
        from backend.pipeline.person_analysis import _compute_iou

        bbox1 = {"x": 0, "y": 0, "w": 10, "h": 10}
        bbox2 = {"x": 5, "y": 5, "w": 10, "h": 10}
        # Intersection: 5x5 = 25, Area1 = 100, Area2 = 100, Union = 175, IoU = 25/175
        iou = _compute_iou(bbox1, bbox2)
        assert 0.1 < iou < 0.2


class TestColorExtraction:
    """Tests for color extraction functions."""

    def test_rgb_to_color_name_basic(self):
        from backend.pipeline.person_analysis import _rgb_to_color_name

        # Test some basic colors
        assert _rgb_to_color_name(255, 0, 0) == "rot"
        assert _rgb_to_color_name(0, 0, 255) == "blau"
        assert _rgb_to_color_name(0, 255, 0) == "grün"

    def test_rgb_to_color_name_grayscale(self):
        from backend.pipeline.person_analysis import _rgb_to_color_name

        # White
        assert _rgb_to_color_name(255, 255, 255) == "weiß"
        # Black
        assert _rgb_to_color_name(10, 10, 10) == "schwarz"


class TestPersonClass:
    """Tests for Person tracking class."""

    def test_person_creation(self):
        from backend.pipeline.person_analysis import Person

        person = Person(person_id=1, first_seen_ts=10.0, name="Test Person")
        assert person.person_id == 1
        assert person.first_seen_ts == 10.0
        assert person.name == "Test Person"
        assert len(person.appearances) == 0

    def test_person_add_appearance(self):
        from backend.pipeline.person_analysis import Person

        person = Person(person_id=1, first_seen_ts=10.0)
        person.add_appearance(
            timestamp_s=10.0,
            image_path="/test/image.jpg",
            face_bbox={"x": 100, "y": 100, "w": 50, "h": 50},
            person_region=np.zeros((100, 50, 3), dtype=np.uint8),
            attributes={"top_color": "blau"},
        )

        assert len(person.appearances) == 1
        assert person.appearances[0]["timestamp_s"] == 10.0
        assert person.attributes["top_color"] == "blau"

    def test_person_color_tracking(self):
        from backend.pipeline.person_analysis import Person

        person = Person(person_id=1, first_seen_ts=0.0)
        person.update_color((100.0, 120.0, 140.0))
        person.update_color((102.0, 118.0, 142.0))

        mean = person.mean_color()
        assert abs(mean[0] - 101.0) < 1.0  # B channel
        assert abs(mean[1] - 119.0) < 1.0  # G channel
        assert abs(mean[2] - 141.0) < 1.0  # R channel


class TestPersonsContext:
    """Tests for _build_persons_context function."""

    def test_empty_persons_df(self):
        from backend.pipeline.gpt_description import _build_persons_context
        import pandas as pd

        result = _build_persons_context(None, 0.0, 10.0)
        assert result == ""

        result = _build_persons_context(pd.DataFrame(), 0.0, 10.0)
        assert result == ""

    def test_persons_in_slot(self):
        from backend.pipeline.gpt_description import _build_persons_context
        import pandas as pd

        persons_df = pd.DataFrame([
            {
                "person_id": 1,
                "name": "Maria",
                "first_seen_ts": 5.0,
                "last_seen_ts": 15.0,
                "description": "Maria trägt ein blaues Oberteil.",
            },
            {
                "person_id": 2,
                "name": "Hans",
                "first_seen_ts": 20.0,
                "last_seen_ts": 30.0,
                "description": "Hans trägt eine schwarze Jacke.",
            },
        ])

        # Slot 0-10 should include Maria (first_seen=5, last_seen=15)
        result = _build_persons_context(persons_df, 0.0, 10.0)
        assert "Maria" in result
        assert "Hans" not in result
        assert "ERSTNENNUNG" in result

    def test_persons_first_vs_subsequent_mention(self):
        from backend.pipeline.gpt_description import _build_persons_context
        import pandas as pd

        persons_df = pd.DataFrame([
            {
                "person_id": 1,
                "name": "Maria",
                "first_seen_ts": 5.0,
                "last_seen_ts": 15.0,
                "description": "Maria trägt ein blaues Oberteil.",
            },
        ])

        # Slot that contains the first appearance → ERSTNENNUNG
        result = _build_persons_context(persons_df, 0.0, 10.0)
        assert "ERSTNENNUNG" in result

        # Slot that starts at the first appearance time → ERSTNENNUNG (first slot with this person)
        result = _build_persons_context(persons_df, 5.0, 10.0)
        assert "ERSTNENNUNG" in result

        # Slot that is entirely after the first appearance → FOLGEBENENNUNG
        result = _build_persons_context(persons_df, 15.0, 20.0)
        assert "FOLGEBENENNUNG" in result


class TestAnalyzePersons:
    """Integration tests for analyze_persons function."""

    def test_analyze_persons_no_images(self):
        from backend.pipeline.person_analysis import analyze_persons

        result = analyze_persons([], progress_cb=None)
        import pandas as pd
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @patch("backend.pipeline.person_analysis.detect_faces_in_image")
    def test_analyze_persons_with_mocked_detection(self, mock_detect):
        from backend.pipeline.person_analysis import analyze_persons

        # Mock face detection to return one face per image
        mock_detect.return_value = [
            {"x": 100, "y": 100, "w": 50, "h": 50, "confidence": 0.9}
        ]

        # Create fake image paths with timestamps
        images = [
            "/tmp/test_00-00-10-000.jpg",
            "/tmp/test_00-00-20-000.jpg",
        ]

        progress_calls = []
        result = analyze_persons(images, progress_cb=lambda *args: progress_calls.append(args))

        import pandas as pd
        assert isinstance(result, pd.DataFrame)
        # Should detect 1 person across 2 frames (tracking)
        # (depends on tracking logic - may be 1 or 2 depending on time gap)

    def test_analyze_persons_graceful_fallback_no_model(self):
        from backend.pipeline.person_analysis import analyze_persons

        # Even without a model, should return empty DataFrame (graceful)
        with patch("backend.pipeline.person_analysis.YuNetDetector") as mock_detector:
            mock_instance = MagicMock()
            mock_instance.detect.return_value = []
            mock_detector.return_value = mock_instance

            result = analyze_persons(["/tmp/fake_image.jpg"], progress_cb=None)

            import pandas as pd
            assert isinstance(result, pd.DataFrame)


class TestYuNetDetector:
    """Tests for YuNetDetector class."""

    def test_detector_returns_empty_without_model(self):
        from backend.pipeline.person_analysis import YuNetDetector

        with patch.object(YuNetDetector, "_ensure_model", return_value=False):
            detector = YuNetDetector()
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            faces = detector.detect(img)
            assert faces == []

    def test_detector_singleton(self):
        from backend.pipeline.person_analysis import YuNetDetector

        # Reset singleton for test
        YuNetDetector._instance = None
        YuNetDetector._model = None

        d1 = YuNetDetector()
        d2 = YuNetDetector()
        assert d1 is d2

    def test_detector_output_format(self):
        """Test that detector returns correct output format (x, y, w, h, confidence)."""
        from backend.pipeline.person_analysis import YuNetDetector

        # Reset singleton
        YuNetDetector._instance = None
        YuNetDetector._model = None

        # Create mock model that returns a valid result
        mock_model = MagicMock()
        # Simulate FaceDetectorYN output: (1, 15) = [x, y, w, h, 5_landmarks..., conf]
        mock_result = np.array([[100, 100, 50, 60, 130, 130, 150, 130, 155, 135, 130, 140, 155, 145, 0.9]], dtype=np.float32)
        mock_model.detect.return_value = (None, mock_result)
        mock_model.setInputSize = MagicMock()

        with patch.object(YuNetDetector, "_ensure_model", return_value=True):
            with patch.object(YuNetDetector, "_model", mock_model):
                detector = YuNetDetector()
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                faces = detector.detect(img)

                assert len(faces) == 1
                face = faces[0]
                assert "x" in face
                assert "y" in face
                assert "w" in face
                assert "h" in face
                assert "confidence" in face
                assert face["x"] == 100
                assert face["y"] == 100
                assert face["w"] == 50
                assert face["h"] == 60
                assert abs(face["confidence"] - 0.9) < 0.01

    def test_detector_handles_none_results(self):
        """Test that detector handles None results gracefully."""
        from backend.pipeline.person_analysis import YuNetDetector

        # Reset singleton
        YuNetDetector._instance = None
        YuNetDetector._model = None

        mock_model = MagicMock()
        mock_model.detect.return_value = (None, None)
        mock_model.setInputSize = MagicMock()

        with patch.object(YuNetDetector, "_ensure_model", return_value=True):
            with patch.object(YuNetDetector, "_model", mock_model):
                detector = YuNetDetector()
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                faces = detector.detect(img)

                assert faces == []

    def test_detector_handles_empty_results(self):
        """Test that detector handles empty array results gracefully."""
        from backend.pipeline.person_analysis import YuNetDetector

        # Reset singleton
        YuNetDetector._instance = None
        YuNetDetector._model = None

        mock_model = MagicMock()
        mock_model.detect.return_value = (None, np.array([], dtype=np.float32).reshape(0, 15))
        mock_model.setInputSize = MagicMock()

        with patch.object(YuNetDetector, "_ensure_model", return_value=True):
            with patch.object(YuNetDetector, "_model", mock_model):
                detector = YuNetDetector()
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                faces = detector.detect(img)

                assert faces == []


class TestFaceNetEmbedding:
    """Tests for FaceNet embedding extractor."""

    def test_cosine_similarity_same_vector(self):
        """Cosine similarity of same vector should be 1.0."""
        from backend.pipeline.person_analysis import _cosine_similarity
        import numpy as np

        v = np.array([1.0, 2.0, 3.0])
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_cosine_similarity_opposite_vectors(self):
        """Cosine similarity of opposite vectors should be -1.0."""
        from backend.pipeline.person_analysis import _cosine_similarity
        import numpy as np

        v1 = np.array([1.0, 2.0, 3.0])
        v2 = np.array([-1.0, -2.0, -3.0])
        assert abs(_cosine_similarity(v1, v2) - (-1.0)) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        """Cosine similarity of orthogonal vectors should be 0.0."""
        from backend.pipeline.person_analysis import _cosine_similarity
        import numpy as np

        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0])
        assert abs(_cosine_similarity(v1, v2)) < 1e-6

    def test_cosine_similarity_zero_vector(self):
        """Cosine similarity with zero vector should be 0.0."""
        from backend.pipeline.person_analysis import _cosine_similarity
        import numpy as np

        v1 = np.array([1.0, 2.0, 3.0])
        v2 = np.array([0.0, 0.0, 0.0])
        assert _cosine_similarity(v1, v2) == 0.0

    def test_person_embedding_similarity(self):
        """Test Person class embedding similarity method."""
        from backend.pipeline.person_analysis import Person
        import numpy as np

        # Create person with initial embedding
        emb1 = np.random.randn(512)
        person = Person(1, 0.0, embedding=emb1)

        # Similar embedding should have high similarity
        emb2 = emb1 + np.random.randn(512) * 0.1
        sim = person.embedding_similarity(emb2)
        assert sim > 0.8, "Similar embedding should have high similarity"

        # Different embedding should have lower similarity
        emb3 = np.random.randn(512)
        sim3 = person.embedding_similarity(emb3)
        assert sim3 < 0.9, "Different embedding should have lower similarity"

    def test_person_mean_embedding(self):
        """Test Person mean embedding calculation."""
        from backend.pipeline.person_analysis import Person
        import numpy as np

        person = Person(1, 0.0)

        # No embeddings should return None
        assert person.mean_embedding() is None

        # Add embeddings
        emb1 = np.array([1.0, 0.0, 0.0])
        emb2 = np.array([2.0, 0.0, 0.0])
        person._embeddings = [emb1, emb2]

        mean_emb = person.mean_embedding()
        expected = np.array([1.5, 0.0, 0.0])
        assert np.allclose(mean_emb, expected)


class TestFaceEmbeddingExtractor:
    """Tests for FaceEmbeddingExtractor class."""

    def test_extractor_singleton(self):
        """Test that extractor is a singleton."""
        from backend.pipeline.person_analysis import FaceEmbeddingExtractor

        # Reset singleton for test
        FaceEmbeddingExtractor._instance = None
        FaceEmbeddingExtractor._mtcnn = None
        FaceEmbeddingExtractor._resnet = None

        e1 = FaceEmbeddingExtractor()
        e2 = FaceEmbeddingExtractor()
        assert e1 is e2

    def test_extractor_fallback_when_models_unavailable(self):
        """Test graceful fallback when FaceNet models can't load."""
        from backend.pipeline.person_analysis import FaceEmbeddingExtractor

        # Reset singleton
        FaceEmbeddingExtractor._instance = None
        FaceEmbeddingExtractor._mtcnn = None
        FaceEmbeddingExtractor._resnet = None

        extractor = FaceEmbeddingExtractor()

        # Mock _ensure_models to return False
        with patch.object(extractor, "_ensure_models", return_value=False):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            result = extractor.extract_from_image(img, {"x": 10, "y": 10, "w": 30, "h": 30})
            assert result is None