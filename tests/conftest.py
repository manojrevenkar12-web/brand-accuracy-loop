import json
import tomllib
from pathlib import Path

import pytest

from accuracy import settings as settings_mod
from accuracy.extract import Extractor
from accuracy.world.sim import World

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def world():
    cfg = tomllib.loads((ROOT / "config" / "world.toml").read_text())
    cfg.update(brands=15, prompts_train=200, prompts_eval=60)
    return World(cfg)


@pytest.fixture(scope="session")
def settings():
    return settings_mod.load()


@pytest.fixture(scope="session")
def extractor(world, settings):
    return Extractor(world.vault, settings["lexicon"])


@pytest.fixture(scope="session")
def model():
    return json.loads((ROOT / "models" / "verifier.json").read_text())
