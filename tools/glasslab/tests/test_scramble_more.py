"""scrambler hard cases (review #9): shadow roots, lazy images, backgrounds on any element, canvas, video posters"""
import asyncio, json

import pytest

from tools.glasslab import lab

pytestmark = pytest.mark.e2e
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
SNAP = """JSON.stringify({
  shadow: document.getElementById('host').shadowRoot.getElementById('inner').textContent,
  lazy: getComputedStyle(document.getElementById('lazy')).objectPosition,
  btn: getComputedStyle(document.getElementById('bgbtn')).backgroundImage,
  cv: getComputedStyle(document.getElementById('cv')).filter,
  vid: getComputedStyle(document.getElementById('vid')).filter })"""


@pytest.fixture(scope="module")
def after(fixture_url, tmp_path_factory):
    async def go():
        async with lab.session(None, tmp_path_factory.mktemp("scr2") / "browser.log") as pg:
            await pg.goto(fixture_url("private2.html"), settle=1)
            await pg.probe("scramble", ["#mail"], 7)
            await pg.eval(f"document.getElementById('lazy').src = '{PNG}'")   # lazy load swaps in the real photo
            await asyncio.sleep(0.5)
            return json.loads(await pg.eval(SNAP))
    return asyncio.run(go())


def test_shadow_root_text_scrambled(after):
    assert "margaret" not in after["shadow"].lower() and len(after["shadow"]) == len("Margaret Thornbury")


def test_lazy_image_covered_after_src_swap(after):
    assert "-99999" in after["lazy"]


def test_background_avatar_on_any_element(after):
    assert after["btn"] == "none"


def test_canvas_and_video_covered(after):
    assert "contrast(0)" in after["cv"] and "contrast(0)" in after["vid"]
