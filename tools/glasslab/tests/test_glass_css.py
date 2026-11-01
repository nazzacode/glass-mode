"""glass.css slider maths: every tier must respond to the slider over its whole range and visibly so; the default
keeps the readable floors, the low end is clear (the user's trade), caps at the high end."""
import asyncio, json

import pytest

from tools.glasslab import lab

pytestmark = pytest.mark.e2e
TIERS = ["--g-frame", "--g-content-abs", "--g-popover"]
READ = """(t => { const i = document.createElement('i'); document.body.append(i);
  const a = t.map(v => { i.style.backgroundColor = `var(${v})`; const m = getComputedStyle(i).backgroundColor.match(/[\\d.]+/g); return +(m[3] ?? 1); });
  i.remove(); return JSON.stringify(a); })(%s)"""


@pytest.fixture(scope="module")
def alphas(fixture_url, tmp_path_factory):
    async def go():
        out = {}
        async with lab.session(None, tmp_path_factory.mktemp("css") / "browser.log") as pg:
            await pg.goto(fixture_url("app.html"), settle=0.5)
            for mode in ("dark", "light"):
                for s in (0.1, 0.3, 0.45, 0.6, 0.9):
                    await pg.glass(mode, s)
                    out[(mode, s)] = json.loads(await pg.eval(READ % json.dumps(TIERS)))
        return out
    return asyncio.run(go())


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_every_step_changes_every_tier(alphas, mode):
    steps = [alphas[(mode, s)] for s in (0.1, 0.3, 0.45, 0.6, 0.9)]
    for i, tier in enumerate(TIERS):
        col = [round(x[i], 3) for x in steps]
        assert all(b > a for a, b in zip(col, col[1:])), (mode, tier, col)


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_clear_at_the_low_end_readable_at_the_default_caps_at_the_high_end(alphas, mode):
    lo, mid, hi = alphas[(mode, 0.1)], alphas[(mode, 0.45)], alphas[(mode, 0.9)]
    floors = {"dark": [0.68, 0.86, 0.9], "light": [0.77, 0.87, 0.87]}[mode]
    assert [round(x, 2) for x in lo] == [0.12, 0.2, 0.6]
    assert [round(x, 2) for x in mid] == floors
    assert [round(x, 2) for x in hi] == [0.92, 0.96, 0.96]
