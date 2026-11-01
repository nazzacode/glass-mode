"""popup slider, real extension: dragging moves other tabs at once (it sat behind a 500 ms debounce, so it looked dead)."""
import asyncio

import pytest

from tools.glasslab import lab
from tools.glasslab.tests.test_extension import xpi  # noqa: F401  (fixture)

pytestmark = pytest.mark.e2e
UUID = "11111111-2222-4333-8444-555555555555"
POPUP = f"moz-extension://{UUID}/dist/popup/popup.html"
# BiDi may not navigate to extension pages, so the popup page opens as the first tab, from the startup pref
PREFS = {"extensions.webextensions.uuids": '{"%s":"%s"}' % (lab.EXT_ID, UUID), "browser.startup.page": 1, "browser.startup.homepage": POPUP}
DRAG = """(() => { const s = document.querySelector('input[name=glass-opacity]'); s.value = %d;
  s.dispatchEvent(new (s.ownerDocument.defaultView.Event)('input', { bubbles: true })); return s.value; })()"""
ALPHA = "document.documentElement.style.getPropertyValue('--tz-glass-alpha')"


def test_slider_reaches_other_tabs_without_waiting_for_the_save(xpi, fixture_url, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("GLASSLAB_SYSTEM", "1")

    async def go():
        async with lab.session(xpi, tmp_path / "browser.log", extra_prefs=PREFS) as page:
            await asyncio.sleep(3)
            tree = (await page.b.call("browsingContext.getTree"))["contexts"]
            popup = next(c["context"] for c in tree if c["url"] == POPUP)
            page.ctx = (await page.b.call("browsingContext.create", type="tab", referenceContext=popup))["context"]  # the lab's first context isn't a tab to tabs.query
            await page.goto(fixture_url("plain.html"), settle=2)
            seen = []
            for v in (20, 75):
                await page.b.eval(popup, DRAG % v)
                await asyncio.sleep(0.2)  # well under the 500 ms save debounce
                seen.append(await page.eval(ALPHA))
            return seen
    assert asyncio.run(go()) == ["0.2", "0.75"]
