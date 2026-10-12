"""the built extension's scripts load in their contexts: content scripts are classic scripts (no `import`), the background
is an ES module (manifest) — a shared chunk imported by a classic script kills it silently (happened: background.js)"""
import json, re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DIST = ROOT / "dist"
IMPORT = re.compile(r"^\s*import[\s{*]", re.M)


@pytest.fixture(scope="module")
def manifest():
    if not (DIST / "transparent-zen.js").exists():
        pytest.skip("no build (npm run build)")
    return json.loads((ROOT / "manifest.json").read_text())


def test_content_scripts_are_classic(manifest):
    for cs in manifest["content_scripts"]:
        for js in cs["js"]:
            assert not IMPORT.search((ROOT / js).read_text()), f"{js} imports a chunk — content scripts can't"


def test_background_imports_only_as_module(manifest):
    bg = manifest["background"]
    for js in bg["scripts"]:
        if IMPORT.search((ROOT / js).read_text()):
            assert bg.get("type") == "module", f"{js} imports chunks but the background isn't a module"
