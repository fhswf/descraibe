"""Tests for backend.pipeline.ad_slots – pauses → AD slots conversion and quality report."""
from __future__ import annotations

import pandas as pd
import pytest

from backend.pipeline.ad_slots import (
    _any_overlap_exceeds,
    _total_overlap,
    pauses_to_slots,
    quality_report,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_pauses(*triples):
    """Build a pauses DataFrame from (start, end, dur) triples."""
    rows = [{"start_s": s, "end_s": e, "dur_s": d} for s, e, d in triples]
    return pd.DataFrame(rows)


def make_speech(*triples):
    """Build a speech DataFrame from (start, end, dur) triples."""
    rows = [{"start_s": s, "end_s": e, "dur_s": d} for s, e, d in triples]
    return pd.DataFrame(rows)


# ── pauses_to_slots ─────────────────────────────────────────────────────────────

class TestPausesToSlots:
    def test_empty_pauses_returns_empty_slots(self):
        df = make_pauses()
        result = pauses_to_slots(df)
        assert result.empty
        assert "slot" in result.columns

    def test_single_pause_becomes_slot(self):
        df = make_pauses((0.0, 2.0, 2.0))
        result = pauses_to_slots(df)
        assert len(result) == 1
        assert result.iloc[0]["slot"] == 1
        assert result.iloc[0]["start_s"] == 0.0
        assert result.iloc[0]["end_s"] == 2.0

    def test_slots_numbered_sequentially(self):
        df = make_pauses((0.0, 2.0, 2.0), (5.0, 7.0, 2.0), (10.0, 12.0, 2.0))
        result = pauses_to_slots(df)
        assert list(result["slot"]) == [1, 2, 3]

    def test_padding_in_applied(self):
        df = make_pauses((1.0, 3.0, 2.0))
        result = pauses_to_slots(df, pad_in_s=0.5)
        assert result.iloc[0]["start_s"] == 1.5
        assert result.iloc[0]["end_s"] == 3.0

    def test_padding_out_applied(self):
        df = make_pauses((1.0, 3.0, 2.0))
        result = pauses_to_slots(df, pad_out_s=0.5)
        assert result.iloc[0]["start_s"] == 1.0
        assert result.iloc[0]["end_s"] == 2.5

    def test_both_paddings_applied(self):
        df = make_pauses((1.0, 5.0, 4.0))
        result = pauses_to_slots(df, pad_in_s=0.5, pad_out_s=1.0)
        assert result.iloc[0]["start_s"] == 1.5
        assert result.iloc[0]["end_s"] == 4.0
        assert result.iloc[0]["dur_s"] == 2.5

    def test_min_slot_s_filters_short_pauses(self):
        df = make_pauses((0.0, 0.5, 0.5), (2.0, 4.0, 2.0))
        result = pauses_to_slots(df, min_slot_s=1.0)
        assert len(result) == 1
        assert result.iloc[0]["start_s"] == 2.0

    def test_default_min_slot_s_is_one_second(self):
        df = make_pauses((0.0, 0.9, 0.9))
        result = pauses_to_slots(df)
        assert result.empty

    def test_negative_duration_after_padding_removed(self):
        df = make_pauses((0.0, 0.3, 0.3))
        result = pauses_to_slots(df, pad_in_s=0.2, pad_out_s=0.2)
        assert result.empty

    def test_slots_without_speech_df_unchanged(self):
        df = make_pauses((0.0, 2.0, 2.0), (5.0, 7.0, 2.0))
        result = pauses_to_slots(df, speech_df=None)
        assert len(result) == 2


class TestPausesToSlotsWithSpeechOverlap:
    def test_slot_removed_when_speech_overlap_exceeds_epsilon(self):
        pauses = make_pauses((1.0, 4.0, 3.0))  # 3-second pause
        speech = make_speech((0.5, 3.5, 3.0))  # speech overlaps 1.0-3.5

        result = pauses_to_slots(pauses, speech_df=speech, whisper_overlap_eps_s=0.05)
        assert result.empty, "Slot should be removed due to > 0.05s overlap"

    def test_slot_kept_when_speech_overlap_below_epsilon(self):
        pauses = make_pauses((1.0, 4.0, 3.0))  # 3-second pause
        speech = make_speech((3.9, 5.0, 1.1))  # only 0.1s overlap with pause

        result = pauses_to_slots(pauses, speech_df=speech, whisper_overlap_eps_s=0.2)
        assert len(result) == 1

    def test_multiple_slots_some_removed(self):
        pauses = make_pauses((1.0, 4.0, 3.0), (10.0, 14.0, 4.0))
        speech = make_speech((0.5, 3.5, 3.0))  # overlaps with first pause

        result = pauses_to_slots(pauses, speech_df=speech, whisper_overlap_eps_s=0.05)
        assert len(result) == 1
        assert result.iloc[0]["start_s"] == 10.0

    def test_empty_speech_df_keeps_all_slots(self):
        pauses = make_pauses((1.0, 4.0, 3.0), (10.0, 14.0, 4.0))
        speech = make_speech()

        result = pauses_to_slots(pauses, speech_df=speech, whisper_overlap_eps_s=0.01)
        assert len(result) == 2

    def test_slot_at_boundary_exactly_epsilon_is_kept(self):
        pauses = make_pauses((1.0, 4.0, 3.0))
        speech = make_speech((4.0, 5.0, 1.0))  # overlaps 0.0s (touching boundary)

        result = pauses_to_slots(pauses, speech_df=speech, whisper_overlap_eps_s=0.0)
        assert len(result) == 1

    def test_slot_removed_when_overlap_exactly_epsilon_plus_delta(self):
        pauses = make_pauses((1.0, 4.0, 3.0))
        speech = make_speech((3.96, 5.0, 1.04))  # 0.04s overlap

        result = pauses_to_slots(pauses, speech_df=speech, whisper_overlap_eps_s=0.04)
        assert result.empty


# ── _any_overlap_exceeds ───────────────────────────────────────────────────────

class TestAnyOverlapExceeds:
    def test_no_overlap_returns_false(self):
        speech = make_speech((10.0, 12.0, 2.0))
        assert _any_overlap_exceeds(0.0, 2.0, speech, eps_s=0.1) is False

    def test_small_overlap_within_epsilon_returns_false(self):
        speech = make_speech((1.9, 3.0, 1.1))  # 0.1s overlap
        assert _any_overlap_exceeds(0.0, 2.0, speech, eps_s=0.15) is False

    def test_overlap_exceeds_epsilon_returns_true(self):
        speech = make_speech((1.9, 3.0, 1.1))  # 0.1s overlap
        assert _any_overlap_exceeds(0.0, 2.0, speech, eps_s=0.05) is True

    def test_multiple_speech_segments_one_exceeds(self):
        speech = make_speech((0.0, 0.5, 0.5), (1.9, 3.0, 1.1))  # second exceeds eps
        assert _any_overlap_exceeds(0.0, 2.0, speech, eps_s=0.05) is True

    def test_empty_speech_returns_false(self):
        speech = make_speech()
        assert _any_overlap_exceeds(0.0, 2.0, speech, eps_s=0.0) is False


# ── _total_overlap ─────────────────────────────────────────────────────────────

class TestTotalOverlap:
    def test_no_overlap_returns_zero(self):
        speech = make_speech((10.0, 12.0, 2.0))
        assert _total_overlap(0.0, 2.0, speech) == pytest.approx(0.0)

    def test_full_overlap(self):
        speech = make_speech((1.0, 3.0, 2.0))
        assert _total_overlap(0.0, 4.0, speech) == pytest.approx(2.0)

    def test_partial_overlap(self):
        speech = make_speech((1.0, 3.0, 2.0))
        assert _total_overlap(0.0, 2.0, speech) == pytest.approx(1.0)

    def test_multiple_overlapping_segments(self):
        speech = make_speech((1.0, 2.0, 1.0), (3.0, 4.0, 1.0))
        assert _total_overlap(0.0, 5.0, speech) == pytest.approx(2.0)


# ── quality_report ─────────────────────────────────────────────────────────────

class TestQualityReport:
    def test_all_green_when_no_speech_overlap(self):
        pauses = make_pauses((0.0, 1.0, 1.0), (5.0, 7.0, 2.0))
        speech = make_speech((2.0, 3.0, 1.0))
        slots = make_pauses((0.0, 1.0, 1.0), (5.0, 7.0, 2.0))

        report = quality_report(pauses, speech, slots)

        assert report["green_count"] == 2
        assert report["yellow_count"] == 0
        assert report["red_count"] == 0

    def test_yellow_threshold(self):
        pauses = make_pauses((0.0, 1.0, 1.0))  # pause
        speech = make_speech((0.95, 1.05, 0.1))  # 0.05s overlap (boundary of yellow)

        slots = make_pauses((0.0, 1.0, 1.0))
        report = quality_report(pauses, speech, slots)

        assert report["yellow_count"] == 1

    def test_red_threshold(self):
        pauses = make_pauses((0.0, 2.0, 2.0))
        speech = make_speech((0.9, 1.2, 0.3))  # 0.3s overlap (> 0.20 red threshold)

        slots = make_pauses((0.0, 2.0, 2.0))
        report = quality_report(pauses, speech, slots)

        assert report["red_count"] == 1

    def test_green_when_overlap_below_yellow(self):
        pauses = make_pauses((0.0, 1.0, 1.0))
        speech = make_speech((0.97, 1.02, 0.05))  # 0.03s overlap

        slots = make_pauses((0.0, 1.0, 1.0))
        report = quality_report(pauses, speech, slots)

        assert report["green_count"] == 1
        assert report["yellow_count"] == 0
        assert report["red_count"] == 0

    def test_max_overlap_used_not_total(self):
        pauses = make_pauses((0.0, 3.0, 3.0))
        speech = make_speech((0.0, 1.0, 1.0), (1.0, 2.0, 1.0), (2.0, 3.0, 1.0))

        slots = make_pauses((0.0, 3.0, 3.0))
        report = quality_report(pauses, speech, slots)

        # Each segment overlaps 1.0s, so max is 1.0s (red threshold = 0.20)
        assert report["red_count"] == 1

    def test_report_includes_row_details(self):
        pauses = make_pauses((0.0, 2.0, 2.0))
        speech = make_speech((1.9, 3.0, 1.1))

        slots = make_pauses((0.0, 2.0, 2.0))
        report = quality_report(pauses, speech, slots)

        assert len(report["rows"]) == 1
        row = report["rows"][0]
        assert "speech_overlap_max_s" in row
        assert "status" in row
        assert row["start_s"] == 0.0
        assert row["end_s"] == 2.0

    def test_total_pauses_and_slots_in_report(self):
        pauses = make_pauses((0.0, 1.0, 1.0), (5.0, 7.0, 2.0))
        speech = make_speech()
        slots = make_pauses((0.0, 1.0, 1.0), (5.0, 7.0, 2.0))

        report = quality_report(pauses, speech, slots)

        assert report["total_pauses"] == 2
        assert report["total_slots"] == 2

    def test_empty_pauses(self):
        pauses = make_pauses()
        speech = make_speech((0.0, 1.0, 1.0))
        slots = make_pauses()

        report = quality_report(pauses, speech, slots)

        assert report["total_pauses"] == 0
        assert report["rows"] == []

    def test_empty_speech(self):
        pauses = make_pauses((0.0, 1.0, 1.0))
        speech = make_speech()
        slots = make_pauses((0.0, 1.0, 1.0))

        report = quality_report(pauses, speech, slots)

        assert report["green_count"] == 1
        assert report["rows"][0]["speech_overlap_max_s"] == 0.0

    def test_boundary_conditions(self):
        # Pause and speech share exactly one boundary point
        pauses = make_pauses((0.0, 1.0, 1.0))
        speech = make_speech((1.0, 2.0, 1.0))

        slots = make_pauses((0.0, 1.0, 1.0))
        report = quality_report(pauses, speech, slots)

        # Overlap at boundary is 0.0s, so green
        assert report["green_count"] == 1
        assert report["rows"][0]["speech_overlap_max_s"] == 0.0