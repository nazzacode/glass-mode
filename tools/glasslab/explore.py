"""glasslab explore: open a screen's hidden UI (menus, dropdowns, dialogs, search suggestions) and score every surface
that appears like a screen: tier unity, text contrast — and opacity, so a popover never lets the page bleed through.

Read-only by construction: only controls that reveal UI (aria-haspopup / aria-expanded / combobox / search fields) are
activated; never navigation links, submit buttons, or anything whose label matches DANGER. Typing goes into search fields
only and is never submitted. After each state the page is restored (Escape → blur → reload as a last resort)."""
import asyncio, json, re

from PIL import Image

from .lab import KEY
from .metrics import alpha_map, layer_ok, region_alpha, rkey, score

DANGER = (r"delet|remov|discard|trash|spam|archiv|send|repl|forward|\bpost|publish|tweet|share|invite|sign.?out|log.?out"
          r"|subscri|follow|block|report|mute|leave|buy|pay|purchase|order|checkout|call|install|download|upgrade|clear|reset"
          r"|empty|cancel|account|profile")
MAX_TRIGGERS = 12
QUERY = "the"              # typed into search fields to raise suggestions; never submitted
LOCATE = """(sel => { let e = null; try { e = document.querySelector(sel); } catch (_) {} const r = e && e.getBoundingClientRect();
  return JSON.stringify(r && r.width && r.height ? [r.left + r.width / 2, r.top + r.height / 2] : null); })(%s)"""


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:32] or "control"


async def activate(pg, t):
    pos = json.loads(await pg.eval(LOCATE % json.dumps(t["sel"])) or "null")
    if not pos:
        return False
    await pg.click(*pos)
    await asyncio.sleep(0.6)
    if t["kind"] == "type":
        await pg.keys(*QUERY)
        await asyncio.sleep(1.2)
    return True


async def restored(pg, url):
    return not await pg.probe("layers", "diff") and await pg.eval("location.href") == url


async def reset(pg, url, t, settle):
    if t["kind"] == "type":
        await pg.keys(KEY["Control"], "a")
        await pg.keys(KEY["Backspace"])
    for step in ("Escape", "blur"):
        if step == "Escape":
            await pg.keys(KEY["Escape"])
        else:
            await pg.eval("document.activeElement && document.activeElement.blur()")
        await asyncio.sleep(0.4)
        if await restored(pg, url):
            return
    await pg.goto(url, settle)


async def measure(pg, key, layers, bounds, modes, alpha, shots):
    scopes = [l["sel"] for l in layers]
    glass = {}
    for mode in modes:
        await pg.glass(mode, alpha)
        black, white = await pg.shot("#000"), await pg.shot("#fff")
        await pg.clear_backdrop()
        if shots:
            black.save(shots / f"{key}.{mode}.{int(alpha * 100)}.black.png")
            white.save(shots / f"{key}.{mode}.{int(alpha * 100)}.white.png")
        a = alpha_map(black, white)
        glass[mode] = (await pg.probe("text", bounds, [0, 0, 0, 0], scopes) or [], await pg.probe("unity", scopes) or {},
                       min(region_alpha(a, l["panel"]) for l in layers))
    await pg.detach_styles()                       # native twins last: detaching may close fragile popups
    native = {rkey(r): (min(r["cr"]), r["fg"]) for r in (await pg.probe("text", bounds, [0, 0, 0, 0], scopes) or [])}
    await pg.attach_styles()
    out = {}
    for mode, (runs, unity, a) in glass.items():
        m = score(runs, native, unity.get("fgs", []), unity)
        m["opacity"] = a
        m["over_content"] = any(l["over"] for l in layers)
        m["ok"] = layer_ok(m)
        out[mode] = m
    return out


async def visit(pg, screen, fn, triggers=None, settle=3, max_triggers=MAX_TRIGGERS):
    """open each safe trigger's hidden UI → await fn(key, trigger, layers) while it is open → [non-None results].
    Page restored after every trigger. `triggers` lets a caller enumerate first (on the real page: DANGER needs real labels)."""
    url = await pg.eval("location.href")
    out = []
    for t in triggers if triggers is not None else await pg.probe("triggers", DANGER, max_triggers) or []:
        try:
            await pg.probe("layers", "mark")
            if await activate(pg, t) and (layers := await pg.probe("layers", "diff") or []):
                if (r := await fn(f"{screen}~{slug(t['label'] or t['id'])}", t, layers)) is not None:
                    out.append(r)
        except Exception as e:  # one odd control must not sink the run (re-rendered DOM, navigation, …)
            print(f"  ↳ {t['label'][:30]!r}: skipped ({type(e).__name__}: {str(e)[:80]})", flush=True)
        await reset(pg, url, t, settle)
    return out


async def explore(pg, bounds, screen="page", modes=("dark", "light"), alpha=0.45, shots=None, settle=3, max_triggers=MAX_TRIGGERS):
    """→ [{key, trigger, layers, modes: {mode: metrics}, ok}] for every trigger that revealed a floating layer"""
    async def one(key, t, layers):
        modes_m = await measure(pg, key, layers, bounds, modes, alpha, shots)
        s = {"key": key, "trigger": t, "layers": layers, "modes": modes_m, "ok": all(m["ok"] for m in modes_m.values())}
        print(f"  ↳ {s['key']:38s} " + "  ".join(f"{md} surface {m['surface']:4.0%} opacity {m['opacity']:.2f}"
              f"{'' if m['over_content'] else ' (clear)'} contrast {min(m['contrast']):4.0%}" for md, m in modes_m.items())
              + f"  {'ok' if s['ok'] else 'FAIL'}", flush=True)
        return s
    return await visit(pg, screen, one, settle=settle, max_triggers=max_triggers)
