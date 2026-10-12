"""glasslab shots: gallery screenshots for the public showcase.

Per showcase screen (screens.json `"showcase"`) × glass mode: headless Zen + extension, goto + act, scramble private
scopes (`"private"`: probes/scramble.js), glass at the default slider, capture over black + white → exact colour +
alpha → showcase.render on an own procedural wallpaper (wallgen) → <out>/<screen>.<mode>.{jpg,webp}.
Only the scrambled, rendered result is written (no raw captures).

--all: test gallery for the public site. EVERY screen × tested mode + every hidden-UI state the explorer opens
(explore.visit: triggers enumerated on the real page so DANGER sees real labels, then scrambled), glass at the default
slider → compact tile on a blurred own wallpaper → site/tests/<screen>[~<state>].<mode>.webp + index.json
(tile → screen, state, mode, result key). Private screens: scrambled before every capture (a reset may reload the page),
state names carry no page text (`ui-<n>`, joined to results by a hash `ref`). Numbers come from `test`, not from here."""
import asyncio, hashlib, json, re, time
from pathlib import Path

from PIL import Image

from . import explore, lab, showcase, wallgen
from .metrics import composite
from .suite import AUTO, DEFAULT_ALPHA, MODES, load_screens

TILE_W = 960
TILE_VIEWPORT = (1440, 900)

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


# ── --sweep: the one knob, animated ─────────────────────────────────────────────────────────────────────────────────
SWEEP = [round(0.1 * i, 1) for i in range(1, 10)]   # popup slider 10 … 90 %
SWEEP_SIZE = (1600, 1000)


def pingpong(xs):
    """10→90→20: a seamless loop without doubled end frames"""
    return list(xs) + list(xs[-2:0:-1])


def save_animation(frames, path, ms):
    seq = pingpong(frames)
    seq[0].save(path, save_all=True, append_images=seq[1:], duration=ms, loop=0, quality=80, method=4)
    return path


async def sweep(xpi, sc, mode, out, log):
    """one screen, the slider from 10 % to 90 % and back → <screen>.<mode>.sweep.webp (launch GIF)"""
    async with lab.session(xpi, log, VIEWPORT) as pg:
        await pg.b.call("browsingContext.setViewport", context=pg.ctx,
                        viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, devicePixelRatio=DPR)
        await pg.goto(sc["url"], sc.get("settle", 7), sc.get("act"))
        if private(sc):
            await pg.probe("scramble", private(sc), SEED)
        wall, frames = wallgen.make(wallpaper(sc, mode)), []
        for a in SWEEP:
            await pg.glass(mode, a)
            frames.append(showcase.render(await pg.shot("#000"), await pg.shot("#fff"), wall, size=SWEEP_SIZE))
            await pg.clear_backdrop()
            print(f"  {mode} {int(a * 100)}%", flush=True)
    return save_animation(frames, out / f"{sc['id']}.{mode}.sweep.webp", 220)


def main_sweep(xpi, screen, out=None, mode="dark"):
    sc = next((s for s in load_screens() if s["id"] == screen), None)
    if not sc:
        raise SystemExit(f"glasslab shots --sweep: no screen {screen!r}")
    out = Path(out or Path(__file__).resolve().parents[2] / "site/shots")
    out.mkdir(parents=True, exist_ok=True)
    print(asyncio.run(sweep(xpi, sc, mode, out, Path.home() / ".cache/glasslab/sweep.log")))
    return 0


# ── --all: test gallery tiles ─────────────────────────────────────────────────────────────────────────────────────────
def select_all(screens, filt=""):
    return [s for s in screens if re.search(filt, s["id"])]


def test_modes(sc, wanted=MODES):
    """modes the suite measures (screen restriction only; showcase restrictions are about beauty, not coverage)"""
    return [m for m in wanted if m in sc.get("modes", MODES)]


test_modes.__test__ = False         # pytest: not a test


def ref(key):
    """short stable hash: joins a private tile to its result row without carrying the (page-text) state label"""
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def state_name(sc, i, key, label):
    """explored state i (0-based) → tile stem + public label; private screens: ordinal only + hash ref of the real key"""
    if private(sc):
        return {"stem": f"{sc['id']}~ui-{i + 1}", "label": f"hidden UI {i + 1}", "key": None, "ref": ref(key)}
    return {"stem": key, "label": label, "key": key}


def entry(sc, mode, st):
    """index.json row for one tile"""
    suffix = f".{mode}.{int(DEFAULT_ALPHA * 100)}"
    e = {"file": f"{st['stem']}.{mode}.webp", "screen": sc["id"], "state": st["label"], "mode": mode,
         "key": st["key"] and st["key"] + suffix, "scrambled": bool(private(sc))}
    if st.get("ref"):
        e["ref"] = st["ref"] + suffix
    return e


