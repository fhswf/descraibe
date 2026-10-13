"""Current attribute-image validation (no ML models)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.pipeline.persons import attribute_state, review_artifacts


class PreviewAccessTests(unittest.TestCase):
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
