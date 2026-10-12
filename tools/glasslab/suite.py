"""glasslab test: readability + unity matrix for every screen in screens.json, and for the hidden UI each screen opens.

Per screen × glass mode × slider alpha:
  - captures over pure black and pure white → exact per-pixel colour + alpha (CSP-proof), composited offline onto
    blurred wallpapers (backdrops) → contact sheets; `glass` = share of the window where the desktop shows through
  - text probe: every visible text run, APCA through its real paint stack over the backdrop bounds (darkest / brightest
    blurred-wallpaper patch). Target per run: size floor (75 body · 60 labels/controls · 45 large), relaxed to the site's
    own native contrast ×0.9 where the native design is already below it → glass never reads worse than the site.
  - unity: surfaces must be glass.css tiers; neutral text must be a shared foreground.
Then (default alpha, every mode) `explore` opens menus / dropdowns / dialogs / suggestions read-only and scores each layer
the same way + opacity (explore.py). Exemptions (reported, not scored): text on site data colours / images / accent fills.
"""
import asyncio, json, os, re, time
from pathlib import Path

from PIL import Image

from . import explore, lab
from .metrics import alpha_map, composite, glass_share, rkey, score, verdict

HERE = Path(__file__).parent
ALPHAS = [0.1, 0.45, 0.9]          # popup slider extremes + default
DEFAULT_ALPHA = 0.45
MODES = ["dark", "light"]
REGRESSION = 0.03                   # baseline compare: a metric dropping more than this fails
BACKDROPS = Path(os.environ.get("GLASSLAB_BACKDROPS", Path.home() / ".cache/glasslab/backdrops"))
DEFAULT_BOUNDS = [[0, 0, 0], [222, 222, 222]]   # measured over 22 live wallpapers (p5 / p95, blurred) on 2026-10-09
METRICS = ("contrast", "surface", "text")
AUTO = "document.dispatchEvent(new CustomEvent('tz-auto-glass'))"


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


def state_rows(states, screen, alpha):
    """explored states → one result row per mode (key <screen>~<state>.<mode>.<α>)"""
    return [{**m, "key": f"{s['key']}.{mode}.{int(alpha * 100)}", "screen": screen, "state": s["trigger"]["label"],
             "mode": mode, "alpha": alpha, "layers": s["layers"]}
            for s in states for mode, m in s["modes"].items()]


async def measure_screen(pg, sc, out, bounds):
    pg_rows = []
    await pg.detach_styles()
    (await pg.shot()).save(out / "shots" / f"{sc['id']}.native.png")
    native = {rkey(r): (min(r["cr"]), r["fg"]) for r in (await pg.probe("text", bounds, [0, 0, 0, 0]) or [])}
    await pg.attach_styles()
    for mode in sc.get("modes", MODES):
        for a in ALPHAS:
            await pg.glass(mode, a)
            key = f"{sc['id']}.{mode}.{int(a * 100)}"
            black, white = await pg.shot("#000"), await pg.shot("#fff")
            black.save(out / "raw" / f"{key}.black.png")
            white.save(out / "raw" / f"{key}.white.png")
            await pg.clear_backdrop()
            unity = await pg.probe("unity") or {}
            m = score(await pg.probe("text", bounds, [0, 0, 0, 0]) or [], native, unity.get("fgs", []), unity)
            m.update(key=key, screen=sc["id"], mode=mode, alpha=a, ok=verdict(m), glass=glass_share(alpha_map(black, white)))
            pg_rows.append(m)
            print(f"  {key:30s} contrast {min(m['contrast']):4.0%}  surface {m['surface']:4.0%}  text {m['text']:4.0%}"
                  f"  glass {m['glass']:4.0%}  {'ok' if m['ok'] else 'FAIL'}", flush=True)
    return pg_rows


async def run_screens(xpi, out, screens, bounds, do_explore=True):
    results = []
    async with lab.session(xpi, out / "zen.log") as pg:
        for sc in screens:
            print(f"· {sc['id']}", flush=True)
            await pg.goto(sc["url"], sc.get("settle", 7), sc.get("act"))
            if sc.get("auto"):  # site without a style → measure auto glass (same switch as the popup toggle)
                await pg.eval(AUTO)
                await asyncio.sleep(1.5)
            results += await measure_screen(pg, sc, out, bounds)
            if do_explore and sc.get("explore", True):
                states = await explore.explore(pg, bounds, sc["id"], sc.get("modes", MODES), DEFAULT_ALPHA, out / "raw",
                                               settle=sc.get("settle", 7), private=bool(sc.get("private")))
                results += state_rows(states, sc["id"], DEFAULT_ALPHA)
    return results


