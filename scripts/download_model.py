"""Download the pinned checkpoint explicitly; the game itself stays offline for Laya."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.model_files import MODEL_REPO, MODEL_REVISION, REQUIRED_MODEL_FILES, ROOT, missing_model_files


def main(argv=None):
    parser = argparse.ArgumentParser(description="Download Laya Multilingual weights and JSON configuration.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "models/laya",
                        help="Download root; the checkpoint will be in its multilingual subfolder.")
    parser.add_argument("--revision", default=MODEL_REVISION, help="Hugging Face commit or tag.")
    parser.add_argument("--dry-run", action="store_true", help="Check remote files without downloading weights.")
    args = parser.parse_args(argv)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        parser.error("Install the optional Laya dependencies: uv sync --locked --extra laya")
    destination = args.output_dir.expanduser().resolve()
    result = snapshot_download(
        repo_id=MODEL_REPO,
        revision=args.revision,
        local_dir=str(destination),
        allow_patterns=[f"multilingual/{name}" for name in REQUIRED_MODEL_FILES],
        dry_run=args.dry_run,
    )
    if args.dry_run:
        for item in result:
            print(f"{item.filename}: {item.file_size:,} bytes")
        return 0

    model_dir = destination / "multilingual"
    missing = missing_model_files(model_dir)
    if missing:
        parser.error("Incomplete checkpoint; missing: " + ", ".join(missing))
    print(f"Ready: {model_dir}")
    print(f"Source: {MODEL_REPO}@{args.revision}")
    print("For a custom directory, set LAYA_MODEL_DIR to the path above before starting the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
