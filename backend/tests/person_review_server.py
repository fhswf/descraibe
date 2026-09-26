"""Loopback-only Playwright fixture. Never opens existing production jobs.

python backend/tests/person_review_server.py --build <frontend-build> --data-dir <scratch> [--review-only]
node backend/tests/person_stages_browser.cjs http://127.0.0.1:5181
With --review-only, use person_review_browser.cjs instead.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--port", default=5181, type=int)
    args = parser.parse_args()
    base = args.data_dir / ("review-fixture-" + uuid.uuid4().hex[:8])
    base.mkdir(parents=True)
    os.environ.update(AD_JOBS_DIR=str(base), AD_USER_CONFIG_DIR=str(base / "users"), AD_DATABASE_URL="", OIDC_ISSUER_URL="")
    import pytest
    patches = pytest.MonkeyPatch()
    tests = Path(__file__).parent
    if args.review_only:
        job = runpy.run_path(str(tests / "test_person_review.py"))["job_dir"].__wrapped__(base)
        (job / "job.json").write_text(json.dumps({"job_id": "job", "status": "idle"}))
        import cv2
        import numpy as np
        image = np.full((200, 100, 3), [85, 55, 52], np.uint8)
        image[20:60, 10:40] = [153, 184, 222]
        _, jpeg = cv2.imencode(".jpg", image)
        for crop in (job / "person_analysis" / "person_crops").rglob("*.jpg"):
            crop.write_bytes(jpeg.tobytes())
    else:
        job, _, _ = runpy.run_path(str(tests / "test_person_stages.py"))["staged_job"].__wrapped__(base, patches)
        from backend.pipeline.persons import attribute_stage
        from backend.pipeline.persons.qwen_attributes import FIELDS
        class QwenDouble:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def predict(self, pid, paths):
                return json.dumps({field: "Testwert" for field in FIELDS})
        patches.setattr(attribute_stage, "QwenAttributes", QwenDouble)
    from backend.app import app
    from starlette.staticfiles import StaticFiles
    import uvicorn
    app.mount("/", StaticFiles(directory=args.build, html=True), name="test_frontend")
    print(f"Isolated fixture: {job}", flush=True)
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        patches.undo()


if __name__ == "__main__":
    main()
