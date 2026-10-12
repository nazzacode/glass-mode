"""procedural wallpapers we own (public shots can't use the user's — Apple aerials, copyrighted). numpy + PIL only,
deterministic per seed. Each preset = smooth colour field + crisp structure (ridges, wave edges, stars, streaks) so the
compositor blur behind the window reads clearly against the sharp surround.

  ./glasslab-free: python3 -m tools.glasslab.wallgen OUT_DIR   → every preset as png (look at them)"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ── maths ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def grid(size):
    """x ∈ [0, aspect], y ∈ [0, 1] (top → bottom), float32"""
    W, H = size
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    return x / H, y / H


def rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32)


def ramp(t, stops):
    """t → colour along [(pos, '#hex'), …]"""
    t = np.clip(t, 0, 1)
    ps = np.array([p for p, _ in stops], np.float32)
    cs = np.stack([rgb(c) for _, c in stops])
    return np.stack([np.interp(t, ps, cs[:, k]) for k in range(3)], axis=-1)


def smooth(e0, e1, v):
    t = np.clip((v - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def waves(x, rng, freqs, amps):
    """smooth 1-D field: sum of sines with seeded phases"""
    return sum(a * np.sin(f * x + rng.uniform(0, 2 * np.pi)) for f, a in zip(freqs, amps))


def ridge(x, rng, base, rough):
    """mountain-ish ridge line: low frequencies + sharper high-frequency detail"""
    return base + waves(x, rng, [1.3, 3.1, 7.7, 17.0, 41.0], [.045 * rough, .03 * rough, .014 * rough, .006 * rough, .0025 * rough])


def over(img, colour, a):
    a = a[..., None] if a.ndim == 2 else a
    return img * (1 - a) + colour * a


def edge(y, line, px):
    """crisp AA coverage of the region below `line` (≈1 px wide transition)"""
    return smooth(-px, px, y - line)


def glow(x, y, cx, cy, rx, ry):
    return np.exp(-(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2))


def grain(img, rng, amt=1.6):
    """fine noise: dithers gradients (no banding after JPEG)"""
    return img + rng.normal(0, amt, img.shape[:2])[..., None]


# ── presets ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def aurora(size, rng):
    """night: indigo sky, green→violet aurora curtains with crisp lower hems, stars, layered dark ridges, still lake"""
    x, y = grid(size)
    px = 1 / size[1]
    img = ramp(y, [(0, "#03041a"), (.3, "#08113a"), (.55, "#0f2552"), (.68, "#16345e")])
    stars = (rng.random(size[::-1]) > .9982) * rng.uniform(.25, 1, size[::-1]) * smooth(.6, .15, y)
    img = img + stars[..., None] * 235
    for base, height, amp in [(.44, .24, 1.0), (.52, .14, .85), (.36, .2, .55)]:
        hem = base + waves(x, rng, [1.3, 3.1, 7.0, 15.0], [.09, .045, .018, .005])
        d = hem - y
        prof = np.where(d > 0, np.exp(-d / height), np.exp(-(d / .012) ** 2))
        rays = .62 + .38 * np.clip(.5 + sum(rng.uniform(.08, .22) * np.sin(f * x + rng.uniform(0, 6.3))
                                            for f in rng.uniform(14, 160, 16)), 0, 1)
        patch = .15 + .85 * smooth(-.3, .7, waves(x, rng, [1.6, 3.7], [1, .6]))
        col = ramp(d / height, [(0, "#5dffb0"), (.5, "#22d890"), (1.1, "#3f6cff"), (1.8, "#b04dff")])
        img = img + col * (prof * rays * patch * amp * .9)[..., None]
        img = img + rgb("#2bffa0") * (np.exp(-(d / .03) ** 2) * patch * amp * .12)[..., None]   # hem bloom
    far = ridge(x, rng, .60, 1.0)
    img = over(img, ramp(y - far, [(0, "#1d3358"), (.15, "#0b1530")]), edge(y, far, px))
    near = ridge(x, rng, .69, 1.5)
    img = over(img, ramp(y - near, [(0, "#0b1428"), (.12, "#050913")]), edge(y, near, px))
    shore = .81 + waves(x, rng, [2.1, 5.3], [.004, .002])
    ys = np.clip(((2 * shore - y) * size[1]).astype(int), 0, size[1] - 1)    # still water: sky + aurora mirrored
    refl = np.take_along_axis(img, ys[..., None].repeat(3, -1), axis=0) * .7 + rgb("#02040b") * .3
    ripple = .88 + .12 * np.sin(y * size[1] * .8 + waves(x, rng, [9, 21], [3, 2]))
    img = over(img, refl * ripple[..., None], edge(y, shore, px))
    return grain(img, rng)


def dusk(size, rng):
    """sunset: indigo → plum → coral → amber, low sun with glow, lit cloud streaks, hazy layered hills"""
    x, y = grid(size)
    px, A = 1 / size[1], size[0] / size[1]
    img = ramp(y, [(0, "#1d1b4a"), (.22, "#4a2c6e"), (.42, "#a2467a"), (.56, "#ef7a6e"), (.66, "#ffc27a")])
    sx, sy = A * .63, .60
    img = img + rgb("#ffb070") * (glow(x, y, sx, sy, .55, .22) * .55)[..., None]
    sun = smooth(.052 + px, .052 - px, np.hypot(x - sx, y - sy))
    img = over(img, rgb("#fff1d6"), sun)
    for cy, th, ln, op in [(.29, .012, .5, .35), (.355, .008, .38, .3), (.44, .014, .6, .4), (.47, .006, .3, .3)]:
        cx = rng.uniform(.2, A - .2)
        cl = cy + waves(x, rng, [2.3, 5.1], [.008, .003])
        band = np.exp(-(np.maximum(y - cl, (cl - y) * 2.2) / th) ** 2) * smooth(ln, 0, np.abs(x - cx))   # flat lit base
        img = over(img, ramp(y - cl, [(-.01, "#ff9fb0"), (.004, "#ffe0c8")]), band * op)
    layers = ["#c86a84", "#9a4a78", "#6c3466", "#46224f", "#2a1438"]
    for i, c in enumerate(layers):
        line = ridge(x, rng, .62 + i * .075, .55 + i * .25)
        tint = ramp(y - line, [(0, c), (.2, "#1a0c26")]) * .25 + rgb(c) * .75
        img = over(img, tint, edge(y, line, px))
        img = img + rgb("#ffb070") * (glow(x, y, sx, line.mean(), .5, .03) * .12 * (1 - i / 5) * edge(y, line, px))[..., None]
    return grain(img, rng)


def bloom(size, rng):
    """light: macOS-like pastel colour field + crisp translucent ribbons with bright rims"""
    x, y = grid(size)
    px, A = 1 / size[1], size[0] / size[1]
    img = ramp(y, [(0, "#f3eeff"), (1, "#fff0e8")])
    for c, cx, cy, r, op in [("#ff8a5c", .1, .9, .55, .9), ("#ff6fa8", .6, 1.0, .45, .8), ("#9a7bff", 1.0, .3, .6, .85),
                             ("#4fb4ff", .3, .05, .55, .85), ("#5fdcb4", 1.45, .95, .45, .7), ("#ffc85a", 1.55, .05, .4, .75)]:
        img = over(img, rgb(c), glow(x, y, cx * A / 1.6 + rng.uniform(-.05, .05), cy + rng.uniform(-.05, .05), r, r * .8) * op)
    for i, (c, base, op) in enumerate([("#ffffff", .38, .22), ("#9d7dff", .55, .22), ("#ff7fae", .68, .24), ("#ffffff", .82, .28)]):
        line = base + waves(x, rng, [1.2, 2.6, 4.9], [.08, .035, .012]) + .12 * (x / A - .5) * (-1) ** i
        below = edge(y, line, px)
        img = over(img, rgb(c), below * op * smooth(.5, 0, y - line))
        rim = np.exp(-((y - line) / (1.2 * px)) ** 2)
        img = over(img, rgb("#ffffff"), rim * .55)
    return grain(img, rng, 1.2)


def tide(size, rng):
    """vivid mid-tone: Big-Sur-like stacked waves sweeping diagonally, teal → ultramarine → violet, lit crests"""
    x, y = grid(size)
    px, A = 1 / size[1], size[0] / size[1]
    img = ramp(y - .25 * x / A, [(-.25, "#ffd6a8"), (.15, "#ff9fae"), (.4, "#8e7cf0"), (.75, "#2f3fb8")])
    img = img + rgb("#fff0c0") * (glow(x, y, A * .78, .05, .45, .2) * .45)[..., None]
    cols = ["#5fd6e6", "#2fb0d8", "#2f7fe0", "#3d4fd0", "#4a2fb0", "#2a1a78"]
    for i, c in enumerate(cols):
        line = .28 + i * .13 + .22 * (x / A - .5) + waves(x, rng, [2.2, 4.1, 9.0], [.05, .02, .006])
        below = edge(y, line, px)
        shade = ramp(y - line, [(0, c), (.16, "#120c40")]) * .35 + rgb(c) * .65
        img = over(img, shade, below)
        img = over(img, rgb("#e8fbff"), np.exp(-((y - line) / (1.4 * px)) ** 2) * .6)
        img = img + rgb("#ffffff") * (np.exp(-np.maximum(y - line, 0) / .012) * below * .10)[..., None]
    return grain(img, rng)


PRESETS = {"aurora": aurora, "dusk": dusk, "bloom": bloom, "tide": tide}
MODE = {"dark": "aurora", "light": "bloom"}


def for_mode(mode):
    return MODE.get(mode, MODE["dark"])


def make(name, size=(2560, 1600), seed=0):
    """preset name → RGB image (deterministic per seed)"""
    rng = np.random.default_rng([seed, sorted(PRESETS).index(name)])
    return Image.fromarray(np.clip(np.rint(PRESETS[name](size, rng)), 0, 255).astype("uint8"))


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    for n in PRESETS:
        make(n).save(out / f"{n}.png")
