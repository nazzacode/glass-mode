"""the in-page glass panel (Alt+Shift+G): the UI for windows without a toolbar (web apps). Real keys, real extension."""
import asyncio

import pytest

from tools.glasslab import lab
from tools.glasslab.lab import KEY
from tools.glasslab.tests.test_extension import xpi  # noqa: F401  (fixture)

pytestmark = pytest.mark.e2e
PANEL = "document.querySelector('tz-glass-panel')"
ROOT = PANEL + "?.shadowRoot"


@pytest.fixture(scope="module")
def panel(xpi, fixture_url, tmp_path_factory):  # noqa: F811
    async def go():
        async with lab.session(xpi, tmp_path_factory.mktemp("panel") / "browser.log") as pg:
            await pg.goto(fixture_url("plain.html"), settle=1)
            r = {}
            await pg.keys(KEY["Alt"], KEY["Shift"], "g")
            await asyncio.sleep(0.8)
            r["open"] = await pg.eval(f"!!{PANEL} && !{PANEL}.hidden")
            r["slider"] = await pg.eval(f"{ROOT}.querySelector('input[type=range]').value")
            r["modes"] = await pg.eval(f"[...{ROOT}.querySelectorAll('[data-theme]')].map(b => b.dataset.theme).join(',')")
            await pg.eval(f"(s => {{ s.value = 60; s.dispatchEvent(new Event('input', {{bubbles: true}})); }})({ROOT}.querySelector('input[type=range]'))")
            await asyncio.sleep(0.8)
            r["alpha"] = await pg.eval("document.documentElement.style.getPropertyValue('--tz-glass-alpha')")
            await pg.eval(f"{ROOT}.querySelector('[data-theme=light]').click()")
            await asyncio.sleep(0.8)
            r["mode"] = await pg.eval("document.documentElement.dataset.tzGlass")
            r["report"] = await pg.eval(f"{ROOT}.querySelector('a[href*=issues]')?.href ?? ''")
            await pg.keys(KEY["Escape"])
            await asyncio.sleep(0.4)
            r["closed"] = await pg.eval(f"!{PANEL} || {PANEL}.hidden")
            return r
    return asyncio.run(go())


def test_shortcut_opens_the_panel(panel):
    assert panel["open"] and panel["slider"] == "45"


def test_three_modes(panel):
    assert panel["modes"] == "auto,dark,light"


def test_slider_sets_opacity_everywhere(panel):
    assert panel["alpha"] == "0.6"


def test_mode_buttons(panel):
    assert panel["mode"] == "light"


def test_report_link_and_escape(panel):
    assert "issues/new" in panel["report"] and panel["closed"]