def merge_index(old, new, shot):
    """re-shot screens (ids in `shot`) replace all their old rows; other screens keep theirs. Sorted by file"""
    return sorted([e for e in old if e["screen"] not in shot] + new, key=lambda e: e["file"])


def stale(old, new, shot):
    """tile files of re-shot screens that this run did not produce again → delete"""
    keep = {e["file"] for e in new}
    return [e["file"] for e in old if e["screen"] in shot and e["file"] not in keep]


def tile(black, white, wall, width=TILE_W):
    """exact composite of the capture onto the compositor-blurred wallpaper, `width` px wide"""
    img = composite(black, white, showcase.blurred(showcase.cover(wall, black.size)))
    return img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)


async def scramble(pg, sc):
    """private screen → scramble now (idempotent); refuse to go on if the scrambler didn't run"""
    if not private(sc):
        return
    if not (stats := await pg.probe("scramble", private(sc), SEED)):
        raise RuntimeError(f"{sc['id']}: scrambler did not run → no capture")
    await asyncio.sleep(0.3)        # let late paints settle after the text swap
    return stats


async def snap(pg, sc, ms, st, out, walls):
    rows = []
    for mode in ms:
        await scramble(pg, sc)
        await pg.glass(mode, DEFAULT_ALPHA)
        black, white = await pg.shot("#000"), await pg.shot("#fff")
        await pg.clear_backdrop()
        e = entry(sc, mode, st)
        tile(black, white, walls[mode]).save(out / e["file"], quality=82, method=6)
        rows.append(e)
    return rows


async def capture_all(pg, sc, wanted, out, walls):
    """one screen → index rows: base view per mode, then every explored state per mode"""
    await pg.goto(sc["url"], sc.get("settle", 7), sc.get("act"))
    if sc.get("auto"):
        await pg.eval(AUTO)
        await asyncio.sleep(1.5)
    ms = test_modes(sc, wanted)
    triggers = (await pg.probe("triggers", explore.DANGER, explore.MAX_TRIGGERS) or []) if sc.get("explore", True) else []
    if private(sc):
        print(f"  scrambled {await scramble(pg, sc)}", flush=True)
    rows = await snap(pg, sc, ms, {"stem": sc["id"], "label": None, "key": sc["id"]}, out, walls)
    n = 0

    async def one(key, t, layers):
        nonlocal n
        st = state_name(sc, n, key, t["label"])
        n += 1
        got = await snap(pg, sc, ms, st, out, walls)
        print(f"  ↳ {st['stem']}  {len(got)} tiles", flush=True)
        return got
    for got in await explore.visit(pg, sc["id"], one, triggers=triggers, settle=sc.get("settle", 7)):
        rows += got
    return rows


async def run_all(xpi, screens, out, wanted, log):
    walls = {m: wallgen.make(wallgen.for_mode(m), TILE_VIEWPORT) for m in MODES}
    index_path = out / "index.json"
    old = json.loads(index_path.read_text())["tiles"] if index_path.exists() else []
    new = []
    async with lab.session(xpi, log, TILE_VIEWPORT) as pg:
        for sc in screens:
            print(f"· {sc['id']}", flush=True)
            try:
                new += await capture_all(pg, sc, wanted, out, walls)
            except Exception as e:  # one broken screen (login wall, bot check) must not sink the gallery
                print(f"  skipped ({type(e).__name__}: {str(e)[:120]})", flush=True)
    done = {e["screen"] for e in new}
    for f in stale(old, new, done):
        (out / f).unlink(missing_ok=True)
    tiles = merge_index(old, new, done)
    index_path.write_text(json.dumps({"tiles": tiles}, indent=1) + "\n")
    return tiles


def main_all(xpi, filt="", out=None, wanted=MODES):
    screens = select_all(load_screens(), filt)
    if not screens:
        raise SystemExit(f"glasslab shots --all: no screens match {filt!r}")
    out = Path(out or Path(__file__).resolve().parents[2] / "site/tests")
    out.mkdir(parents=True, exist_ok=True)
    log = Path.home() / ".cache/glasslab" / f"shots-all-{time.strftime('%Y%m%d-%H%M%S')}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    tiles = asyncio.run(run_all(xpi, screens, out, wanted, log))
    print(f"\ntests gallery: {out}  ({len(tiles)} tiles; private screens scrambled; still look before publishing)")
    return 0


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
