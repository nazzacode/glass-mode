"""glasslab test: readability + unity matrix for every screen in screens.json.

Per screen × glass mode × slider alpha:
  - captures over pure black and pure white → exact per-pixel colour + alpha (CSP-proof), composited offline onto
    blurred wallpapers (backdrops) → contact sheets
  - text probe: every visible text run, APCA through its real paint stack over the backdrop bounds (darkest / brightest
    blurred-wallpaper patch). Target per run: size floor (75 body · 60 labels/controls · 45 large), relaxed to the site's
    own native contrast ×0.9 where the native design is already below it → glass never reads worse than the site.
  - unity: surfaces must be glass.css tiers; neutral text must be a shared foreground.
Exemptions (reported, not scored): text on site data colours / images / accent fills — void if glass changed its colour.
"""
import asyncio, json, os, re, time
from pathlib import Path

import numpy as np
from PIL import Image

from . import lab
from .metrics import TARGETS, composite, rkey, score, verdict

HERE = Path(__file__).parent
ALPHAS = [0.1, 0.45, 0.9]          # popup slider extremes + default
DEFAULT_ALPHA = 0.45
MODES = ["dark", "light"]
REGRESSION = 0.03                   # baseline compare: a metric dropping more than this fails
BACKDROPS = Path(os.environ.get("GLASSLAB_BACKDROPS", Path.home() / ".cache/glasslab/backdrops"))
DEFAULT_BOUNDS = [[0, 0, 0], [222, 222, 222]]   # measured over 22 live wallpapers (p5 / p95, blurred) on 2026-10-09


