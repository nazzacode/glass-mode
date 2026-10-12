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
                    "end": await pg.eval("location.href"),
                    "open": await pg.eval("document.querySelectorAll('.pop:not([hidden]), dialog[open]').length"),
                    "out": out}
    return asyncio.run(go())


def state(explored, trigger_id):
    return next((s for s in explored["states"] if s["trigger"]["id"] == trigger_id), None)


def test_opens_every_safe_trigger(explored):
    for t in ("menu-bad-btn", "menu-good-btn", "search", "dialog-btn"):
        assert state(explored, t), f"{t} not explored: {[s['trigger'] for s in explored['states']]}"


def test_never_touches_dangerous_controls(explored):
    assert explored["danger"] is False
    assert state(explored, "danger-btn") is None


def test_flags_unstyled_menu(explored):
    s = state(explored, "menu-bad-btn")
    assert not s["ok"]
    dark = s["modes"]["dark"]
    assert dark["surface"] < 0.5
    assert any("255, 255, 255" in f[0] for f in dark["surface_foreign"])


@pytest.mark.parametrize("trigger", ["menu-good-btn", "search", "dialog-btn"])
def test_styled_layers_pass(explored, trigger):
    s = state(explored, trigger)
    assert s["ok"], {m: (v["surface"], v["alpha"], v["contrast"], v["failing"][:2]) for m, v in s["modes"].items()}


def test_layer_is_the_new_surface(explored):
    s = state(explored, "menu-good-btn")
    assert any(re.search(r"#menu-good", l["sel"]) for l in s["layers"])


def test_restores_page_after_each_state(explored):
    assert explored["end"] == explored["start"]
    assert explored["open"] == 0


def test_saves_state_shots(explored):
    s = state(explored, "menu-bad-btn")
    assert (explored["out"] / f"{s['key']}.dark.45.black.png").exists()
