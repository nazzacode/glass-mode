"""showcase render (pure): one centred glass window over a crisp wallpaper, blurred behind the window only."""
import numpy as np
import pytest
from PIL import Image

from tools.glasslab import showcase

SIZE = (1280, 800)
RED = (200, 30, 30)


def capture(size=(400, 250), clear_left=True):
    """black/white pair: left half clear glass (α 0), right half opaque red (α 1)"""
    black, white = Image.new("RGB", size, RED), Image.new("RGB", size, RED)
    if clear_left:
        w, h = size
        black.paste((0, 0, 0), (0, 0, w // 2, h))
        white.paste((255, 255, 255), (0, 0, w // 2, h))
    return black, white


def stripes(size=SIZE):
    """high-frequency wallpaper: crisp ≠ blurred anywhere"""
    x = np.arange(size[0])[None, :, None]
    a = np.where((x // 6) % 2, 230, 20) * np.ones((size[1], 1, 3))
    a[..., 1] = np.linspace(40, 200, size[1])[:, None]
    return Image.fromarray(a.astype("uint8"))


@pytest.fixture(scope="module")
def shot():
    black, white = capture()
    wall = stripes()
    out = showcase.render(black, white, wall, size=SIZE)
    return {"out": np.asarray(out, dtype=float), "wall": np.asarray(showcase.cover(wall, SIZE), dtype=float),
            "blur": np.asarray(showcase.blurred(showcase.cover(wall, SIZE)), dtype=float),
            "rect": showcase.window_rect(SIZE, black.size), "img": out}


def test_size_and_mode(shot):
    assert shot["img"].size == SIZE and shot["img"].mode == "RGB"


def test_window_centred_with_wide_margins(shot):
    x, y, w, h = shot["rect"]
    W, H = SIZE
    assert abs(x - (W - x - w)) <= 1 and abs(y - (H - y - h)) <= 1
    assert x >= 0.18 * W and W - x - w >= 0.18 * W
    assert abs(w / h - 400 / 250) < 0.02                         # aspect from the capture


def test_tall_capture_fits_height():
    x, y, w, h = showcase.window_rect(SIZE, (400, 600))
    assert y >= 0.08 * SIZE[1] and h <= SIZE[1] and abs(w / h - 400 / 600) < 0.02


def test_outside_is_crisp_wallpaper_only_darkened(shot):
    out, wall = shot["out"], shot["wall"]
    x, y, w, h = shot["rect"]
    outside = np.ones(out.shape[:2], bool)
    outside[y:y + h, x:x + w] = False
    assert (out[outside] <= wall[outside] + 2).all()            # shadow only darkens
    assert np.abs(out[:40, :40] - wall[:40, :40]).max() <= 2     # far away: untouched wallpaper
    k = out[outside].sum(1) / np.maximum(wall[outside].sum(1), 1)  # darkening is neutral (same factor per channel)
    d = np.abs(out[outside] - wall[outside] * k[:, None])
    assert np.percentile(d, 99) < 4


def test_clear_glass_shows_blurred_wallpaper(shot):
    out, blur, wall = shot["out"], shot["blur"], shot["wall"]
    x, y, w, h = shot["rect"]
    patch = np.s_[y + h // 2 - 20:y + h // 2 + 20, x + w // 8:x + w // 8 + 40]   # inside the clear half
    assert np.abs(out[patch] - blur[patch]).mean() < 3
    assert np.abs(out[patch] - wall[patch]).mean() > 30        # visibly not the crisp stripes


def test_opaque_page_keeps_its_colour(shot):
    out = shot["out"]
    x, y, w, h = shot["rect"]
    assert np.abs(out[y + h // 2, x + 3 * w // 4] - RED).max() <= 3


def test_corners_rounded():
    black, white = capture(clear_left=False)                     # fully opaque red window
    wall = Image.new("RGB", SIZE, (128, 128, 128))
    out = np.asarray(showcase.render(black, white, wall, size=SIZE), dtype=float)
    x, y, w, h = showcase.window_rect(SIZE, black.size)
    for cx, cy in [(x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)]:
        r, g, b = out[cy, cx]
        assert abs(r - g) < 4 and abs(g - b) < 4                 # corner pixel = (shadowed) wallpaper, not page red
    r = showcase.radius_px(w)
    assert np.abs(out[y + 2 * r, x + 2 * r] - RED).max() <= 3


def test_hairline_border_lightens_edge():
    black, white = Image.new("RGB", (400, 250), (20, 20, 24)), Image.new("RGB", (400, 250), (20, 20, 24))
    out = np.asarray(showcase.render(black, white, Image.new("RGB", SIZE, (60, 60, 60)), size=SIZE), dtype=float)
    x, y, w, h = showcase.window_rect(SIZE, black.size)
    assert out[y, x + w // 2].mean() > out[y + 6, x + w // 2].mean() + 4


def test_deterministic():
    black, white = capture()
    a = showcase.render(black, white, stripes(), size=SIZE)
    b = showcase.render(black, white, stripes(), size=SIZE)
    assert np.array_equal(np.asarray(a), np.asarray(b))


def test_save_writes_jpg_and_small_webp(tmp_path):
    img = Image.new("RGB", (2560, 1600), (90, 120, 160))
    paths = showcase.save(img, tmp_path / "x.dark")
    assert [p.name for p in paths] == ["x.dark.jpg", "x.dark.webp"]
    assert Image.open(paths[0]).size == (2560, 1600)
    assert Image.open(paths[1]).size == (1280, 800)
