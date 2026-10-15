"""Load the integration's pure modules (const, mapping, budget, api) without importing Home Assistant."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "custom_components" / "fenton_weatherkit"

if "fenton_weatherkit" not in sys.modules:
    package = types.ModuleType("fenton_weatherkit")
    package.__path__ = [str(PACKAGE)]
    sys.modules["fenton_weatherkit"] = package
    for name in ("const", "mapping", "budget", "api"):
        spec = importlib.util.spec_from_file_location(f"fenton_weatherkit.{name}", PACKAGE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)


@pytest.fixture
def response() -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "weather.json").read_text())


@pytest.fixture
def alert_detail() -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "alert.json").read_text())
