"""Local backend configuration tests."""

from __future__ import annotations

import os

from app import config


def test_backend_env_is_loaded_without_manual_environment_variables(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "WATSONX_API_KEY=from-dotenv\n"
        "WATSONX_PROJECT_ID=dotenv-project\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("WATSONX_API_KEY", raising=False)
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    monkeypatch.setattr(config, "ENV_FILE", env_file)

    assert config.load_backend_env() is True
    assert os.environ["WATSONX_API_KEY"] == "from-dotenv"
    assert os.environ["WATSONX_PROJECT_ID"] == "dotenv-project"


def test_operating_system_environment_wins_over_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("WATSONX_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("WATSONX_API_KEY", "from-operating-system")
    monkeypatch.setattr(config, "ENV_FILE", env_file)

    config.load_backend_env()

    assert os.environ["WATSONX_API_KEY"] == "from-operating-system"
