"""probes measure what is painted: element opacity counts (Material state layers are full-colour boxes at 8 % opacity)"""
import asyncio

import pytest

from tools.glasslab import lab

pytestmark = pytest.mark.e2e
BOUNDS = [[0, 0, 0], [222, 222, 222]]


@pytest.fixture(scope="module")
def probed(fixture_url, tmp_path_factory):
    async def go():
        async with lab.session(None, tmp_path_factory.mktemp("probes") / "browser.log") as pg:
            await pg.goto(fixture_url("app.html"), settle=1)
            await pg.glass("dark", 0.45)
            return await pg.probe("text", BOUNDS, [0, 0, 0, 0]), await pg.probe("unity")
    return asyncio.run(go())


def test_state_layer_opacity_counts_in_contrast(probed):
    runs, _ = probed
    row = next(r for r in runs if r["t"].startswith("Row with a state layer"))
    assert min(row["cr"]) >= 60 and row["cr"][0] < 200, row


def test_pseudo_state_layer_opacity_counts(probed):
    runs, _ = probed
    row = next(r for r in runs if r["t"].startswith("Pseudo state layer row"))
    assert min(row["cr"]) >= 60, row


def test_short_single_line_list_label_is_a_label(probed):
    runs, _ = probed
    row = next(r for r in runs if r["t"].startswith("Row with a state layer"))   # 22 chars, one line, 15px
    assert row["need"] == 60


def test_probes_read_oklch(fixture_url, tmp_path):
    """Firefox keeps oklch() in computed style: probes must convert, else text reads as transparent (Lc 0)"""
    async def go():
        async with lab.session(None, tmp_path / "browser.log") as pg:
            await pg.goto(fixture_url("modern.html"), settle=0.5)
            return await pg.probe("text", BOUNDS, [0, 0, 0, 0]), await pg.probe("unity")
    runs, unity = asyncio.run(go())
    muted = next(r for r in runs if r["t"].startswith("Muted text"))
    assert min(muted["cr"]) > 30, muted
    assert unity["foreign"] and "oklch" not in str(unity["foreign"]), unity["foreign"]


@pytest.fixture(scope="module")
def edge(fixture_url, tmp_path_factory):
    async def go():
        async with lab.session(None, tmp_path_factory.mktemp("edge") / "browser.log") as pg:
            await pg.goto(fixture_url("probes.html"), settle=1)
            return await pg.probe("unity"), await pg.probe("unity", ["#frame"])
    return asyncio.run(go())


def test_shared_inks_immune_to_site_important_rules(edge):
    unity, _ = edge
    assert unity["fgs"][0] == [242, 242, 245], unity["fgs"]


def test_inherit_wrapper_counts_as_its_tier(edge):
    unity, _ = edge
    assert unity["tiers"].get("--g-frame", 0) > 0, unity


def test_iframe_only_layer_is_unmeasured_not_failed(edge):
    _, frame = edge
    assert frame["surface"] == 1 and frame.get("unmeasured", 0) > 0, frame


def test_screen_open_runs_act_keys_after(fixture_url, tmp_path):
    """screens.json `keys` are real (trusted) keypresses — some apps ignore synthetic events; `after` runs once they're done"""
    sc = {"url": fixture_url("keys.html"), "settle": 0.5, "act": "document.body.dataset.act = 1", "keys": ["["],
          "after": "document.body.dataset.after = document.body.classList.contains('left-hidden')"}

    async def go():
        async with lab.session(None, tmp_path / "browser.log") as pg:
            await pg.open(sc)
            return await pg.eval("JSON.stringify(document.body.dataset)")
    assert asyncio.run(go()) == '{"act":"1","after":"true"}'
