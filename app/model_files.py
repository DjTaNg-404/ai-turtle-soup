"""Locations and file manifest for the supported Laya Multilingual checkpoint."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "convaiinnovations/laya"
MODEL_REVISION = "1c5edc17a7acd8701df6fc341c0d179f1c62c982"
REQUIRED_MODEL_FILES = (
    "model.safetensors",
    "rl_agent_config.json",
    "encoder/config.json",
    "tokenizer/tokenizer.json",
    "tokenizer/tokenizer_config.json",
)


def resolve_model_dir(explicit=None) -> Path:
    override = explicit or os.getenv("LAYA_MODEL_DIR")
    if override:
        return Path(override).expanduser().resolve()
    project_model = ROOT / "models/laya/multilingual"
    # Preserve the location used by early local installations.
    legacy_model = Path.home() / "model/laya/multilingual"
    if project_model.exists() or not legacy_model.is_dir():
        return project_model
    return legacy_model


def missing_model_files(directory: Path) -> list[str]:
    return [name for name in REQUIRED_MODEL_FILES if not (directory / name).is_file()]
