from pathlib import Path

import pytest

from app import model_files
from app.judge import JudgeError, LayaJudge


def test_model_location_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(model_files, "ROOT", tmp_path / "project")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("LAYA_MODEL_DIR", raising=False)
    project = tmp_path / "project/models/laya/multilingual"
    legacy = tmp_path / "home/model/laya/multilingual"
    assert model_files.resolve_model_dir() == project
    legacy.mkdir(parents=True)
    assert model_files.resolve_model_dir() == legacy
    project.mkdir(parents=True)
    assert model_files.resolve_model_dir() == project
    monkeypatch.setenv("LAYA_MODEL_DIR", str(tmp_path / "configured"))
    assert model_files.resolve_model_dir() == tmp_path / "configured"
    assert model_files.resolve_model_dir(tmp_path / "explicit") == tmp_path / "explicit"


def test_missing_checkpoint_has_actionable_error_without_loading_torch(tmp_path, monkeypatch):
    judge = LayaJudge(model_dir=tmp_path)
    monkeypatch.setattr(judge, "_load", lambda: pytest.fail("Do not construct a model before checking files"))
    with pytest.raises(JudgeError, match="scripts/download_model.py"):
        judge.load()
    assert not judge.ready and not judge.loading
    assert "model.safetensors" in judge.status()["error"]
