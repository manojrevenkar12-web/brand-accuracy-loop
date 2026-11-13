from __future__ import annotations

import os
import tomllib
from pathlib import Path

# the checkout in development; the image sets ACCURACY_ROOT, because an installed package lives in site-packages
ROOT = Path(os.environ.get("ACCURACY_ROOT", Path(__file__).resolve().parents[2]))


def load(path: Path | None = None) -> dict:
    cfg = tomllib.loads((path or ROOT / "config" / "pipeline.toml").read_text())
    cfg["lexicon"] = tomllib.loads((ROOT / "config" / "lexicon.toml").read_text())["cues"]
    return cfg
