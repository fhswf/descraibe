"""Tests for person context generation used by the AD pipeline."""


class TestPersonsContext:
    """Tests for _build_persons_context function."""

    def test_empty_persons_df(self):
        from backend.pipeline.gpt_description import _build_persons_context
        import pandas as pd

        result = _build_persons_context(None, 0.0, 10.0)
        assert result == ""

        result = _build_persons_context(pd.DataFrame(), 0.0, 10.0)
        assert result == ""

    def test_persons_in_slot(self):
        from backend.pipeline.gpt_description import _build_persons_context
        import pandas as pd

        persons_df = pd.DataFrame([
            {
                "person_id": 1,
                "name": "Maria",
                "first_seen_ts": 5.0,
                "last_seen_ts": 15.0,
                "description": "Maria trägt ein blaues Oberteil.",
                "attributes": {"hair_color": "braun"},
            },
            {
                "person_id": 2,
                "name": "Hans",
                "first_seen_ts": 20.0,
                "last_seen_ts": 30.0,
                "description": "Hans trägt eine schwarze Jacke.",
            },
        ])

        # Slot 0-10 should include Maria (first_seen=5, last_seen=15)
        result = _build_persons_context(persons_df, 0.0, 10.0)
        assert "Maria" in result
        assert "Hans" not in result
        assert "ERSTNENNUNG" in result
        assert "blaues Oberteil" not in result
        assert "hair_color" not in result and "braun" not in result
        assert result == "\n### Personen im Slot\n- **Maria** [ERSTNENNUNG]"

    def test_persons_first_vs_subsequent_mention(self):
        from backend.pipeline.gpt_description import _build_persons_context
        import pandas as pd

        persons_df = pd.DataFrame([
            {
                "person_id": 1,
                "name": "Maria",
                "first_seen_ts": 5.0,
                "last_seen_ts": 15.0,
                "description": "Maria trägt ein blaues Oberteil.",
            },
        ])

        # Slot that contains the first appearance → ERSTNENNUNG
        result = _build_persons_context(persons_df, 0.0, 10.0)
        assert "ERSTNENNUNG" in result

        # Slot that starts at the first appearance time → ERSTNENNUNG
        result = _build_persons_context(persons_df, 5.0, 10.0)
        assert "ERSTNENNUNG" in result

        # Slot that is entirely after the first appearance → FOLGEBENENNUNG
        result = _build_persons_context(persons_df, 15.0, 20.0)
        assert "FOLGEBENENNUNG" in result
