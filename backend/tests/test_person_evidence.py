"""Review evidence/exclusions, independent of model/GPU dependencies."""
import csv
import json
import subprocess
import sys

import pytest

from backend.tests.test_person_review import job_dir, api  # noqa: F401 - shared fixtures
from backend.pipeline.persons import review_state as review, review_artifacts as artifacts


def exclude(job, value=True, changes=None):
    return review.mutate(job, review.current(job)["version"], "assign", {
        "changes": changes or [], "face_exclusions": [{"face_id": 1, "excluded": value}]})


def temporal(result):
    keys = ("person_id", "track_ids", "appearances", "appearances_count", "first_seen_ts", "last_seen_ts")
    return [{k: p[k] for k in keys} for p in result["persons"]]


def test_exclusion_restore_preserves_times_and_originals(job_dir):
    root = job_dir / "person_analysis"
    before = {name: (root / name).read_bytes() for name in artifacts.FILES}
    initial = review.current(job_dir)
    result = exclude(job_dir)
    assert temporal(result) == temporal(initial)
    assert result["persons"][0]["representative_crop_id"] != 1
    assert result["persons"][0]["valid_identity_crop_ids"] == []
    assert result["excluded_face_observations"] == [1]
    assert artifacts.load(job_dir).review_crops(1, {1})[0]["excluded"] is True
    assert review.current(job_dir) == result
    restored = exclude(job_dir, False)
    assert temporal(restored) == temporal(initial)
    assert restored["persons"][0]["representative_crop_id"] == 1
    assert restored["persons"][0]["valid_identity_crop_ids"] == [1]
    assert before == {name: (root / name).read_bytes() for name in artifacts.FILES}
    saved = json.loads((root / review.FILENAME).read_text())
    assert saved["schema_version"] == 2
    assert saved["excluded_face_observations"] == []
    assert set(saved) == {"schema_version", "analysis_id", "revision", "next_person_id", "assignments", "persons", "excluded_face_observations"}


def test_exclusion_follows_observation_through_track_move(job_dir):
    result = exclude(job_dir, changes=[{"track_id": 1, "action": "assign", "person_id": 2}])
    person = next(p for p in result["persons"] if p["person_id"] == 2)
    assert person["track_ids"] == [1, 3]
    assert person["first_seen_ts"] == 10 and person["last_seen_ts"] == 32
    assert 1 not in person["valid_identity_crop_ids"]
    assert person["representative_crop_id"] != 1
    assert result["excluded_face_observations"] == [1]


@pytest.mark.parametrize("bad", [{"face_id": 999, "excluded": True}, {"face_id": True, "excluded": True},
    {"face_id": 1, "excluded": "true"}, {"face_id": 1, "excluded": True, "person_id": 2}])
def test_invalid_exclusion_rolls_back_entire_batch(job_dir, bad):
    initial = review.current(job_dir)
    with pytest.raises(artifacts.ReviewError):
        review.mutate(job_dir, initial["version"], "assign", {"changes": [{"track_id": 1, "action": "unassign"}], "face_exclusions": [bad]})
    assert review.current(job_dir) == initial


def test_v1_state_is_migrated_without_losing_assignments(job_dir):
    result = exclude(job_dir)
    path = job_dir / "person_analysis" / review.FILENAME
    state = json.loads(path.read_text())
    state["schema_version"] = 1
    state.pop("excluded_face_observations")
    path.write_text(json.dumps(state))
    loaded = review.current(job_dir)
    assert temporal(loaded) == temporal(result)
    assert loaded["excluded_face_observations"] == []
    exclude(job_dir)
    assert json.loads(path.read_text())["schema_version"] == 2


def test_legacy_success_is_not_invented(job_dir):
    path = job_dir / "person_analysis" / "face_observations.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    for row in rows:
        row.pop("embedding_created")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    result = review.current(job_dir)
    assert result["legacy_evidence"] is True
    assert result["tracks"][0]["facemoe_observation_count"] == 0
    assert result["persons"][0]["valid_identity_crop_ids"] == []
    assert artifacts.load(job_dir).review_crops(1, set())[0]["evidence_status"] == "legacy_unverified"


def test_api_exclusions_reload_and_restore(api, job_dir):
    client, sm, _ = api
    before = client.get("/api/jobs/job/persons").json()
    response = client.post("/api/jobs/job/track-assignments", json={"version": before["version"], "changes": [], "face_exclusions": [{"face_id": 1, "excluded": True}]})
    assert response.status_code == 200
    assert temporal(response.json()) == temporal(before)
    sm._STORE.clear()
    reloaded = client.get("/api/jobs/job/persons").json()
    assert reloaded["excluded_face_observations"] == [1]
    script = "import json,sys,os; from pathlib import Path; os.environ['AD_JOBS_DIR']=str(Path(sys.argv[1]).parent); from backend.session_manager import get_job; print(json.dumps(get_job('job')['person_review']))"
    process = subprocess.run([sys.executable, "-c", script, str(job_dir)], capture_output=True, text=True, check=True)
    restarted = json.loads(process.stdout)
    assert restarted["excluded_face_observations"] == [1]
    assert temporal(restarted) == temporal(before)
    assert client.get("/api/jobs/job/tracks/1/crops").json()["crops"][0]["excluded"] is True
    response = client.post("/api/jobs/job/track-assignments", json={"version": reloaded["version"], "changes": [], "face_exclusions": [{"face_id": 1, "excluded": False}]})
    assert response.status_code == 200
    assert response.json()["excluded_face_observations"] == []


def test_missing_v2_exclusions_are_not_silently_reset(job_dir):
    exclude(job_dir)
    path = job_dir / "person_analysis" / review.FILENAME
    state = json.loads(path.read_text())
    state.pop("excluded_face_observations")
    path.write_text(json.dumps(state))
    with pytest.raises(artifacts.ReviewError):
        review.current(job_dir)
