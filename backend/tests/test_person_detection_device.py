import pytest

from backend.pipeline.persons import detection


@pytest.mark.parametrize(
    ("requested", "cuda_available", "expected"),
    [
        ("auto", True, "cuda"),
        ("auto", False, "cpu"),
        ("cpu", True, "cpu"),
        ("cuda", True, "cuda"),
    ],
)
def test_resolve_device(requested, cuda_available, expected, monkeypatch):
    monkeypatch.setenv("AD_PERSON_DEVICE", requested)
    monkeypatch.setattr(detection.torch.cuda, "is_available", lambda: cuda_available)

    assert detection._resolve_device() == expected


def test_required_cuda_fails_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("AD_PERSON_DEVICE", "cuda")
    monkeypatch.setattr(detection.torch.cuda, "is_available", lambda: False)

    with pytest.raises(RuntimeError, match="cannot access CUDA"):
        detection._resolve_device()


def test_invalid_device_setting_is_rejected(monkeypatch):
    monkeypatch.setenv("AD_PERSON_DEVICE", "gpu")

    with pytest.raises(ValueError, match="AD_PERSON_DEVICE"):
        detection._resolve_device()
