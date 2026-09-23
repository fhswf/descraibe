"""Preview-only seeking and current attribute-image validation (no ML models)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from backend.pipeline.persons import attribute_state, review_artifacts


class PreviewAccessTests(unittest.TestCase):
    def test_seek_matches_sequential_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'preview.avi')
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), 25, (64, 48))
            self.assertTrue(writer.isOpened())
            for index in range(100):
                writer.write(np.full((48, 64, 3), index * 2, np.uint8))
            writer.release()
            capture = cv2.VideoCapture(path)
            try:
                for number in range(1, 101):
                    ok, frame = capture.read()
                    self.assertTrue(ok)
                    if number in (1, 2, 49, 99, 100):
                        np.testing.assert_array_equal(
                            review_artifacts.read_preview_frame(path, number), frame)
            finally:
                capture.release()

    def test_seek_failures_reopen_and_read_sequentially(self):
        for failure in ('unsupported', 'position', 'decode', 'exception'):
            with self.subTest(failure=failure):
                fast, fallback = MagicMock(), MagicMock()
                fast.set.return_value = failure != 'unsupported'
                fast.read.return_value = (failure != 'decode', object())
                fast.get.return_value = 99 if failure == 'position' else 3
                if failure == 'exception':
                    fast.set.side_effect = cv2.error('seek failed')
                expected = object()
                fallback.grab.return_value = True
                fallback.retrieve.return_value = (True, expected)
                with patch.object(cv2, 'VideoCapture', side_effect=[fast, fallback]):
                    self.assertIs(review_artifacts.read_preview_frame('video', 3), expected)
                self.assertEqual(fallback.grab.call_count, 3)
                fast.release.assert_called_once()
                fallback.release.assert_called_once()

    def test_unavailable_frame_is_404_and_releases_capture(self):
        fast, fallback = MagicMock(), MagicMock()
        fast.set.return_value = False
        fallback.grab.return_value = False
        with patch.object(cv2, 'VideoCapture', side_effect=[fast, fallback]):
            with self.assertRaises(review_artifacts.ReviewError) as error:
                review_artifacts.read_preview_frame('video', 3)
        self.assertEqual(error.exception.status, 404)
        fallback.release.assert_called_once()

    def test_attribute_images_use_cached_metadata_but_fresh_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = SimpleNamespace(root=root, tracking_revision=1, assignment_revision=2,
                                   identity_revision=3, persons={1: {}}, crop_file=lambda crop: root / f'{crop}.jpg')
            payload = {'revision': 1, 'tracking_revision': 1, 'assignment_revision': 2,
                       'persons': {'1': {'images': [{'crop_id': 7}]}}}
            def save():
                (root / 'attributes.json').write_text(json.dumps(payload), encoding='utf-8')
            save()
            with patch.object(review_artifacts, 'load_for_preview', return_value=data) as cached, \
                    patch.object(review_artifacts, 'load', side_effect=AssertionError('uncached load')):
                self.assertEqual(attribute_state.image_file(root, '1:2:1', 7), root / '7.jpg')
                cached.assert_called_once()
                with self.assertRaises(review_artifacts.ReviewError) as error:
                    attribute_state.image_file(root, '1:2:1', 8)
                self.assertEqual(error.exception.status, 404)
                payload['revision'] = 2
                save()
                with self.assertRaises(review_artifacts.ReviewError):
                    attribute_state.image_file(root, '1:2:1', 7)
                self.assertEqual(attribute_state.image_file(root, '1:2:2', 7), root / '7.jpg')
                data.assignment_revision = 3
                with self.assertRaises(review_artifacts.ReviewError):
                    attribute_state.image_file(root, '1:3:2', 7)
                (root / 'attributes.json').unlink()
                with self.assertRaises(review_artifacts.ReviewError):
                    attribute_state.image_file(root, '1:3:2', 7)


if __name__ == '__main__':
    unittest.main()
