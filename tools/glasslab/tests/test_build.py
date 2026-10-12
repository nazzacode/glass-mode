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


def test_content_bundle_is_fresh(manifest):
    """the content script is a separate build; a misdirected outDir once left a stale bundle in dist/ (silently)"""
    js = ROOT / manifest["content_scripts"][0]["js"][0]
    newest = max(p.stat().st_mtime for p in (ROOT / "src/main").rglob("*.ts") if not p.name.endswith(".test.ts"))
    assert js.stat().st_mtime >= newest, f"{js} older than src/main — rebuild (npm run build)"


def test_package_holds_only_the_extension(manifest):
    """the .xpi once shipped site/ screenshots, the lab and docs (16 MB): allowlist what a user's browser needs"""
    import zipfile
    zips = sorted((ROOT / "builds").glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        pytest.skip("no package (npm run build)")
    z = zipfile.ZipFile(zips[-1])
    top = {n.split("/")[0] for n in z.namelist()}
    assert top <= {"manifest.json", "LICENSE", "data", "dist", "styles", "assets"}, top - {"manifest.json", "LICENSE", "data", "dist", "styles", "assets"}
    assert not [n for n in z.namelist() if n.endswith(".map")]
    assert zips[-1].stat().st_size < 1_500_000
