"""pure scoring maths shared by `test` (whole screens) and `explore` (hidden UI layers). No browser, unit-tested."""
import re

import numpy as np
from PIL import Image

TARGETS = {"contrast": 0.9, "surface": 0.9, "text": 0.85, "exempt_max": 0.1}
LAYER_ALPHA = 0.8       # menus/dialogs/suggestions: below this the page behind bleeds through their text (popover tier ≥ .85)
CLEAR = 0.97            # a pixel counts as glass (desktop shows through) below this alpha


def alpha_map(black, white):
    """exact per-pixel alpha from the page captured over pure black and pure white: α = 1 − (W − B)/255"""
    B = np.asarray(black.convert("RGB"), dtype=np.float32)
    W = np.asarray(white.convert("RGB"), dtype=np.float32)
    return np.clip(1 - (W - B).mean(axis=2) / 255, 0, 1)


def region_alpha(alpha, rect):
    """mean alpha inside rect [x, y, w, h] (clipped to the image)"""
    x, y, w, h = (int(round(v)) for v in rect)
    a = alpha[max(0, y):max(0, y + h), max(0, x):max(0, x + w)]
    return round(float(a.mean()), 3) if a.size else 1.0


def glass_share(alpha):
    """share of the window where the desktop shows through (is the page actually glass?)"""
    return round(float((alpha < CLEAR).mean()), 3)


def composite(black, white, wall):
    """exact: out = B + (1 − α)·wall"""
    B = np.asarray(black.convert("RGB"), dtype=np.float32)
    a = alpha_map(black, white)[..., None]
    bg = np.asarray(wall.convert("RGB").resize(black.size), dtype=np.float32)
    return Image.fromarray(np.clip(B + (1 - a) * bg, 0, 255).astype("uint8"))


def rkey(r):
    """identity of a text run across native/glass renders: selector + text + position (layout is identical)"""
    return (r["sel"], r["t"], r.get("x", 0) // 4, r.get("y", 0) // 4)


def neutral_text_conformance(runs, fgs, tol=10):
    """share of neutral text chars whose colour is a glass foreground (saturated text = accent/status, ignored)"""
    ok = tot = 0
    foreign = {}
    for r in runs:
        c = [float(x) for x in re.findall(r"[\d.]+", r["fg"])[:3]]
        if len(c) < 3 or max(c) - min(c) > 24:
            continue
        tot += r["n"]
        if any(f and all(abs(c[i] - f[i]) <= tol for i in range(3)) for f in fgs):
            ok += r["n"]
        else:
            k = f"{r['fg']} {r['sel']}"
            foreign[k] = foreign.get(k, 0) + r["n"]
    return (ok / tot if tot else 1.0), sorted(foreign.items(), key=lambda x: -x[1])[:6]


def scored_bounds(mode, n):
    """indices of the n wallpaper bounds (ordered darkest → brightest) that gate contrast for a glass mode. Light glass is
    promised on bright wallpapers → brightest bound only; dark glass (and native/unknown) → every bound. The rest are
    still measured and reported (`contrast_all`), never gating."""
    return [n - 1] if mode == "light" and n else list(range(n))


def score(runs, native, fgs, unity, mode=None):
    """split exempt runs, set per-run targets (size floor, relaxed to native ×0.9), contrast pass per bound + unity.
    `contrast` = scored bounds only (scored_bounds(mode)); `contrast_all` = every bound, darkest → brightest (informational)"""
    def exempt(r):
        nv = native.get(rkey(r))
        return (r.get("chip") or r.get("img")) and nv is not None and nv[1] == r["fg"]
    ex = [r for r in runs if exempt(r)]
    sc = [r for r in runs if not exempt(r)]
    for r in sc:
        nv = native.get(rkey(r))
        r["native"] = nv and nv[0]
        r["target"] = r["need"] if nv is None else min(r["need"], nv[0] * 0.9)
    tot = sum(r["n"] for r in sc) or 1
    nb = len(sc[0]["cr"]) if sc else 0
    contrast_all = [sum(r["n"] for r in sc if r["cr"][k] >= r["target"]) / tot for k in range(nb)] or [1.0]
    idx = scored_bounds(mode, nb)
    contrast = [contrast_all[k] for k in idx] or [1.0]
    text, text_foreign = neutral_text_conformance(sc, fgs)
    failing = {}
    for r in sc:
        lc = [r["cr"][k] for k in idx]
        if min(lc) < r["target"]:
            g = failing.setdefault(r["sel"], {"sel": r["sel"], "chars": 0, "lc": lc, "target": round(r["target"]), "fg": r["fg"], "t": r["t"]})
            g["chars"] += r["n"]
    img_exempt = sum(r["n"] for r in ex if r.get("img") and not r.get("chip")) / max(1, sum(r["n"] for r in runs))
    return {"texts": len(sc), "exempt": len(ex), "exempt_img_share": round(img_exempt, 3), "contrast": [round(v, 3) for v in contrast],
            "contrast_all": [round(v, 3) for v in contrast_all],
            "surface": round(unity.get("surface", 0), 3), "text": round(text, 3), "tiers": unity.get("tiers", {}),
            "surface_foreign": unity.get("foreign", []), "text_foreign": text_foreign,
            "failing": sorted(failing.values(), key=lambda g: -g["chars"])[:10]}


def verdict(m):
    return (min(m["contrast"]) >= TARGETS["contrast"] and m["surface"] >= TARGETS["surface"]
            and m["text"] >= TARGETS["text"] and m["exempt_img_share"] <= TARGETS["exempt_max"])


def layer_ok(m):
    """hidden-UI layer (menu, dialog, suggestions): screen verdict + opaque enough that the page doesn't bleed through —
    where there is page beneath (over_content); a drawer over clear glass is frame glass and may be thin"""
    return verdict(m) and (m["opacity"] >= LAYER_ALPHA or not m.get("over_content", True))
