import dataclasses
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str):
        return json.loads((FIXTURES_DIR / name).read_text())

    return _load


@pytest.fixture
def patch_output_dir(monkeypatch, tmp_path):
    """Redirige les fichiers générés (carte, GeoJSON, PDF) vers un répertoire jetable.

    ``SETTINGS`` est un dataclass ``frozen=True`` importé par valeur dans plusieurs
    modules ; seul ``outputs._shared`` utilise ``SETTINGS.output_dir`` (via
    ``new_output_path``), donc c'est le seul module qu'il faut patcher pour que la
    génération de carte/GeoJSON/PDF écrive dans ``tmp_path``.
    """
    from mcp_irve.config import SETTINGS
    from mcp_irve.outputs import _shared as outputs_shared

    patched = dataclasses.replace(SETTINGS, output_dir=tmp_path)
    monkeypatch.setattr(outputs_shared, "SETTINGS", patched)
    return tmp_path
