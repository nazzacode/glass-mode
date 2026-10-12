"""auto glass (on-the-fly mode for sites without a style) on the plain fixture: real extension, real probes."""
import asyncio

import pytest

from tools.glasslab import explore, lab, metrics
from tools.glasslab.tests.test_extension import xpi  # noqa: F401  (fixture)

pytestmark = pytest.mark.e2e
BOUNDS = [[0, 0, 0], [222, 222, 222]]
START = "document.dispatchEvent(new CustomEvent('tz-auto-glass'))"   # lab hook = what the popup toggle does


@pytest.fixture(scope="module", params=["dark", "light"])
def auto(request, xpi, fixture_url, tmp_path_factory):  # noqa: F811
    out = tmp_path_factory.mktemp(f"auto-{request.param}")

    async def go():
        async with lab.session(xpi, out / "browser.log") as pg:
            await pg.goto(fixture_url("plain.html"), settle=1)
            await pg.eval(START)
            await asyncio.sleep(1.5)
            await pg.glass(request.param, 0.45)
            black, white = await pg.shot("#000"), await pg.shot("#fff")
            await pg.clear_backdrop()
            unity = await pg.probe("unity")
            runs = await pg.probe("text", BOUNDS, [0, 0, 0, 0])
            r = {"mode": request.param, "unity": unity, "runs": runs, "glass": metrics.glass_share(metrics.alpha_map(black, white)),
                 "score": metrics.score(runs, {}, unity["fgs"], unity),
                 "btn": await pg.eval("getComputedStyle(document.querySelector('.btn')).backgroundColor"),
                 "tag": await pg.eval("getComputedStyle(document.querySelector('.tag')).backgroundColor"),
                 "pic": await pg.eval("getComputedStyle(document.querySelector('.pic')).backgroundImage"),
                 "ms": await pg.eval("document.documentElement.dataset.tzAutoMs")}
            r["states"] = await explore.explore(pg, BOUNDS, "plain", (request.param,), 0.45)
            return r
    return asyncio.run(go())


def test_page_becomes_glass(auto):
    assert auto["glass"] >= 0.6, "the desktop must show through most of the window"


def test_surfaces_are_glass_tiers(auto):
    assert auto["score"]["surface"] >= 0.9, auto["unity"]["foreign"]


def test_text_is_readable_on_any_wallpaper(auto):
    assert min(auto["score"]["contrast"]) >= 0.9, auto["score"]["failing"][:4]


def test_neutral_text_uses_shared_inks(auto):
    assert auto["score"]["text"] >= 0.85, auto["score"]["text_foreign"]


def test_brand_colours_and_images_kept(auto):
    assert auto["btn"] == "rgb(24, 119, 242)"
    assert auto["tag"] == "rgb(255, 232, 163)"
    assert "gradient" in auto["pic"]


def test_menus_and_dialogs_become_popovers(auto):
    by = {s["trigger"]["label"]: s for s in auto["states"]}
    for label in ("Menu", "Open dialog"):
        assert label in by, list(by)
        assert by[label]["ok"], {k: (v["surface"], v["opacity"], v["contrast"], v["surface_foreign"]) for k, v in by[label]["modes"].items()}


def test_fast(auto):
    assert auto["ms"] is not None and float(auto["ms"]) < 100