def backdrops():
    """bounds + wallpaper images from `glasslab wallpapers`; synthetic fallback so the suite always runs"""
    meta = BACKDROPS / "bounds.json"
    if meta.exists():
        m = json.loads(meta.read_text())
        return m["bounds"], {w: Image.open(BACKDROPS / f"{w}.png") for w in m["sheet"]}
    sky = Image.linear_gradient("L").resize((1400, 1000)).convert("RGB")
    return DEFAULT_BOUNDS, {"synthetic-day": Image.eval(sky, lambda v: 120 + v // 3), "synthetic-night": Image.eval(sky, lambda v: v // 6)}


def load_screens(filt=""):
    data = json.loads((HERE / "screens.json").read_text())
    return [s for s in data["screens"] if re.search(filt, s["id"])]










async def run_screens(xpi, out, screens, bounds):
    results = []
    async with lab.session(xpi, out / "zen.log") as pg:
        for sc in screens:
            print(f"· {sc['id']}", flush=True)
            await pg.goto(sc["url"], sc.get("settle", 7), sc.get("act"))
            await pg.detach_styles()
            (await pg.shot()).save(out / "shots" / f"{sc['id']}.native.png")
            native = {rkey(r): (min(r["cr"]), r["fg"]) for r in (await pg.probe("text", bounds, [0, 0, 0, 0]) or [])}
            await pg.attach_styles()
            for mode in sc.get("modes", MODES):
                for a in ALPHAS:
                    await pg.glass(mode, a)
                    key = f"{sc['id']}.{mode}.{int(a * 100)}"
                    (await pg.shot("#000")).save(out / "raw" / f"{key}.black.png")
                    (await pg.shot("#fff")).save(out / "raw" / f"{key}.white.png")
                    await pg.clear_backdrop()
                    runs = await pg.probe("text", bounds, [0, 0, 0, 0]) or []
                    unity = await pg.probe("unity") or {}
                    m = score(runs, native, unity.get("fgs", []), unity)
                    m.update(key=key, screen=sc["id"], mode=mode, alpha=a, ok=verdict(m))
                    results.append(m)
                    print(f"  {key:30s} contrast {min(m['contrast']):4.0%}  surface {m['surface']:4.0%}  text {m['text']:4.0%}"
                          f"  {'ok' if m['ok'] else 'FAIL'}", flush=True)
    return results




def sheets(results, out, walls):
    first = next(iter(walls.values()))
    for scr in dict.fromkeys(r["screen"] for r in results):
        modes = [m for m in MODES if (out / "raw" / f"{scr}.{m}.{int(ALPHAS[0] * 100)}.black.png").exists()]
        rows = []
        for mode in modes:
            row = []
            for a in ALPHAS:
                key = f"{scr}.{mode}.{int(a * 100)}"
                img = composite(Image.open(out / "raw" / f"{key}.black.png"), Image.open(out / "raw" / f"{key}.white.png"), first)
                img.save(out / "shots" / f"{key}.png")
                row.append(img)
            rows.append(row)
        for mode in modes:
            key = f"{scr}.{mode}.{int(DEFAULT_ALPHA * 100)}"
            blk, wht = Image.open(out / "raw" / f"{key}.black.png"), Image.open(out / "raw" / f"{key}.white.png")
            rows.append([composite(blk, wht, w) for w in walls.values()])
        tw, th = 700, 500
        sheet = Image.new("RGB", (max(map(len, rows)) * tw, len(rows) * th), (40, 40, 40))
        for y, row in enumerate(rows):
            for x, im in enumerate(row):
                sheet.paste(im.resize((tw, th)), (x * tw, y * th))
        sheet.save(out / f"sheet-{scr}.jpg", quality=85)


def summary_md(results):
    lines = ["| screen | mode | α | texts | contrast dark bg | contrast bright bg | surface | text | ok | worst |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        w = r["failing"][0] if r["failing"] else None
        c = r["contrast"] + r["contrast"][-1:]
        lines.append(f"| {r['screen']} | {r['mode']} | {int(r['alpha'] * 100)} | {r['texts']} | {c[0]:.0%} | {c[1]:.0%} | "
                     f"{r['surface']:.0%} | {r['text']:.0%} | {'✓' if r['ok'] else '✗'} | "
                     + (f"`{w['sel']}` Lc {min(w['lc'])} (target {w['target']})" if w else "") + " |")
    return "\n".join(lines) + "\n"


def baseline_numbers(results):
    """numbers only (no page text) → safe to commit"""
    return {r["key"]: {"contrast": min(r["contrast"]), "surface": r["surface"], "text": r["text"], "ok": r["ok"]} for r in results}


def compare(results, baseline):
    regs = []
    for k, now in baseline_numbers(results).items():
        was = baseline.get(k)
        if not was:
            continue
        for m in ("contrast", "surface", "text"):
            if now[m] < was[m] - REGRESSION:
                regs.append(f"{k} {m} {was[m]:.0%} → {now[m]:.0%}")
    return regs


def main(xpi, filt="", out=None, save_baseline=False, compare_baseline=False):
    screens = load_screens(filt)
    if not screens:
        raise SystemExit(f"glasslab: no screens match {filt!r}")
    out = Path(out or Path.home() / ".cache/glasslab/runs" / time.strftime("%Y%m%d-%H%M%S"))
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "shots").mkdir(exist_ok=True)
    bounds, walls = backdrops()
    results = asyncio.run(run_screens(xpi, out, screens, bounds))
    sheets(results, out, walls)
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "summary.md").write_text(summary_md(results))
    fails = [r["key"] for r in results if r["alpha"] == DEFAULT_ALPHA and not r["ok"]]
    extremes = [r["key"] for r in results if r["alpha"] != DEFAULT_ALPHA and not r["ok"]]
    bl = HERE / "baseline.json"
    regs = compare(results, json.loads(bl.read_text())) if compare_baseline and bl.exists() else []
    if save_baseline:
        merged = json.loads(bl.read_text()) if bl.exists() else {}
        merged.update(baseline_numbers(results))
        bl.write_text(json.dumps(dict(sorted(merged.items())), indent=1) + "\n")
    print(f"\nrun: {out}\nfails at default α: {fails or 'none'}\nfails at slider extremes: {extremes or 'none'}"
          + (f"\nregressions vs baseline: {regs or 'none'}" if compare_baseline else ""))
    return 1 if fails or regs else 0
