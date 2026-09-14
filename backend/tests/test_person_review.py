"""Regression tests using current pipeline manifests, with no model dependencies."""
import csv
import json
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from backend.pipeline.persons import review_artifacts as artifacts, review_state as review


@pytest.fixture
def job_dir(tmp_path):
    job = tmp_path / "job"
    root = job / "person_analysis"
    root.mkdir(parents=True)
    tracks = [{"track_id": i, "scene_id": 1, "start_s": i * 10, "end_s": i * 10 + 2} for i in range(1, 6)]
    persons = [{"person_id": 1, "name": "Anna", "segments": tracks[:2]},
               {"person_id": 2, "name": "Ben", "segments": tracks[2:3]}]
    (root / "persons.json").write_text(json.dumps({"persons": persons, "unassigned_tracks": tracks[3:]}))

    def write(name, fields, rows):
        with (root / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields.split(), delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    write("track_identities.csv", "person_id track_id assignment_source", [
        {"track_id": i, "person_id": {1: 1, 2: 1, 3: 2}.get(i, ""), "assignment_source": "automatic"} for i in range(1, 6)])
    crops = []
    for tid in range(1, 5):
        for frame in range(12):
            relative = f"person_crops/track_{tid:04d}/frame_{frame:08d}.jpg"
            path = root / relative
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(b"test-jpeg")
            crops.append(dict(crop_id=len(crops) + 1, track_id=tid, scene_id=1, frame_number=frame,
                              timestamp_s=tid * 10 + frame / 6, x1=0, y1=0, x2=100, y2=200,
                              crop_path=relative))
    write("person_crops.csv", "crop_id track_id scene_id frame_number timestamp_s x1 y1 x2 y2 crop_path", crops)
    write("face_observations.csv", "face_id person_crop_path face_x1 face_y1 face_x2 face_y2 face_usable face_confidence alignment_ok embedding_created", [
        dict(face_id=1, person_crop_path=crops[0]["crop_path"], face_x1=10, face_y1=20, face_x2=40,
             face_y2=60, face_usable=True, face_confidence=.9, alignment_ok=True, embedding_created=True)])
    return job


def change(job, changes):
    return review.mutate(job, review.current(job)["version"], "assign", {"changes": changes})


def test_automatic_fallback_and_distributed_samples(job_dir):
    result = review.current(job_dir)
    assert len(result["persons"]) == 2
    assert [t["track_id"] for t in result["unassigned_tracks"]] == [4, 5]
    assert not (job_dir / "person_analysis" / review.FILENAME).exists()
    data = artifacts.load(job_dir)
    crops = data.sample(1)
    assert len(crops) == 8 and crops[0]["frame_number"] == 0 and crops[-1]["frame_number"] == 11
    assert crops[0]["face_bbox"] == [10, 20, 40, 60]
    assert data.sample(5) == []


def test_whole_track_recomputes_every_field_and_preserves_originals(job_dir):
    root = job_dir / "person_analysis"
    originals = {name: (root / name).read_bytes() for name in artifacts.FILES}
    result = change(job_dir, [{"track_id": 1, "action": "assign", "person_id": 2}])
    people = {p["person_id"]: p for p in result["persons"]}
    assert people[1]["track_ids"] == [2]
    assert people[1]["appearances"] == [{"start_s": 20, "end_s": 22}]
    assert people[1]["appearances_count"] == 1
    assert (people[1]["first_seen_ts"], people[1]["last_seen_ts"]) == (20, 22)
    assert people[1]["representative_crop_id"] == 13
    assert people[2]["track_ids"] == [1, 3]
    assert people[2]["appearances_count"] == 2
    assert (people[2]["first_seen_ts"], people[2]["last_seen_ts"]) == (10, 32)
    assert people[2]["representative_crop_id"] == 1
    assert result["faces"][0]["person_id"] == 2
    assert people[2]["representative_crop"].startswith("person_analysis/person_crops/")
    assert review.current(job_dir) == result
    assert originals == {name: (root / name).read_bytes() for name in artifacts.FILES}
    saved = (root / review.FILENAME).read_text()
    assert "embedding" not in saved.lower() and "/api/" not in saved


def test_batch_create_unassign_and_cropless_track(job_dir):
    result = change(job_dir, [{"track_id": 4, "action": "create_person"}, {"track_id": 2, "action": "unassign"}])
    assert result["revision"] == 1
    assert {t["track_id"] for t in result["unassigned_tracks"]} == {2, 5}
    result = change(job_dir, [{"track_id": 5, "action": "assign", "person_id": 3}])
    assert next(p for p in result["persons"] if p["person_id"] == 3)["track_ids"] == [4, 5]


def test_metadata_merge_delete_and_monotonic_ids(job_dir):
    result = review.mutate(job_dir, review.current(job_dir)["version"], "metadata", {"person_id": 2, "name": "Berta", "description": "Beschreibung"})
    result = review.mutate(job_dir, result["version"], "merge", {"source_person_id": 1, "target_person_id": 2})
    assert result["persons"][0]["track_ids"] == [1, 2, 3]
    assert result["persons"][0]["name"] == "Berta"
    assert result["persons"][0]["description"] == "Beschreibung"
    result = review.mutate(job_dir, result["version"], "delete", {"source_person_id": 2})
    assert result["persons"] == [] and len(result["unassigned_tracks"]) == 5
    result = change(job_dir, [{"track_id": 5, "action": "create_person"}])
    assert result["persons"][0]["person_id"] == 3
    assert result["persons"][0]["representative_crop"] is None


@pytest.mark.parametrize("invalid", [
    {"track_id": 999, "action": "unassign"}, {"track_id": 2, "action": "split"},
    {"track_id": 2, "action": "assign", "person_id": 999}, {"track_id": True, "action": "unassign"},
    {"track_id": 1, "action": "unassign"}, {"track_id": 2, "action": "assign", "person_id": True},
])
def test_invalid_batch_is_atomic(job_dir, invalid):
    with pytest.raises(artifacts.ReviewError):
        change(job_dir, [{"track_id": 1, "action": "unassign"}, invalid])
    assert review.current(job_dir)["revision"] == 0
    assert not (job_dir / "person_analysis" / review.FILENAME).exists()


def test_stale_version_and_disk_failure_keep_saved_state(job_dir, monkeypatch):
    old = review.current(job_dir)["version"]
    result = change(job_dir, [{"track_id": 1, "action": "unassign"}])
    with pytest.raises(artifacts.ReviewError) as error:
        review.mutate(job_dir, old, "assign", {"changes": [{"track_id": 2, "action": "unassign"}]})
    assert error.value.status == 409
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(review.os, "replace", fail)
    with pytest.raises(artifacts.ReviewError) as error:
        change(job_dir, [{"track_id": 2, "action": "unassign"}])
    assert error.value.status == 500 and review.current(job_dir) == result
    assert not list((job_dir / "person_analysis").glob("*.tmp"))


def test_corrupt_and_changed_analysis_never_silently_reset(job_dir):
    change(job_dir, [{"track_id": 1, "action": "unassign"}])
    path = job_dir / "person_analysis" / review.FILENAME
    original = path.read_bytes()
    path.write_text("{")
    with pytest.raises(artifacts.ReviewError):
        review.current(job_dir)
    path.write_bytes(original)
    manifest = job_dir / "person_analysis" / "persons.json"
    manifest.write_text(manifest.read_text() + " ")
    with pytest.raises(artifacts.ReviewError):
        review.current(job_dir)


def test_crop_paths_cannot_escape(job_dir):
    data = artifacts.load(job_dir)
    data.crops[1]["crop_path"] = "../job.json"
    (job_dir / "job.json").write_text("secret")
    with pytest.raises(artifacts.ReviewError):
        data.crop_file(1)
    with pytest.raises(artifacts.ReviewError):
        data.crop_file(999)


@pytest.fixture
def api(job_dir, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app, session_manager as sm
    monkeypatch.setattr(sm, "_BASE_DIR", job_dir.parent)
    monkeypatch.setattr(sm, "_STORE", {})
    (job_dir / "job.json").write_text(json.dumps({"job_id": "job", "status": "idle"}))
    monkeypatch.setattr(app, "_DATASTORE", SimpleNamespace(enabled=False))
    return TestClient(app.app), sm, app


def test_api_batch_and_restart_ignore_stale_parquet(api, job_dir):
    client, sm, _ = api
    first = client.get("/api/jobs/job/persons").json()
    response = client.post("/api/jobs/job/track-assignments", json={"version": first["version"], "changes": [{"track_id": 4, "action": "create_person"}]})
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1
    assert client.post("/api/jobs/job/track-assignments", json={"version": first["version"], "changes": [{"track_id": 1, "action": "unassign"}]}).status_code == 409
    import pandas as pd
    pd.DataFrame([{"person_id": 999, "name": "stale"}]).to_parquet(job_dir / "persons_df.parquet")
    sm._STORE.clear()
    restored = client.get("/api/jobs/job/persons").json()
    assert restored["version"] == response.json()["version"]
    assert len(restored["persons"]) == 3
    # A fresh interpreter also reconstructs the exact same canonical projection.
    script = "import json,sys,os; from pathlib import Path; os.environ['AD_JOBS_DIR']=str(Path(sys.argv[1]).parent); from backend.session_manager import get_job; print(json.dumps(get_job('job')['person_review']))"
    process = subprocess.run([sys.executable, "-c", script, str(job_dir)], capture_output=True, text=True, check=True)
    assert json.loads(process.stdout)["version"] == restored["version"]


def test_api_crop_routes_and_legacy_routes(api):
    client, _, _ = api
    assert client.get("/api/jobs/job/persons/1/tracks").json()["tracks"][0]["track_id"] == 1
    assert len(client.get("/api/jobs/job/tracks/unassigned").json()["tracks"]) == 2
    assert len(client.get("/api/jobs/job/tracks/1/crops?limit=999").json()["crops"]) == 1
    assert len(client.get("/api/jobs/job/tracks/4/crops").json()["crops"]) == 5
    assert client.get("/api/jobs/job/person-crops/1").content == b"test-jpeg"
    assert client.get("/api/jobs/job/person-crops/1?analysis_id=old").status_code == 409
    assert client.get("/api/jobs/job/person-crops/999").status_code == 404
    assert client.get("/api/jobs/job/persons/merge-suggestions").status_code == 200
    assert client.get("/api/jobs/job/persons/1/similar-faces").status_code == 200
    assert client.post("/api/jobs/job/faces/merge", json={"face_ids": [1], "target_person_id": 2}).status_code == 409


def test_api_database_failure_does_not_lose_correction(api):
    client, _, app = api
    first = client.get("/api/jobs/job/persons").json()
    app._DATASTORE = SimpleNamespace(enabled=True, store_persons=lambda *args: False)
    response = client.post("/api/jobs/job/track-assignments", json={"version": first["version"], "changes": [{"track_id": 1, "action": "unassign"}]})
    assert response.status_code == 200
    assert response.json()["database_sync"] == "pending"
    assert client.get("/api/jobs/job/persons").json()["revision"] == 1


def test_concurrent_saves_have_one_winner_and_running_job_rejects(api):
    client, sm, _ = api
    version = client.get("/api/jobs/job/persons").json()["version"]
    def save(tid):
        return client.post("/api/jobs/job/track-assignments", json={"version": version, "changes": [{"track_id": tid, "action": "unassign"}]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, [1, 2])) == [200, 409]
    sm._STORE["job"]["status"] = "running"
    assert save(3) == 409


def test_database_projection_normalizes_json_and_updates_both_times(tmp_path):
    import logging
    from unittest.mock import MagicMock
    from backend.db.store import DataStore
    store = DataStore("", tmp_path, logging.getLogger("review-test"))
    driver = MagicMock()
    store._psycopg = driver
    store.database_url = "postgresql://test"
    cursor = driver.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    assert store.store_persons("job", [{"person_id": 1, "name": "Anna", "first_seen_ts": 10,
        "last_seen_ts": 22, "attributes": '{"coat":"blue"}',
        "appearances": '[{"start_s":10,"end_s":22}]'}])
    calls = cursor.execute.call_args_list
    assert "INSERT INTO jobs" in calls[0].args[0]
    sql, params = next(call.args for call in calls if "INSERT INTO job_persons" in call.args[0])
    assert "first_seen_ts = EXCLUDED.first_seen_ts" in sql
    assert "last_seen_ts = EXCLUDED.last_seen_ts" in sql
    assert any(isinstance(v, str) and json.loads(v) == {"coat": "blue"} for v in params if isinstance(v, str) and v.startswith("{"))
    assert any(isinstance(v, str) and isinstance(json.loads(v), list) for v in params if isinstance(v, str) and v.startswith("["))
    driver.connect.side_effect = OSError("offline")
    assert store.store_persons("job", []) is False


def test_corrupt_review_clears_cached_projection(api, job_dir):
    client, sm, _ = api
    client.get("/api/jobs/job/persons")
    (job_dir / "person_analysis" / review.FILENAME).write_text("{")
    assert client.get("/api/jobs/job/persons").status_code == 409
    assert "person_review" not in sm.get_job("job")
    assert sm.get_job("job")["persons_df"] is None