def sheets(results, out, walls):
    """per screen: modes × slider on the first wallpaper, default α on every wallpaper; explored states: one row each"""
    first = next(iter(walls.values()))
    shot = lambda key, wall: composite(Image.open(out / "raw" / f"{key}.black.png"), Image.open(out / "raw" / f"{key}.white.png"), wall)
    for scr in dict.fromkeys(r["screen"] for r in results):
        mine = [r for r in results if r["screen"] == scr]
        rows = []
        for mode in dict.fromkeys(r["mode"] for r in mine if "state" not in r):
            row = []
            for a in ALPHAS:
                img = shot(f"{scr}.{mode}.{int(a * 100)}", first)
                img.save(out / "shots" / f"{scr}.{mode}.{int(a * 100)}.png")
                row.append(img)
            rows.append(row)
            rows.append([shot(f"{scr}.{mode}.{int(DEFAULT_ALPHA * 100)}", w) for w in walls.values()])
        for r in (r for r in mine if "state" in r):
            img = shot(r["key"], first)
            img.save(out / "shots" / f"{r['key']}.png")
            rows.append([img])
        tw, th = 700, 500
        sheet = Image.new("RGB", (max(map(len, rows)) * tw, len(rows) * th), (40, 40, 40))
        for y, row in enumerate(rows):
            for x, im in enumerate(row):
                sheet.paste(im.resize((tw, th)), (x * tw, y * th))
        sheet.save(out / f"sheet-{scr}.jpg", quality=85)


def summary_md(results):
    lines = ["| screen | state | mode | α | texts | contrast dark bg | contrast bright bg | surface | text | glass / layer α | ok | worst |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        w = r["failing"][0] if r["failing"] else None
        c = r["contrast"] + r["contrast"][-1:]
        g = f"opacity {r['opacity']:.2f}" if "state" in r else f"{r.get('glass', 0):.0%}"
        lines.append(f"| {r['key'].split('.')[0]} | {r.get('state', '')} | {r['mode']} | {int(r['alpha'] * 100)} | "
                     f"{r['texts']} | {c[0]:.0%} | {c[1]:.0%} | {r['surface']:.0%} | {r['text']:.0%} | {g} | {'✓' if r['ok'] else '✗'} | "
                     + (f"`{w['sel']}` Lc {min(w['lc'])} (target {w['target']})" if w else "") + " |")
    return "\n".join(lines) + "\n"


def failures(results, default_only=True):
    return [r["key"] for r in results if not r["ok"] and (r["key"].endswith(f".{int(DEFAULT_ALPHA * 100)}")) == default_only]


def baseline_numbers(results):
    """numbers only (no page text) → safe to commit"""
    return {r["key"]: {"contrast": min(r["contrast"]), "surface": r["surface"], "text": r["text"], "ok": r["ok"]} for r in results}


def compare(results, baseline):
    regs = []
    for k, now in baseline_numbers(results).items():
        was = baseline.get(k)
        for m in METRICS if was else ():
            if now[m] < was[m] - REGRESSION:
                regs.append(f"{k} {m} {was[m]:.0%} → {now[m]:.0%}")
    return regs


def run(xpi, filt="", out=None, do_explore=True):
    """measure every matching screen (+ hidden UI) → result rows; writes raw captures, sheets, results.json, summary.md"""
    screens = load_screens(filt)
    if not screens:
        raise SystemExit(f"glasslab: no screens match {filt!r}")
    out = Path(out or Path.home() / ".cache/glasslab/runs" / time.strftime("%Y%m%d-%H%M%S"))
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "shots").mkdir(exist_ok=True)
    bounds, walls = backdrops()
    results = asyncio.run(run_screens(xpi, out, screens, bounds, do_explore))
    sheets(results, out, walls)
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "summary.md").write_text(summary_md(results))
    print(f"\nrun: {out}")
    return results


def main(xpi, filt="", out=None, save_baseline=False, compare_baseline=False, do_explore=True):
    results = run(xpi, filt, out, do_explore)
    fails, extremes = failures(results), failures(results, default_only=False)
    bl = HERE / "baseline.json"
    regs = compare(results, json.loads(bl.read_text())) if compare_baseline and bl.exists() else []
    if save_baseline:
        merged = json.loads(bl.read_text()) if bl.exists() else {}
        merged.update(baseline_numbers(results))
        bl.write_text(json.dumps(dict(sorted(merged.items())), indent=1) + "\n")
    print(f"fails at default α (screens + hidden UI): {fails or 'none'}\nfails at slider extremes: {extremes or 'none'}"
          + (f"\nregressions vs baseline: {regs or 'none'}" if compare_baseline else ""))
    return 1 if fails or regs else 0
