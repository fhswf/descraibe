import sys
import types

import pandas as pd

from backend.pipeline import export, gpt_description


class FakeChoiceResponse:
    def __init__(self, content):
        self.choices = [
            types.SimpleNamespace(
                message=types.SimpleNamespace(content=content)
            )
        ]


def test_describe_slots_keeps_completion_errors_out_of_text(monkeypatch, tmp_path):
    class FakeCompletions:
        def create(self, **kwargs):
            raise RuntimeError("Connection error.")

    class FakeOpenAI:
        def __init__(self, api_key):
            self.chat = types.SimpleNamespace(
                completions=FakeCompletions()
            )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    slots_df = pd.DataFrame([{"slot": 1, "start_s": 1.0, "end_s": 3.0}])
    slot_map_df = pd.DataFrame([{"slot": 1, "img_path": str(image_path)}])

    records = gpt_description.describe_slots(
        slots_df,
        slot_map_df,
        "system",
        "user",
        api_key="test-key",
    )

    assert len(records) == 1
    assert records[0]["ok"] is False
    assert records[0]["reason"] == "gpt_error"
    assert records[0]["text"] == ""
    assert records[0]["error"]["message"] == "Connection error."


def test_describe_slots_strips_api_key_whitespace(monkeypatch, tmp_path):
    seen = {}

    class FakeCompletions:
        def create(self, **kwargs):
            return FakeChoiceResponse("OK")

    class FakeOpenAI:
        def __init__(self, api_key):
            seen["api_key"] = api_key
            self.chat = types.SimpleNamespace(
                completions=FakeCompletions()
            )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    slots_df = pd.DataFrame([{"slot": 1, "start_s": 1.0, "end_s": 3.0}])
    slot_map_df = pd.DataFrame([{"slot": 1, "img_path": str(image_path)}])

    gpt_description.describe_slots(
        slots_df,
        slot_map_df,
        "system",
        "user",
        api_key="test-key\n",
    )

    assert seen["api_key"] == "test-key"


def test_describe_slots_stores_original_and_shortened_text(monkeypatch, tmp_path):
    class FakeCompletions:
        def __init__(self):
            self.responses = [
                FakeChoiceResponse("Ausfuehrliche Originalfassung mit vielen Details."),
                FakeChoiceResponse("Kurze Fassung."),
            ]

        def create(self, **kwargs):
            return self.responses.pop(0)

    class FakeOpenAI:
        def __init__(self, api_key):
            self.chat = types.SimpleNamespace(
                completions=FakeCompletions()
            )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(
        gpt_description,
        "_count_syllables",
        lambda text: 99 if text.startswith("Ausfuehrliche") else 4,
    )

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    slots_df = pd.DataFrame([{"slot": 1, "start_s": 1.0, "end_s": 3.0}])
    slot_map_df = pd.DataFrame([{"slot": 1, "img_path": str(image_path)}])

    records = gpt_description.describe_slots(
        slots_df,
        slot_map_df,
        "system",
        "user",
        api_key="test-key",
        syllables_per_second=2.0,
        syl_safety_factor=1.0,
        max_rewrite_attempts=1,
    )

    assert records[0]["ok"] is True
    assert records[0]["original_text"] == "Ausfuehrliche Originalfassung mit vielen Details."
    assert records[0]["text"] == "Kurze Fassung."
    assert records[0]["rewrite_attempts"] == 1
    assert records[0]["syllable_limit"] == 4
    assert records[0]["syllables_original"] == 99
    assert records[0]["syllables_final"] == 4


