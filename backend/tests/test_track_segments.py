"""Current segment ownership, observed times, invalidation and restart."""
import csv
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from test_person_stages import staged_job, hash_outputs
from backend.pipeline.persons import stage_state, review_state, review_artifacts, track_segments
from backend.pipeline.persons.tracking_stage import run_tracking
from backend.pipeline.persons.identity_stage import run_identities


def split(job, snapshot, tid=1, frame=29):
    return stage_state.save_faces(job, {"version": snapshot["version"], "track_changes": [{"action": "split", "track_id": tid, "before_frame": frame}]})


def test_split_partitions_faces_and_exact_tracking_times(staged_job):
    job, video, _ = staged_job
    first = run_tracking(video, job)
    original = hash_outputs(stage_state.root(job) / 'person_crops')
    result = split(job, first)
    segments = [t for t in result["tracks"] if t["source_track_id"] == 1]
    assert [t["track_id"] for t in segments] == [6, 7]
    assert [(t["start_frame"], t["end_frame"]) for t in segments] == [(1, 22), (29, 57)]
    assert [(t["start_s"], t["end_s"]) for t in segments] == [(0, 21/30), (28/30, 56/30)]
    ids = [c["face_id"] for t in segments for c in t["observations"]]
    assert len(ids) == len(set(ids)) == 5
    assert sorted(ids) == sorted(c["face_id"] for c in first["tracks"][0]["observations"])
    assert hash_outputs(stage_state.root(job) / 'person_crops') == original

def test_split_options_start_only_from_second_visible_observation(staged_job):
    job, video, _ = staged_job

    snapshot = run_tracking(video, job)

    track = next(t for t in snapshot["tracks"] if t["track_id"] == 1)

    visible_frames = sorted(
        crop["frame_number"]
        for crop in track["observations"]
    )
    split_frames = [
        option["before_frame"]
        for option in track["split_options"]
    ]

    assert len(visible_frames) >= 2

    # Die erste sichtbare Beobachtung darf keine Split-Option anbieten.
    assert visible_frames[0] not in split_frames

    # Ab der zweiten sichtbaren Beobachtung darf gesplittet werden.
    assert visible_frames[1] in split_frames

def test_split_at_tracking_gap_uses_real_last_frame(staged_job, monkeypatch):
    job, video, calls = staged_job
    tracker = sys.modules["backend.pipeline.persons.tracking"].BytePersonTracker
    original = tracker.update
    def with_gap(self, persons, scene_change=False):
        rows = original(self, persons, scene_change)
        return [p for p in rows if p["track_id"] != 1 or not 20 <= calls["detected_frames"][-1] <= 28]
    monkeypatch.setattr(tracker, "update", with_gap)
    first = run_tracking(video, job)
    result = split(job, first)
    segments = [t for t in result["tracks"] if t["source_track_id"] == 1]
    assert [(t["start_frame"], t["end_frame"]) for t in segments] == [(1, 15), (29, 57)]
    assert segments[0]["end_s"] == 14/30  # Last actual observation; do not fill missing frames.
    with pytest.raises(review_artifacts.ReviewError):
        split(job, result, tid=6, frame=25)


def test_cluster_uses_segments_and_undo_invalidates_identity_review(staged_job):
    job, video, calls = staged_job
    first = run_tracking(video, job)
    automatic = run_identities(video, job)
    changed = split(job, first)
    assert automatic['persons'] and review_state.current(job)['persons'] == []
    assert not review_state.current(job)['identities_ready']
    result = run_identities(video, job)
    assert calls["clusters"][-1]["track_ids"].tolist() == [6, 6, 7, 7]
    assert result["persons"][0]["track_ids"] == [6, 7]
    assert result["persons"][0]["appearances_count"] == 2
    assert calls["detection"] == 9
    result = review_state.mutate(job, result["version"], "assign", {"changes": [{"track_id": 7, "action": "create_person"}]})
    frozen = result["persons"]
    undone = stage_state.save_faces(job, {"version": changed["version"], "track_changes": [{"action": "undo_split", "source_track_id": 1}]})
    assert len(undone["tracks"]) == 5
    assert frozen and review_state.current(job)['persons'] == []
    assert not review_state.current(job)['identities_ready']
    rerun = run_identities(video, job)
    assert rerun["persons"][0]["track_ids"] == [1]
    assert not rerun["identities_stale"]


def test_nested_splits_undo_and_face_exclusions_survive_restart(staged_job):
    job, video, _ = staged_job
    first = run_tracking(video, job)
    changed = split(job, first)
    changed = split(job, changed, tid=7, frame=43)
    assert [t["track_id"] for t in changed["tracks"] if t["source_track_id"] == 1] == [6, 8, 9]
    changed = stage_state.save_faces(job, {"version": changed["version"], "face_exclusions": [{"face_id": 1, "excluded": True}]})
    script = "import sys,json; from backend.pipeline.persons.stage_state import face_snapshot; print(json.dumps(face_snapshot(sys.argv[1])))"
    reloaded = json.loads(subprocess.run([sys.executable, "-c", script, str(job)], capture_output=True, text=True, check=True).stdout)
    assert reloaded == changed
    undone = stage_state.save_faces(job, {"version": changed["version"], "track_changes": [{"action": "undo_split", "source_track_id": 1}]})
    assert undone["excluded_face_observations"] == [1]
    resplit = split(job, undone)
    assert [t["track_id"] for t in resplit["tracks"] if t["source_track_id"] == 1] == [10, 11]


