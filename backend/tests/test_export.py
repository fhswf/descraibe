"""Tests for backend.pipeline.export – output file writers."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.pipeline.export import (
    _clean_line,
    _frame_time,
    _record_note,
    _srt_time,
    write_outputs,
)


# ── _srt_time ──────────────────────────────────────────────────────────────────

class TestSrtTime:
    def test_zero(self):
        assert _srt_time(0.0) == "00:00:00,000"

    def test_one_second(self):
        assert _srt_time(1.0) == "00:00:01,000"

    def test_one_hour(self):
        assert _srt_time(3600.0) == "01:00:00,000"

    def test_milliseconds_rounded(self):
        assert _srt_time(1.234) == "00:00:01,234"
        # Note: int(round()) uses banker's rounding (round half to even)
        # so 1.2345 stays at 1234ms, not 1235ms
        assert _srt_time(1.2345) == "00:00:01,234"

    def test_negative_clamped_to_zero(self):
        assert _srt_time(-5.0) == "00:00:00,000"

    def test_large_value(self):
        assert _srt_time(3723.456) == "01:02:03,456"


# ── _frame_time ────────────────────────────────────────────────────────────────

class TestFrameTime:
    def test_zero(self):
        assert _frame_time(0.0, fps=25) == "00:00:00.00"

    def test_one_second(self):
        assert _frame_time(1.0, fps=25) == "00:00:01.00"

    def test_fractional_frame_rounded(self):
        # At 25 fps, frame 24 is at 0.96s
        assert _frame_time(0.96, fps=25) == "00:00:00.24"
        # 0.97 rounds to frame 24 as well
        assert _frame_time(0.97, fps=25) == "00:00:00.24"
        # 0.98 rounds to frame 24 due to banker's rounding (0.5 rounds to even)
        # 0.98s = 24.5 frames, rounds to 24
        assert _frame_time(0.98, fps=25) == "00:00:00.24"
        # 1.02s = 25.5 frames, rounds to 26 (banker's rounding: 25.5→26)
        # 26 frames = 1 second + 1 frame
        assert _frame_time(1.02, fps=25) == "00:00:01.01"

    def test_negative_clamped_to_zero(self):
        assert _frame_time(-5.0, fps=25) == "00:00:00.00"

    def test_custom_fps(self):
        # At 30 fps, frame 30 is at 1.0s
        assert _frame_time(1.0, fps=30) == "00:00:01.00"
        # Frame 15 at 30fps = 0.5s
        assert _frame_time(0.5, fps=30) == "00:00:00.15"


# ── _clean_line ────────────────────────────────────────────────────────────────

class TestCleanLine:
    def test_empty_string(self):
        assert _clean_line("") == ""

    def test_whitespace_collapsed(self):
        assert _clean_line("  hello   world  ") == "hello world"

    def test_newlines_replaced_with_space(self):
        assert _clean_line("hello\nworld") == "hello world"

    def test_tabs_replaced_with_space(self):
        assert _clean_line("hello\tworld") == "hello world"

    def test_none_returns_empty(self):
        assert _clean_line(None) == ""


# ── _record_note ───────────────────────────────────────────────────────────────

class TestRecordNote:
    def test_error_dict_returns_message(self):
        rec = {"error": {"message": "Connection refused"}}
        assert _record_note(rec) == "Connection refused"

    def test_error_dict_without_message(self):
        rec = {"error": {}}
        assert _record_note(rec) == ""

    def test_reason_field_used_when_no_error(self):
        rec = {"reason": "gpt_error"}
        assert _record_note(rec) == "gpt_error"

    def test_reason_with_whitespace(self):
        rec = {"reason": "  gpt_error  "}
        assert _record_note(rec) == "gpt_error"

    def test_empty_record(self):
        rec = {}
        assert _record_note(rec) == ""

    def test_error_takes_precedence_over_reason(self):
        rec = {"error": {"message": "API error"}, "reason": "fallback"}
        assert _record_note(rec) == "API error"


# ── write_outputs ───────────────────────────────────────────────────────────────

class TestWriteOutputsBroadcast:
    @pytest.fixture
    def records(self):
        return [
            {
                "slot": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "duration_s": 2.0,
                "ok": True,
                "skipped": False,
                "reason": "",
                "text": "Eine Person betritt den Raum.",
            },
            {
                "slot": 2,
                "start_s": 5.0,
                "end_s": 7.0,
                "duration_s": 2.0,
                "ok": True,
                "skipped": False,
                "reason": "",
                "text": "Die Tür schließt sich.",
            },
        ]

    def test_broadcast_creates_gesamt_txt(self, tmp_path, records):
        paths = write_outputs(tmp_path / "run", records, "broadcast")

        gesamt = (tmp_path / "run" / "AD_GESAMT_Broadcast.txt").read_text()
        assert "Eine Person betritt den Raum." in gesamt
        assert "Die Tür schließt sich." in gesamt
        assert "00:00:00,000 --> 00:00:02,000" in gesamt

    def test_broadcast_creates_quality_file(self, tmp_path, records):
        write_outputs(tmp_path / "run", records, "broadcast")

        quality = (tmp_path / "run" / "Qualitätsdatei_Broadcast.txt").read_text()
        assert "Slot" in quality
        assert "Eine Person betritt den Raum." in quality

    def test_broadcast_creates_frazier_csv(self, tmp_path, records):
        write_outputs(tmp_path / "run", records, "broadcast")

        csv = (tmp_path / "run" / "audio_description_frazier.csv").read_text()
        assert "Position;Start;End;Text" in csv
        assert "Eine Person betritt den Raum." in csv

    def test_skipped_slot_not_in_output(self, tmp_path):
        records = [
            {
                "slot": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "duration_s": 2.0,
                "ok": True,
                "skipped": True,
                "reason": "",
                "text": "Should not appear.",
            },
        ]
        write_outputs(tmp_path / "run", records, "broadcast")

        gesamt = (tmp_path / "run" / "AD_GESAMT_Broadcast.txt").read_text()
        assert "Should not appear" not in gesamt

    def test_failed_slot_not_in_gesamt(self, tmp_path):
        records = [
            {
                "slot": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "duration_s": 2.0,
                "ok": False,
                "skipped": False,
                "reason": "gpt_error",
                "text": "Some text.",
            },
        ]
        write_outputs(tmp_path / "run", records, "broadcast")

        gesamt = (tmp_path / "run" / "AD_GESAMT_Broadcast.txt").read_text()
        assert "Some text" not in gesamt


class TestWriteOutputsDirectors:
    @pytest.fixture
    def records(self):
        return [
            {
                "slot": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "duration_s": 2.0,
                "ok": True,
                "skipped": False,
                "reason": "",
                "text": "Person enters room.",
            },
        ]

    def test_directors_creates_gesamt_txt(self, tmp_path, records):
        write_outputs(tmp_path / "run", records, "directors")

        gesamt = (tmp_path / "run" / "AD_GESAMT_DirectorsCut.txt").read_text()
        assert "Person enters room." in gesamt

    def test_directors_creates_quality_file(self, tmp_path, records):
        write_outputs(tmp_path / "run", records, "directors")

        quality = (tmp_path / "run" / "Qualitätsdatei_DirectorsCut.txt").read_text()
        assert "Slot" in quality

    def test_directors_creates_tsv(self, tmp_path, records):
        write_outputs(tmp_path / "run", records, "directors")

        tsv = (tmp_path / "run" / "audio_description_directors_cut.tsv").read_text()
        assert "start\tende\ttext" in tsv
        assert "Person enters room." in tsv

    def test_returns_correct_file_labels(self, tmp_path):
        records = [
            {
                "slot": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "duration_s": 2.0,
                "ok": True,
                "skipped": False,
                "reason": "",
                "text": "Test.",
            },
        ]

        broadcast_paths = write_outputs(tmp_path / "bc", records, "broadcast")
        directors_paths = write_outputs(tmp_path / "dc", records, "directors")

        assert "gesamt_txt" in broadcast_paths
        assert "quality_txt" in broadcast_paths
        assert "frazier_csv" in broadcast_paths

        assert "gesamt_txt" in directors_paths
        assert "quality_txt" in directors_paths
        assert "directors_tsv" in directors_paths

    def test_creates_parent_directories(self, tmp_path):
        records = [
            {
                "slot": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "duration_s": 2.0,
                "ok": True,
                "skipped": False,
                "reason": "",
                "text": "Test.",
            },
        ]

        write_outputs(tmp_path / "nested" / "run", records, "broadcast")

        assert (tmp_path / "nested" / "run" / "AD_GESAMT_Broadcast.txt").exists()


class TestWriteOutputsEdgeCases:
    def test_empty_records(self, tmp_path):
        paths = write_outputs(tmp_path / "run", [], "broadcast")

        assert (tmp_path / "run" / "AD_GESAMT_Broadcast.txt").exists()
        assert paths["gesamt_txt"]

    def test_whitespace_in_text_cleaned(self, tmp_path):
        records = [
            {
                "slot": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "duration_s": 2.0,
                "ok": True,
                "skipped": False,
                "reason": "",
                "text": "  Multiple   spaces   here  ",
            },
        ]

        write_outputs(tmp_path / "run", records, "broadcast")

        gesamt = (tmp_path / "run" / "AD_GESAMT_Broadcast.txt").read_text()
        assert "Multiple   spaces   here" not in gesamt
        assert "Multiple spaces here" in gesamt

    def test_semicolon_in_text_quoted_in_frazier_csv(self, tmp_path):
        records = [
            {
                "slot": 1,
                "start_s": 0.0,
                "end_s": 2.0,
                "duration_s": 2.0,
                "ok": True,
                "skipped": False,
                "reason": "",
                "text": "Text; with semicolon",
            },
        ]

        write_outputs(tmp_path / "run", records, "broadcast")

        csv = (tmp_path / "run" / "audio_description_frazier.csv").read_text()
        assert 'Text; with semicolon' in csv