def test_describe_slots_sends_transcript_and_previous_ad_context(monkeypatch, tmp_path):
    seen_messages = []

    class FakeCompletions:
        def __init__(self):
            self.responses = [
                FakeChoiceResponse("Erste Beschreibung."),
                FakeChoiceResponse("Zweite Beschreibung."),
            ]

        def create(self, **kwargs):
            seen_messages.append(kwargs["messages"])
            return self.responses.pop(0)

    class FakeOpenAI:
        def __init__(self, api_key):
            self.chat = types.SimpleNamespace(
                completions=FakeCompletions()
            )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    slots_df = pd.DataFrame([
        {"slot": 1, "start_s": 10.0, "end_s": 12.0},
        {"slot": 2, "start_s": 20.0, "end_s": 22.0},
    ])
    slot_map_df = pd.DataFrame([
        {"slot": 1, "img_path": str(image_path)},
        {"slot": 2, "img_path": str(image_path)},
    ])
    transcript_df = pd.DataFrame([
        {"index": 1, "start_s": 18.0, "end_s": 19.0, "dur_s": 1.0, "text": "Das ist bereits im Dialog."},
    ])

    gpt_description.describe_slots(
        slots_df,
        slot_map_df,
        "system",
        "user",
        api_key="test-key",
        cut="directors",
        transcript_df=transcript_df,
    )

    assert len(seen_messages) == 2
    second_user_content = seen_messages[1][1]["content"][0]["text"]
    assert "## Kontext" in second_user_content
    assert "Audio-Transkript im Umfeld des Slots" in second_user_content
    assert "Das ist bereits im Dialog." in second_user_content
    assert "Vorherige AD-Slots" in second_user_content
    assert "Slot 1 (10.0-12.0s): Erste Beschreibung." in second_user_content
    assert "Wiederhole keine Informationen" in second_user_content
    assert "Wiederhole keine visuellen Details" in second_user_content


def test_completion_retries_transient_connection_errors(monkeypatch):
    class APIConnectionError(Exception):
        pass

    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise APIConnectionError("Connection error.")
            return "ok"

    completions = FakeCompletions()
    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=completions)
    )
    monkeypatch.setattr(gpt_description.time, "sleep", lambda seconds: None)

    result = gpt_description._completion_with_retries(client, model="gpt-5-mini-2025-08-07")

    assert result == "ok"
    assert completions.calls == 3


def test_describe_slots_aborts_after_consecutive_openai_connection_errors(monkeypatch, tmp_path):
    class APIConnectionError(Exception):
        pass

    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise APIConnectionError("Connection error.")

    completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key):
            self.chat = types.SimpleNamespace(
                completions=completions
            )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(gpt_description.time, "sleep", lambda seconds: None)

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    slots_df = pd.DataFrame([
        {"slot": 1, "start_s": 1.0, "end_s": 3.0},
        {"slot": 2, "start_s": 4.0, "end_s": 6.0},
        {"slot": 3, "start_s": 7.0, "end_s": 9.0},
    ])
    slot_map_df = pd.DataFrame([
        {"slot": 1, "img_path": str(image_path)},
        {"slot": 2, "img_path": str(image_path)},
        {"slot": 3, "img_path": str(image_path)},
    ])

    try:
        gpt_description.describe_slots(
            slots_df,
            slot_map_df,
            "system",
            "user",
            api_key="test-key",
            max_consecutive_gpt_errors=2,
        )
    except gpt_description.GPTGenerationAborted as exc:
        assert "2 consecutive OpenAI connection/API failures" in str(exc)
    else:
        raise AssertionError("Expected GPTGenerationAborted")

    assert completions.calls == 6


def test_exports_do_not_write_error_text_as_ad(tmp_path):
    records = [
        {
            "slot": 1,
            "start_s": 1.0,
            "end_s": 3.0,
            "duration_s": 2.0,
            "ok": False,
            "skipped": False,
            "reason": "gpt_error",
            "error": {"message": "Connection error."},
            "text": "[ERROR:Connection error.]",
        },
        {
            "slot": 2,
            "start_s": 4.0,
            "end_s": 6.0,
            "duration_s": 2.0,
            "ok": True,
            "skipped": False,
            "reason": "",
            "text": "Eine Person tritt ein.",
        },
    ]

    broadcast_paths = export.write_outputs(tmp_path / "broadcast", records, "broadcast")
    directors_paths = export.write_outputs(tmp_path / "directors", records, "directors")

    assert "[ERROR:Connection error.]" not in (tmp_path / "broadcast" / "AD_GESAMT_Broadcast.txt").read_text()
    assert "[ERROR:Connection error.]" not in (tmp_path / "broadcast" / "audio_description_frazier.csv").read_text()
    assert "[ERROR:Connection error.]" not in (tmp_path / "directors" / "audio_description_directors_cut.tsv").read_text()
    assert "[ERROR:Connection error.]" not in (tmp_path / "broadcast" / "Qualitätsdatei_Broadcast.txt").read_text()
    assert "Eine Person tritt ein." in (tmp_path / "broadcast" / "AD_GESAMT_Broadcast.txt").read_text()
    assert set(broadcast_paths) == {"gesamt_txt", "quality_txt", "frazier_csv"}
    assert set(directors_paths) == {"gesamt_txt", "quality_txt", "directors_tsv"}