def test_faceless_segments_get_up_to_five_fallbacks_and_no_review_jpegs(staged_job, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app, session_manager as sm
    job, video, _ = staged_job
    first = run_tracking(video, job)
    before = hash_outputs(stage_state.root(job) / 'person_crops')
    changed = split(job, first, tid=5)
    segments = [t for t in changed["tracks"] if t["source_track_id"] == 5]
    assert [len(t["observations"]) for t in segments] == [4, 5]
    for segment in segments:
        frames = [c['frame_number'] for c in segment['observations']]
        assert len(set(frames)) == min(5, segment["observation_count"])
        assert frames[0] == segment['start_frame'] and frames[-1] == segment['end_frame']
        assert max(b - a for a, b in zip(frames, frames[1:])) <= 7
    assert all(c["face_id"] is None and c["preview_frame"] for t in segments for c in t["observations"])
    monkeypatch.setattr(sm, "_BASE_DIR", job.parent)
    monkeypatch.setattr(sm, "_STORE", {})
    monkeypatch.setattr(app, "_DATASTORE", SimpleNamespace(enabled=False))
    client = TestClient(app.app)
    crop = segments[0]["observations"][0]
    url = f"/api/jobs/job/person-analysis/tracking-frame/5/{crop['frame_number']}?analysis_id={changed['analysis_id']}"
    assert client.get(url).status_code == 200
    assert client.get(url).headers["content-type"] == "image/jpeg"
    assert hash_outputs(stage_state.root(job) / 'person_crops') == before
    run_identities(video, job)
    data = review_artifacts.load(job)
    for track in segments:
        crops = data.review_crops(track["track_id"])
        assert len(crops) == min(5, track["observation_count"])
        assert len({c["frame_number"] for c in crops}) == len(crops)
        assert all(track["start_frame"] <= c["frame_number"] <= track["end_frame"] for c in crops)
        assert all(data.crop_file(c["crop_id"]).is_file() for c in crops)


def test_split_can_leave_child_without_saved_face(staged_job):
    job, video, _ = staged_job
    first = run_tracking(video, job)
    # Only one tracking frame in the first child; keep one rather than duplicate five.
    changed = split(job, first, tid=1, frame=8)
    changed = stage_state.save_faces(job, {"version": changed["version"], "face_exclusions": [{"face_id": 1, "excluded": True}]})
    result = run_identities(video, job)
    data = review_artifacts.load(job)
    assert len(data.review_crops(6)) == 1
    assert data.review_crops(6)[0]["evidence_status"] == "fallback"
    assert next(t for t in result["tracks"] if t["track_id"] == 6)["start_s"] == 0


def test_incomplete_tracking_is_rejected_without_migration(staged_job):
    job, video, _ = staged_job
    first = run_tracking(video, job)
    # Simulate the earlier two-stage format inside this disposable fixture only.
    root = review_artifacts.load_tracking(job).root
    (root / track_segments.TIMELINE).unlink()
    before = hash_outputs(root)
    with pytest.raises(review_artifacts.ReviewError):
        stage_state.face_snapshot(job)
    with pytest.raises(review_artifacts.ReviewError):
        split(job, first)
    assert hash_outputs(root) == before


def test_invalid_batch_does_not_save_face_change_or_split(staged_job):
    job, video, _ = staged_job
    first = run_tracking(video, job)
    for frame in (0, 1, 62):
        with pytest.raises(review_artifacts.ReviewError):
            stage_state.save_faces(job, {"version": first["version"], "face_exclusions": [{"face_id": 1, "excluded": True}],
                "track_changes": [{"action": "split", "track_id": 1, "before_frame": frame}]})
    assert not (stage_state.root(job) / "review_state.json").exists()


def test_sparse_split_and_undo_preserve_exact_observations(staged_job):
    job, video, _ = staged_job
    first = run_tracking(video, job)
    root = stage_state.root(job)
    timeline_before = (root / track_segments.TIMELINE).read_bytes()
    changed = split(job, first)
    segments = [t for t in changed['tracks'] if t['source_track_id'] == 1]
    assert [t['observation_count'] for t in segments] == [4, 5]
    with pytest.raises(review_artifacts.ReviewError):
        split(job, changed, tid=6, frame=9)  # Skipped frame cannot be a split boundary.
    restored = stage_state.save_faces(job, {'version': changed['version'], 'track_changes': [
        {'action': 'undo_split', 'source_track_id': 1}]})
    original_track = first['tracks'][0]
    restored_track = next(t for t in restored['tracks'] if t['track_id'] == 1)
    for field in ('start_frame', 'end_frame', 'start_s', 'end_s', 'observation_count'):
        assert restored_track[field] == original_track[field]
    assert (root / track_segments.TIMELINE).read_bytes() == timeline_before
