import importlib


import pytest


def _load_settings():
    settings_module = importlib.import_module("mlit_mcp.settings")
    importlib.reload(settings_module)
    return settings_module.Settings()


def test_settings_require_api_key(monkeypatch):
    monkeypatch.delenv("MLIT_API_KEY", raising=False)
    monkeypatch.delenv("HUDOUSAN_API_KEY", raising=False)

    settings_module = importlib.import_module("mlit_mcp.settings")
    importlib.reload(settings_module)

    # Disable env file loading by clearing env_file from config
    # Accessing model_config directly as it's a dict in Pydantic V2
    settings_module.Settings.model_config["env_file"] = None

    with pytest.raises(Exception):
        settings_module.Settings()


def test_settings_use_default_base_url(monkeypatch):
    monkeypatch.setenv("MLIT_API_KEY", "dummy-key")
    monkeypatch.delenv("MLIT_BASE_URL", raising=False)
    settings_module = importlib.import_module("mlit_mcp.settings")
    importlib.reload(settings_module)
    settings = settings_module.Settings()
    assert settings.base_url == "https://www.reinfolib.mlit.go.jp/ex-api/external/"
