from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(path: Path | None = None) -> dict:
    cfg = tomllib.loads((path or ROOT / "config" / "pipeline.toml").read_text())
    cfg["lexicon"] = tomllib.loads((ROOT / "config" / "lexicon.toml").read_text())["cues"]
    return cfg
