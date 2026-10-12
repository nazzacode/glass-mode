"""pure scoring maths (no browser)"""
import numpy as np
from PIL import Image

from tools.glasslab import metrics


def solid(rgb, size=(40, 30)):
    return Image.new("RGB", size, rgb)


def test_alpha_map_exact_for_opaque_and_clear():
    # opaque white surface: same on black and white backdrops → alpha 1; clear: shows the backdrop → alpha 0
    assert np.allclose(metrics.alpha_map(solid((255,) * 3), solid((255,) * 3)), 1)
    assert np.allclose(metrics.alpha_map(solid((0,) * 3), solid((255,) * 3)), 0)


def test_alpha_map_half():
    # 50 % black glass: over black → 0, over white → 127.5
    a = metrics.alpha_map(solid((0,) * 3), solid((128,) * 3))
    assert abs(a.mean() - 0.5) < 0.01


def test_region_alpha_and_glass_share():
    a = np.zeros((30, 40))
    a[:, 20:] = 1.0                                       # right half opaque
    assert metrics.region_alpha(a, [20, 0, 20, 30]) == 1.0
    assert metrics.region_alpha(a, [0, 0, 20, 30]) == 0.0
    assert metrics.glass_share(a) == 0.5                  # share of the window where the desktop shows through


def test_composite_matches_formula():
    black, white = solid((40,) * 3), solid((40 + 128,) * 3)  # alpha ≈ .5, colour 40/.5 = 80
    out = np.asarray(metrics.composite(black, white, solid((200,) * 3)))
    assert abs(out.mean() - (40 + 0.5 * 200)) < 2


def run(sel, fg, cr, need=60, n=10, **kw):
    return {"sel": sel, "t": sel, "x": 0, "y": 0, "fg": fg, "cr": cr, "need": need, "n": n, **kw}


def test_score_contrast_and_text_unity():
    fgs = [[242, 242, 245], [223, 223, 227], [168, 168, 176]]
    runs = [run("a", "rgb(242, 242, 245)", [80, 70]), run("b", "rgb(120, 120, 120)", [30, 20])]
    m = metrics.score(runs, {}, fgs, {"surface": 1.0})
    assert m["contrast"] == [0.5, 0.5]
    assert m["text"] == 0.5                                # b is a foreign neutral colour
    assert m["failing"][0]["sel"] == "b"
    assert not metrics.verdict(m)


def test_score_native_relaxation():
    # site's own design reads at Lc 40 → glass needs only 36 for that run
    r = run("a", "rgb(242, 242, 245)", [38, 38])
    m = metrics.score([r], {metrics.rkey(r): (40, "rgb(0, 0, 0)")}, [[242, 242, 245]], {"surface": 1})
    assert m["contrast"] == [1.0, 1.0]


def test_layer_verdict_needs_opaque_enough_glass():
    good = {"surface": 0.95, "opacity": 0.9, "contrast": [1.0, 1.0], "text": 1.0, "exempt_img_share": 0}
    assert metrics.layer_ok(good)
    assert not metrics.layer_ok({**good, "opacity": 0.5})      # see-through popover: page text bleeds through
    assert not metrics.layer_ok({**good, "surface": 0.5})    # site's own colour (unstyled menu)
    assert not metrics.layer_ok({**good, "contrast": [1.0, 0.6]})
