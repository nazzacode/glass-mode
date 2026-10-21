"""glass.css slider maths: every tier must respond to the slider over its whole range (the old clamp(floor, s+x, cap)
left light mode flat below ~65 %: the one control did nothing), floors hold at the low end, caps at the high end."""
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
def test_floors_at_the_low_end_caps_at_the_high_end(alphas, mode):
    lo, hi = alphas[(mode, 0.1)], alphas[(mode, 0.9)]
    floors = {"dark": [0.5, 0.78, 0.85], "light": [0.65, 0.8, 0.8]}[mode]
    assert [round(x, 2) for x in lo] == floors
    assert [round(x, 2) for x in hi] == [0.92, 0.96, 0.96]
