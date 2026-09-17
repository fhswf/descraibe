"""Current-state stages with real decoded video and isolated model doubles."""
import hashlib
import json
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import cv2
import numpy as np
import pytest

from backend.pipeline.persons import stage_state, review_state, review_artifacts
from backend.pipeline.persons.tracking_stage import run_tracking
from backend.pipeline.persons.identity_stage import run_identities


@pytest.fixture
def staged_job(tmp_path, monkeypatch):
    calls = {"tracking": 0, "detection": 0, "detected_frames": [], "resets": [], "face_frames": [], "alignment": [], "recognition": [], "pixels": {}, "clusters": []}
    class Detector:
        def detect(self, frame):
            calls["detection"] += 1
            calls["detected_frames"].append(int(frame[0, 0, 0]) + 1)
            return [{"track_id": tid, "scene_id": 1, "bbox": (40*(tid-1), 0, 40*tid, 100), "confidence": .95} for tid in range(1, 6)]
    class Tracker:
        def __init__(self, **kwargs): calls["tracker_fps"] = kwargs["frame_rate"]
        def start_new_scene(self): calls["resets"].append(calls["tracking"])
        def update(self, persons, scene_change=False):
            calls["tracking"] += 1
            return persons
    class Faces:
        def __init__(self, **kwargs): pass
        def detect(self, frame):
            number = int(frame[0, 0, 0]) + 1
            calls["face_frames"].append(number)
            result = []
            for tid in range(1, 5):
                x = 40*(tid-1)
                crop = frame[5:35, x+5:x+35].copy()
                calls["pixels"][tid, number] = crop.copy()
                landmarks = np.full((5, 2), np.nan) if tid == 3 else np.tile([x+5+tid, 5+number], (5, 1))
                result.append({"bbox": (x+10, 10, x+30, 30), "confidence": .99 if tid != 2 else .1,
                               "crop": crop, "landmarks": landmarks, "face_crop_box": (x+5, 5, x+35, 35)})
            return result
    def align(crop, points):
        calls["alignment"].append(points.copy())
        if np.isnan(points).any():
            return None
        tid, frame = map(int, points[0])
        np.testing.assert_array_equal(crop, calls["pixels"][tid, frame])
        return np.asarray([tid, frame])
    class Recognizer:
        def __init__(self, **kwargs): pass
        def extract_embedding(self, aligned):
            tid, frame = map(int, aligned)
            calls["recognition"].append((tid, frame))
            if tid == 4 or frame == 29:
                raise RuntimeError("controlled failure")
            value = np.zeros(512, np.float32)
            value[0] = 1
            return value
        def close(self): pass
    for name, attrs in {
        "detection": {"RFDETRPersonDetector": Detector},
        "tracking": {"BytePersonTracker": Tracker, "detect_scene_change_frames": lambda path: {31}},
        "face_detection": {"RetinaFaceDetector": Faces, "align_face": align},
        "face_quality": {"check_face_quality": lambda crop, confidence: (confidence > .5, {"blur_score": 10})},
        "face_recognition": {"FaceMoERecognizer": Recognizer},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, "backend.pipeline.persons." + name, module)
    from backend.pipeline.persons import clustering
    original = clustering.run_clustering
    def cluster(**kwargs):
        calls["clusters"].append({k: v.copy() for k, v in kwargs.items()})
        return original(**kwargs)
    monkeypatch.setattr(clustering, "run_clustering", cluster)
    job = tmp_path / "job"
    job.mkdir()
    video = job / "video.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30, (200, 100))
    assert writer.isOpened()
    for number in range(61):
        writer.write(np.full((100, 200, 3), number, np.uint8))
    writer.release()
    (job / "job.json").write_text(json.dumps({"job_id": "job", "status": "idle", "video_path": str(video)}))
    return job, video, calls


def temporal(snapshot):
    return [{key: p[key] for key in ("person_id", "track_ids", "appearances", "appearances_count", "first_seen_ts", "last_seen_ts")} for p in snapshot["persons"]]


def hash_outputs(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob("*") if p.is_file()}


