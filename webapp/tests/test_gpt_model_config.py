from pathlib import Path

from backend import app as app_mod


def test_default_gpt_model_comes_from_config(monkeypatch, tmp_path):
    config_path = tmp_path / "gpt_config.yaml"
    config_path.write_text(
        """
presets:
  standard:
    model: gpt-5-mini-2025-08-07
    temperature: 1.0
    max_output_tokens: 1024
    detail: high
  quality:
    model: gpt-5.2-2025-12-11
    temperature: 1.0
    max_output_tokens: 2048
    detail: high
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("GPT_CONFIG_PATH", str(config_path))

    assert app_mod._default_gpt_model() == "gpt-5-mini-2025-08-07"


def test_system_info_fallback_does_not_reintroduce_gpt_4o(monkeypatch):
    monkeypatch.setenv("GPT_CONFIG_PATH", str(Path("/missing/gpt_config.yaml")))

    info = app_mod.system_info()

    assert info["available_models"] == [
        {"env": "default", "model": "gpt-5-mini-2025-08-07"}
    ]
