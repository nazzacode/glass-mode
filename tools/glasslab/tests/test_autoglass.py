"""auto glass (on-the-fly mode for sites without a style) on the plain fixture: real extension, real probes."""
import asyncio

import pytest

from tools.glasslab import explore, lab, metrics, suite
from tools.glasslab.tests.test_extension import xpi  # noqa: F401  (fixture)

pytestmark = pytest.mark.e2e
BOUNDS = [[0, 0, 0], [222, 222, 222]]
START = suite.AUTO   # lab hook = what the popup toggle does


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


@pytest.fixture(scope="module")
def docs(xpi, fixture_url, tmp_path_factory):  # noqa: F811
    async def go():
        async with lab.session(xpi, tmp_path_factory.mktemp("docs") / "browser.log") as pg:
            await pg.goto(fixture_url("docs.html"), settle=0.5)
            await pg.eval(START)
            await asyncio.sleep(3)  # the consent banner appears at 1.2 s
            await pg.glass("dark", 0.45)
            unity = await pg.probe("unity")
            runs = await pg.probe("text", BOUNDS, [0, 0, 0, 0])
            r = metrics.score(runs, {}, unity["fgs"], unity)
            r["banner"] = await pg.eval("getComputedStyle(document.getElementById('consent')).backgroundColor")
            r["banner_fg"] = await pg.eval("getComputedStyle(document.getElementById('consent')).color")
            return r
    return asyncio.run(go())


def test_content_first_page_is_readable(docs):
    assert min(docs["contrast"]) >= 0.9, docs["failing"][:3]


def test_late_ui_without_mutations_is_glass(docs):
    assert docs["surface"] >= 0.9 and docs["text"] >= 0.85, (docs["surface_foreign"], docs["text_foreign"])


def test_root_marks_survive_spa_class_rewrite(xpi, fixture_url, tmp_path):  # noqa: F811
    async def go():
        async with lab.session(xpi, tmp_path / "browser.log") as pg:
            await pg.goto(fixture_url("spa.html"), settle=0.3)
            await pg.eval(START)
            await asyncio.sleep(2)
            return await pg.eval("document.documentElement.className")
    cls = asyncio.run(go()).split()
    assert {"app-ready", "tz-initialized", "tz-auto"} <= set(cls), cls


@pytest.fixture(scope="module")
def modern(xpi, fixture_url, tmp_path_factory):  # noqa: F811
    async def go():
        async with lab.session(xpi, tmp_path_factory.mktemp("modern") / "browser.log") as pg:
            await pg.goto(fixture_url("modern.html"), settle=0.5)
            await pg.eval(START)
            await asyncio.sleep(1)
            r = {"card": await pg.eval("document.querySelector('.card:not(#hero-card)').dataset.tzTier ?? null"),
                 "muted": await pg.eval("document.querySelector('.muted').dataset.tzInk ?? null")}
            # one appended row in a 5000-row list: only the new row is walked
            await pg.eval("document.getElementById('list').append(Object.assign(document.createElement('li'), {textContent: 'new'}))")
            await asyncio.sleep(0.3)
            r["walked"] = int(await pg.eval("document.documentElement.dataset.tzAutoWalked"))
            # a mutation inside the card on the image hero: its new text is inked like the first pass
            await pg.eval("document.getElementById('hero-card').append(Object.assign(document.createElement('p'), {id: 'late', textContent: 'late text'}))")
            await asyncio.sleep(0.3)
            r["late"] = await pg.eval("document.getElementById('late').dataset.tzInk ?? null")
            r["first"] = await pg.eval("document.getElementById('hero-text').dataset.tzInk ?? null")
            # a state class recolours a row: re-read the site's colour (not our cached one)
            await pg.eval("document.querySelector('li').classList.add('sel')")
            await asyncio.sleep(0.3)
            r["sel"] = await pg.eval("document.querySelector('li').dataset.tzTier ?? null")
            return r
    return asyncio.run(go())


def test_oklch_colours_are_seen(modern):
    assert modern["card"] in ("content", "fill") and modern["muted"] in ("2", "3"), modern


def test_appended_row_walks_only_itself(modern):
    assert modern["walked"] <= 5, modern["walked"]


def test_rewalk_context_matches_first_pass(modern):
    assert modern["late"] == modern["first"] and modern["late"] is not None, modern


def test_state_class_recolour_is_reread(modern):
    assert modern["sel"] == "keep", modern   # oklch(93% .03 255) = a light blue selection: brand/data colour


def test_stacked_id_important_rules_still_get_glass(docs):
    """cookie widgets (#ccc #consent { … !important }): background AND text both remapped, never just one"""
    assert docs["banner"].startswith("rgba(") and docs["banner_fg"] == "rgb(242, 242, 245)", (docs["banner"], docs["banner_fg"])
