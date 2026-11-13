"""Container entry point: the vault from VAULT_PATH, the model from MODEL_PATH."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .. import settings as settings_mod
from ..vault import Vault
from .app import create_app

ROOT = settings_mod.ROOT
vault = Vault.load(Path(os.environ.get("VAULT_PATH", ROOT / "examples" / "vault.json")))
model = json.loads(Path(os.environ.get("MODEL_PATH", ROOT / "models" / "verifier.json")).read_text())
app = create_app(vault, settings_mod.load(), model)
