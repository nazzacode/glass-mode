"""the built extension loads in the lab browser (Zen sideload / Firefox BiDi temporary add-on) and runs its content script"""
import asyncio

import pytest

from tools.glasslab import cli, lab

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def xpi():
    try:
        return cli.xpi(False)
    except SystemExit:
        pytest.skip("no extension build (npm run build)")


def test_content_script_sets_glass_mode(xpi, fixture_url, tmp_path):
    async def go():
        async with lab.session(xpi, tmp_path / "browser.log") as pg:
            await pg.goto(fixture_url("app.html"), settle=2)
            return await pg.eval("document.documentElement.dataset.tzGlass")
    assert asyncio.run(go()) in ("dark", "light")