def test_stage1_has_no_alignment_recognition_or_clusters(staged_job):
    job, video, calls = staged_job
    result = run_tracking(video, job)
    assert calls["detection"] == calls["tracking"] == 9
    assert calls["face_frames"] == [1, 15, 29, 43, 57]
    assert calls["alignment"] == calls["recognition"] == calls["clusters"] == []
    assert len(result["tracks"]) == 5 and sum(t["quality_face_count"] for t in result["tracks"]) == 15
    assert result["identities_ready"] is False
    output = stage_state.root(job)
    assert len(list(output.rglob("*.jpg"))) == 25  # 15 quality faces + 2*5 fallbacks
    assert not list(output.rglob("persons.json"))
    assert not list(output.rglob("track_identities.csv"))
    assert not (stage_state.root(job) / "review_state.json").exists()
    assert len(result["tracks"][1]["observations"]) == 5
    assert result["tracks"][0]["observations"][0]["face_bbox"] == [10, 10, 30, 30]


def test_face_review_preserves_times_and_removes_dependent_results(staged_job):
    job, video, calls = staged_job
    first = run_tracking(video, job)
    first_id = first["tracks"][0]["observations"][0]["face_id"]
    changed = stage_state.save_faces(job, {"version": first["version"], "face_exclusions": [{"face_id": first_id, "excluded": True}]})
    assert changed["tracks"][0]["start_s"] == first["tracks"][0]["start_s"] == 0
    assert changed["tracks"][0]["end_s"] == first["tracks"][0]["end_s"] == 56/30
    clustered = run_identities(video, job)
    assert (1, 1) not in calls["recognition"]
    assert calls["clusters"][-1]["frame_numbers"].tolist() == [15, 43, 57]
    assert len(calls["clusters"][-1]["rejected_track_ids"]) == 17
    assert clustered["persons"][0]["track_ids"] == [1]
    assert clustered["persons"][0]["first_seen_ts"] == 0 and clustered["persons"][0]["last_seen_ts"] == 56/30
    assert not clustered["identities_stale"]
    original = hash_outputs(stage_state.root(job) / 'person_crops')
    # Undo invalidates downstream results; raw crops and track times remain.
    stage_state.save_faces(job, {"version": changed["version"], "face_exclusions": [{"face_id": first_id, "excluded": False}]})
    stale = review_state.current(job)
    assert not stale['identities_ready'] and stale['persons'] == []
    assert not (stage_state.root(job) / 'persons.json').exists()
    assert hash_outputs(stage_state.root(job) / 'person_crops') == original
    again = run_identities(video, job)
    assert not again["identities_stale"]
    assert calls["clusters"][-1]["frame_numbers"].tolist() == [1, 15, 43, 57]
    assert calls["detection"] == calls["tracking"] == 9  # no redetection in step 2


def test_all_faces_excluded_get_body_fallbacks_and_keep_whole_track_actions(staged_job):
    job, video, _ = staged_job
    first = run_tracking(video, job)
    changes = [{"face_id": c["face_id"], "excluded": True} for c in first["tracks"][0]["observations"]]
    stage_state.save_faces(job, {"version": first["version"], "face_exclusions": changes})
    result = run_identities(video, job)
    assert result["persons"] == [] and len(result["unassigned_tracks"]) == 5
    data = review_artifacts.load(job)
    crops = data.review_crops(1)
    assert len(crops) == 5 and all(c["evidence_status"] == "fallback" for c in crops)
    assert all(data.crop_file(c["crop_id"]).is_file() for c in crops)
    result = review_state.mutate(job, result["version"], "assign", {"changes": [{"track_id": 1, "action": "create_person"}]})
    assert result["persons"][0]["track_ids"] == [1]
    result = review_state.mutate(job, result["version"], "assign", {"changes": [{"track_id": 2, "action": "assign", "person_id": 1}]})
    assert result["persons"][0]["track_ids"] == [1, 2]
    result = review_state.mutate(job, result["version"], "delete", {"source_person_id": 1})
    assert len(result["unassigned_tracks"]) == 5


def test_restart_reads_current_files_and_rejects_changed_video(staged_job):
    job, video, _ = staged_job
    first = run_tracking(video, job)
    stage_state.save_faces(job, {"version": first["version"], "face_exclusions": [{"face_id": 1, "excluded": True}]})
    result = run_identities(video, job)
    result = review_state.mutate(job, result["version"], "metadata", {"person_id": 1, "name": "Anna", "description": "geprüft"})
    script = "import json,sys,os; from pathlib import Path; os.environ['AD_JOBS_DIR']=str(Path(sys.argv[1]).parent); from backend.session_manager import get_job; print(json.dumps(get_job('job')['person_review']))"
    process = subprocess.run([sys.executable, "-c", script, str(job)], capture_output=True, text=True, check=True)
    reloaded = json.loads(process.stdout)
    assert reloaded["persons"][0]["name"] == "Anna"
    assert reloaded["excluded_face_observations"] == [1]
    state = stage_state.read_json(stage_state.root(job) / 'persons.json')
    assert state['persons'][0]['name'] == 'Anna'
    rows, _ = stage_state.read_csv(stage_state.root(job) / 'face_observations.csv')
    assert rows[0]['excluded'] == 'True'
    assert not (stage_state.root(job) / 'review_state.json').exists()
    with video.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(review_artifacts.ReviewError):
        run_identities(video, job)
    assert temporal(review_state.current(job)) == temporal(result)


