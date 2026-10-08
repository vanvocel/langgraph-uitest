"""Phase 0 smoke: prove pytest + Allure pipeline works without SUT dependency."""

from __future__ import annotations

from pathlib import Path

import allure
import pytest
import yaml


@allure.epic("Phase0")
@allure.feature("Skeleton")
@pytest.mark.smoke
class TestPhase0Skeleton:
    @allure.title("Load settings.yaml and report via Allure")
    def test_load_settings(self, project_root: Path, allure_env):
        settings_path = project_root / "config" / "settings.yaml"
        assert settings_path.is_file(), f"missing {settings_path}"

        with settings_path.open(encoding="utf-8") as f:
            settings = yaml.safe_load(f)

        allure.attach(
            str(settings),
            name="settings.yaml",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert settings["project"]["name"] == "LangGraph-uitest"
        assert "browser" in settings
        assert "bootstrap" in settings
        accounts_path = project_root / "config" / "accounts.yaml"
        assert accounts_path.is_file()
        with accounts_path.open(encoding="utf-8") as f:
            accounts = yaml.safe_load(f)
        assert "accounts" in accounts
        assert "default_tester" in accounts["accounts"]

    @allure.title("Requirement run directory layout exists after init")
    def test_runs_root_exists(self, project_root: Path):
        runs = project_root / "runs"
        assert runs.is_dir()
