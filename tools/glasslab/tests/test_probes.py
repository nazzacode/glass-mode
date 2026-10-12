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