def test_combined_compatibility_entry_runs_both_without_review(staged_job):
    job, video, calls = staged_job
    from backend.pipeline.person_analysis import analyze_persons
    df, faces = analyze_persons(video, str(job))
    assert len(df) == 1 and faces
    assert calls["detection"] == calls["tracking"] == 9
    assert len(calls["clusters"]) == 1
    assert stage_state.status(job)["identities_ready"] is True
    assert not (stage_state.root(job) / "review_state.json").exists()
    assert not (stage_state.root(job) / 'runs').exists()
    for path in stage_state.root(job).rglob("*"):
        assert path.suffix not in {".npy", ".npz", ".pkl"}
        if path.suffix in {".json", ".csv"}:
            text = path.read_text(encoding="utf-8-sig")
            assert '"embedding":' not in text and ";embedding;" not in text


def test_api_stage1_crops_and_downstream_invalidation(staged_job, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app, session_manager as sm
    job, video, _ = staged_job
    monkeypatch.setattr(sm, "_BASE_DIR", job.parent)
    monkeypatch.setattr(sm, "_STORE", {})
    monkeypatch.setattr(app, "_DATASTORE", SimpleNamespace(enabled=False))
    client = TestClient(app.app)
    first = run_tracking(video, job)
    assert client.get("/api/jobs/job/person-analysis/tracking").status_code == 200
    assert client.get("/api/jobs/job").json()["persons_analyzed"] is False
    crop = first["tracks"][0]["observations"][0]
    assert client.get(f"/api/jobs/job/person-crops/{crop['crop_id']}?analysis_id={first['analysis_id']}").status_code == 200
    run_identities(video, job)
    before = client.get("/api/jobs/job/persons").json()
    res = client.patch("/api/jobs/job/person-analysis/face-review", json={"version": first["version"], "face_exclusions": [{"face_id": 1, "excluded": True}]})
    assert res.status_code == 200
    after = client.get("/api/jobs/job/persons").json()
    assert before['persons'] and after['persons'] == []
    assert not client.get("/api/jobs/job").json()["person_stages"]["identities_ready"]
    assert client.patch("/api/jobs/job/person-analysis/face-review", json={"version": first["version"], "face_exclusions": [{"face_id": 1, "excluded": False}]}).status_code == 409
    assert client.post("/api/jobs/job/track-assignments", json={"version": after["version"], "changes": [], "face_exclusions": [{"face_id": 1, "excluded": True}]}).status_code == 409


def test_failed_runs_preserve_active_outputs_and_corrections(staged_job, monkeypatch):
    job, video, _ = staged_job
    run_tracking(video, job)
    result = run_identities(video, job)
    review_state.mutate(job, result["version"], "metadata", {"person_id": 1, "name": "Anna"})
    pointer = stage_state.status(job)
    before = review_state.current(job)
    review_bytes = hash_outputs(stage_state.root(job))
    def fail(*args, **kwargs):
        raise RuntimeError("controlled stage failure")
    monkeypatch.setattr(sys.modules["backend.pipeline.persons.face_recognition"].FaceMoERecognizer, "__init__", fail)
    with pytest.raises(RuntimeError, match="controlled stage failure"):
        run_identities(video, job)
    monkeypatch.setattr(sys.modules["backend.pipeline.persons.detection"].RFDETRPersonDetector, "detect", fail)
    with pytest.raises(RuntimeError, match="controlled stage failure"):
        run_tracking(video, job)
    assert stage_state.status(job) == pointer
    assert review_state.current(job) == before
    assert hash_outputs(stage_state.root(job)) == review_bytes


def test_stage_lock_rejects_overlapping_runs_and_reviews(staged_job, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app, session_manager as sm
    job, video, _ = staged_job
    first = run_tracking(video, job)
    monkeypatch.setattr(sm, "_BASE_DIR", job.parent)
    monkeypatch.setattr(sm, "_STORE", {})
    monkeypatch.setattr(app, "_DATASTORE", SimpleNamespace(enabled=False))
    queued = []
    monkeypatch.setattr(app, "_start_worker", lambda *args: queued.append(args))
    client = TestClient(app.app)
    assert client.post("/api/jobs/job/person-analysis/identities").status_code == 200
    assert len(queued) == 1
    for route in ["person-analysis/tracking", "person-analysis/identities", "persons"]:
        assert client.post("/api/jobs/job/" + route).status_code == 409
    assert client.patch("/api/jobs/job/person-analysis/face-review", json={"version": first["version"], "face_exclusions": [{"face_id": 1, "excluded": True}]}).status_code == 409
    assert not (stage_state.root(job) / "review_state.json").exists()


def test_new_tracking_replaces_current_files_and_cached_timeline(staged_job, monkeypatch):
    job, video, calls = staged_job
    first = run_tracking(video, job)
    run_identities(video, job)
    root = stage_state.root(job)
    stage_state.atomic_write(root / 'attributes.json', {'persons': {}})
    # The first snapshot has cached the old timeline. The next tracking run
    # observes a shorter fifth track at the same storage path.
    tracker = sys.modules['backend.pipeline.persons.tracking'].BytePersonTracker
    original = tracker.update
    offset = calls['detection']
    def shorter(self, persons, scene_change=False):
        return [p for p in original(self, persons, scene_change)
                if p['track_id'] != 5 or calls['detection'] - offset <= 2]
    monkeypatch.setattr(tracker, 'update', shorter)
    second = run_tracking(video, job)
    assert second['version'] > first['version']
    assert next(t for t in second['tracks'] if t['track_id'] == 5)['end_frame'] == 8
    assert not (root / 'persons.json').exists() and not (root / 'attributes.json').exists()
    assert {p.name for p in root.iterdir()} == {
        'tracks.json', 'tracking_frames.csv', 'face_observations.csv', 'person_crops.csv', 'person_crops'}

@pytest.mark.parametrize('fps,stride', [(2, 1), (15, 3), (25, 6), (30, 7), (60, 14)])
def test_sampling_uses_original_frames_and_every_second_face_call(staged_job, fps, stride):
    job, video, calls = staged_job
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), fps, (200, 100))
    assert writer.isOpened()
    for number in range(61):
        writer.write(np.full((100, 200, 3), number, np.uint8))
    writer.release()
    progress = []
    result = run_tracking(video, job, lambda *args: progress.append(args))
    expected = list(range(1, 62, stride))
    assert calls['detected_frames'] == expected
    assert calls['tracking'] == len(expected)
    assert calls['tracker_fps'] == pytest.approx(fps / stride)
    assert calls['face_frames'] == expected[::2]
    root = stage_state.root(job)
    rows, _ = stage_state.read_csv(root / 'tracking_frames.csv')
    assert [int(r['frame_number']) for r in rows if r['source_track_id'] == '1'] == expected
    assert result['tracks'][0]['end_s'] == pytest.approx((expected[-1] - 1) / fps)
    crops, _ = stage_state.read_csv(root / 'person_crops.csv')
    assert all(int(c['frame_number']) in expected for c in crops)
    assert all(float(c['timestamp_s']) == pytest.approx((int(c['frame_number']) - 1) / fps) for c in crops)
    assert any(current == total == 61 for _, current, total in progress)


def test_cuts_on_skipped_and_selected_frames_reset_before_next_observation(staged_job, monkeypatch):
    job, video, calls = staged_job
    module = sys.modules['backend.pipeline.persons.tracking']
    monkeypatch.setattr(module, 'detect_scene_change_frames', lambda path: {3, 5, 15})
    class SceneTracker:
        def __init__(self, frame_rate):
            self.scene = 1
        def start_new_scene(self):
            self.scene += 1
            calls['resets'].append(len(calls['detected_frames']))
        def update(self, persons):
            return [dict(p, track_id=p['track_id'] + 5*(self.scene-1), scene_id=self.scene) for p in persons]
    monkeypatch.setattr(module, 'BytePersonTracker', SceneTracker)
    result = run_tracking(video, job)
    assert calls['resets'] == [1, 1, 2]  # Both skipped cuts applied before frame 8; frame 15 cut before detection.
    assert {t['scene_id'] for t in result['tracks']} == {1, 3, 4}
    assert [(t['start_frame'], t['end_frame']) for t in result['tracks'] if t['track_id'] in (1, 11, 16)] == [(1, 1), (8, 8), (15, 57)]
    assert calls['face_frames'] == [1, 15, 29, 43, 57]
