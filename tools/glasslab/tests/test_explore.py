"""explorer e2e on the fixture app: finds hidden UI, never clicks dangerous controls, flags the unstyled menu."""
import asyncio, re

import pytest

from tools.glasslab import explore, lab

pytestmark = pytest.mark.e2e
BOUNDS = [[0, 0, 0], [222, 222, 222]]


@pytest.fixture(scope="module")
def explored(fixture_url, tmp_path_factory):
    out = tmp_path_factory.mktemp("explore")

    async def go():
        async with lab.session(None, out / "browser.log") as pg:
            await pg.goto(fixture_url("app.html"), settle=1)
            start = await pg.eval("location.href")
            states = await explore.explore(pg, BOUNDS, shots=out)
            return {"states": states, "danger": await pg.eval("!!window.__danger"), "start": start,
                    "submitted": await pg.eval("!!window.__submitted"), "typed": await pg.eval("!!window.__typed"),
                    "end": await pg.eval("location.href"),
                    "open": await pg.eval("document.querySelectorAll('.pop:not([hidden]), dialog[open], #drawer:not([hidden])').length"),
                    "loads": await pg.eval("sessionStorage.loads"),
                    "out": out}
    return asyncio.run(go())


def state(explored, trigger_id):
    return next((s for s in explored["states"] if s["trigger"]["id"] == trigger_id), None)


def test_opens_every_safe_trigger(explored):
    for t in ("menu-bad-btn", "menu-good-btn", "search", "dialog-btn", "drawer-btn"):
        assert state(explored, t), f"{t} not explored: {[s['trigger'] for s in explored['states']]}"


def test_never_touches_dangerous_controls(explored):
    assert explored["danger"] is False
    for t in ("danger-btn", "de-delete", "titled", "icon-only"):   # English/German verbs, any label source, unlabeled
        assert state(explored, t) is None, t


def test_never_submits_forms(explored):
    assert explored["submitted"] is False and state(explored, "form-more") is None


def test_types_only_into_search_fields(explored):
    assert explored["typed"] is False


def test_flags_unstyled_menu(explored):
    s = state(explored, "menu-bad-btn")
    assert not s["ok"]
    dark = s["modes"]["dark"]
    assert dark["surface"] < 0.5
    assert any("255, 255, 255" in f[0] for f in dark["surface_foreign"])


@pytest.mark.parametrize("trigger", ["menu-good-btn", "search", "dialog-btn", "drawer-btn"])
def test_styled_layers_pass(explored, trigger):
    s = state(explored, trigger)
    assert s["ok"], {m: (v["surface"], v["alpha"], v["contrast"], v["failing"][:2]) for m, v in s["modes"].items()}


def test_layer_is_the_new_surface(explored):
    s = state(explored, "menu-good-btn")
    assert any(re.search(r"#menu-good", l["sel"]) for l in s["layers"])


def test_restores_page_after_each_state(explored):
    assert explored["end"] == explored["start"]
    assert explored["open"] == 0


def test_restores_without_reloading(explored):
    """Escape, else re-click an expanded toggle (panels that ignore Escape); reload only as a last resort"""
    assert explored["loads"] == "1"


def test_saves_state_shots(explored):
    s = state(explored, "menu-bad-btn")
    assert (explored["out"] / f"{s['key']}.dark.45.black.png").exists()


def test_drawer_over_empty_glass_is_not_a_popover(explored):
    s = state(explored, "drawer-btn")
    assert s["modes"]["dark"]["over_content"] is False and s["ok"]   # judged as frame glass, not as a popover


def test_menus_float_over_content(explored):
    assert state(explored, "menu-good-btn")["modes"]["dark"]["over_content"] is True


def test_survives_a_broken_trigger(fixture_url, tmp_path):
    """a trigger whose selector no longer resolves (DOM re-rendered) is skipped, not fatal"""
    async def go():
        async with lab.session(None, tmp_path / "browser.log") as pg:
            await pg.goto(fixture_url("app.html"), settle=1)
            return await explore.activate(pg, {"sel": "div:::nonsense", "label": "x", "kind": "click"})
    assert asyncio.run(go()) is False


def test_ripple_inside_the_trigger_is_not_a_layer(explored):
    s = state(explored, "ripple-btn")
    assert s and [l["sel"] for l in s["layers"]] == ["#menu-sort"], s and s["layers"]
