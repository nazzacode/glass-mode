"""glasslab shots: gallery screenshots for the public showcase.

Per showcase screen (screens.json `"showcase"`) × glass mode: headless Zen + extension, goto + act, scramble private
scopes (`"private"`: probes/scramble.js), glass at the default slider, capture over black + white → exact colour +
alpha → showcase.render on an own procedural wallpaper (wallgen) → <out>/<screen>.<mode>.{jpg,webp}.
Only the scrambled, rendered result is written (no raw captures)."""
import asyncio, re, time
from pathlib import Path

from . import lab, showcase, wallgen
from .suite import DEFAULT_ALPHA, MODES, load_screens

VIEWPORT = (1440, 900)
DPR = 2                 # capture at 2× → crisp after the downscale into the 1536 px window
SEED = 1                # scramble seed: fixed → reruns give the same fake names


def select(screens, filt=""):
    return [s for s in screens if s.get("showcase") and re.search(filt, s["id"])]


def cfg(sc):
    return sc["showcase"] if isinstance(sc.get("showcase"), dict) else {}


def modes(sc, wanted=MODES):
    allowed = set(sc.get("modes", MODES)) & set(cfg(sc).get("modes", MODES))
    return [m for m in wanted if m in allowed]


def wallpaper(sc, mode):
    w = cfg(sc).get("wallpaper")
    w = w.get(mode) if isinstance(w, dict) else w
    return w or wallgen.for_mode(mode)


def private(sc):
    return sc.get("private") or None


async def capture(pg, sc, wanted):
    """→ [(mode, black, white)] for one screen"""
    await pg.goto(sc["url"], sc.get("settle", 7), sc.get("act"))
    if private(sc):
        print(f"  scrambled {await pg.probe('scramble', private(sc), SEED)}", flush=True)
    out = []
    for mode in modes(sc, wanted):
        await pg.glass(mode, DEFAULT_ALPHA)
        out.append((mode, await pg.shot("#000"), await pg.shot("#fff")))
        await pg.clear_backdrop()
    return out


async def run(xpi, screens, out, wanted, log):
    walls = {}
    async with lab.session(xpi, log, VIEWPORT) as pg:
        await pg.b.call("browsingContext.setViewport", context=pg.ctx,
                        viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, devicePixelRatio=DPR)
        for sc in screens:
            print(f"· {sc['id']}", flush=True)
            for mode, black, white in await capture(pg, sc, wanted):
                w = wallpaper(sc, mode)
                walls.setdefault(w, wallgen.make(w))
                paths = showcase.save(showcase.render(black, white, walls[w]), out / f"{sc['id']}.{mode}")
                print(f"  {mode:5s} on {w:7s} → {paths[0]}", flush=True)


def main(xpi, filt="", out=None, wanted=MODES):
    screens = select(load_screens(), filt)
    if not screens:
        raise SystemExit(f"glasslab shots: no showcase screens match {filt!r}")
    out = Path(out or Path(__file__).resolve().parents[2] / "site/shots")
    out.mkdir(parents=True, exist_ok=True)
    log = Path.home() / ".cache/glasslab" / f"shots-{time.strftime('%Y%m%d-%H%M%S')}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(xpi, screens, out, wanted, log))
    print(f"\nshots: {out}  (private screens scrambled; still check before publishing)")
    return 0
