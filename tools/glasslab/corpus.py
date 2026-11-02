"""corpus: frozen real pages, panels open, for the lab and for A vs B. Local only: holds private text, never commit or publish.

Two sources, one format (~/.cache/glasslab/corpus/<id>/{page.html, meta.json, assets/, shot.png}):
  - recorder extension (tools/glasslab/recorder): Alt+Shift+R in daily use → Downloads/glass-corpus → `./glasslab corpus import`
  - `./glasslab corpus seed`: the lab opens screens.json logged in + explores hidden UI, freezing as it goes
Replay: every request goes to a local proxy that serves the current capture at its own URL (over http: the proxy can't
terminate TLS), so site styles match and nothing touches the network. `check` scores frozen against live pixels."""
import asyncio, base64, hashlib, http.server, io, json, re, shutil, threading, time, zipfile
from pathlib import Path
from urllib.parse import unquote_to_bytes, urlsplit

import numpy as np
from PIL import Image

from . import explore, lab
from .suite import DEFAULT_ALPHA, load_screens

STORE = Path.home() / ".cache/glasslab/corpus"
INBOX = Path.home() / "Downloads/glass-corpus"
RECORDER = Path(__file__).parent / "recorder"
RECORDER_ID = "glass-recorder@nazzacode"
CHUNK = 2**24
SEED_TRIGGERS = 6
DRIFT_TOLERANCE = 24  # per channel, after a 4× downscale: text antialiasing isn't drift


def recorder_xpi(path, hook=False):
    """the extension as an xpi. hook=True (lab): + DOM-event trigger, freeze.js preloaded"""
    manifest = json.loads((RECORDER / "manifest.json").read_text())
    names = ["background.js", "freeze.js"]
    if hook:
        manifest["content_scripts"] = [{"matches": ["<all_urls>"], "js": ["freeze.js", "lab-hook.js"], "run_at": "document_idle"}]
        names.append("lab-hook.js")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest))
        for n in names:
            z.write(RECORDER / n, n)
    return path


def http_xpi(xpi, path):
    """the extension with https-only site patterns opened to http: replay is http (real builds keep theirs)"""
    with zipfile.ZipFile(xpi) as src, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        for i in src.infolist():
            data = src.read(i.filename)
            if i.filename == "data/ContentScripts.json":
                data = re.sub(rb"https:(?=//)", b"https?:", data)
            out.writestr(i, data)
    return path


def capture_id(meta):
    digest = hashlib.sha1(f"{meta['url']}{meta.get('recorded', '')}{meta.get('state', '')}".encode()).hexdigest()[:8]
    return f"{meta['host']}-{digest}"


def save(frozen, source, store=None, **extra):
    """frozen page → store; returns its id"""
    store = Path(store or STORE)
    html, shot, assets = frozen.pop("html"), frozen.pop("shot", None), frozen.pop("assets", {})
    meta = {**frozen, "source": source, **extra}
    meta.setdefault("recorded", time.strftime("%Y-%m-%dT%H:%M:%S"))
    cid = capture_id(meta)
    out = store / cid
    out.mkdir(parents=True, exist_ok=True)
    (out / "page.html").write_text(html)
    (out / "assets").mkdir(exist_ok=True)
    types = {}
    for name, url in assets.items():
        head, data = url.split(",", 1)
        types[name] = head[5:].split(";")[0] or "application/octet-stream"
        (out / "assets" / name).write_bytes(base64.b64decode(data) if head.endswith(";base64") else unquote_to_bytes(data))
    (out / "assets.json").write_text(json.dumps(types))
    if shot:
        (out / "shot.png").write_bytes(base64.b64decode(shot.split(",", 1)[1]))
    (out / "meta.json").write_text(json.dumps({**meta, "id": cid}, indent=1))
    return cid


def import_inbox(inbox=None, store=None):
    """recorder downloads → store; each download is removed once stored. Unreadable ones stay put and are reported"""
    inbox, got = Path(inbox or INBOX), []
    for f in sorted(inbox.glob("*.json")) if inbox.exists() else []:
        try:
            got.append(save(json.loads(f.read_text()), "recorder", store))
        except (ValueError, KeyError) as e:
            print(f"  skip {f.name}: {type(e).__name__}: {e}")
            continue
        f.unlink()
    return got


def captures(filt="", store=None):
    store = Path(store or STORE)
    metas = [json.loads(m.read_text()) for m in sorted(store.glob("*/meta.json"))] if store.exists() else []
    return [m for m in metas if re.search(filt, m["id"])]


def http_url(url):
    return re.sub(r"^https:", "http:", url)


class Replay(http.server.BaseHTTPRequestHandler):
    """every request: the current capture's page at its own URL, 404 for all else. Nothing reaches the network"""
    current = None  # (url, capture dir)

    def do_GET(self):
        body, kind = self.lookup()
        self.send_response(200 if body is not None else 404)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body or b"")))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body or b"")

    def lookup(self):
        url, cap = Replay.current or (None, None)
        if not url:
            return None, "text/plain"
        if self.path.split("#")[0] == url.split("#")[0]:
            return (cap / "page.html").read_bytes(), "text/html; charset=utf-8"
        name = urlsplit(self.path).path.removeprefix("/__gl/")
        f = cap / "assets" / name
        if "/" not in name and f.exists():
            return f.read_bytes(), json.loads((cap / "assets.json").read_text()).get(name, "application/octet-stream")
        return None, "text/plain"

    def do_CONNECT(self):
        self.send_error(502)

    def log_message(self, *a):
        pass


class Server:
    """context manager: local proxy + the prefs that send the whole session through it"""

    def __enter__(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Replay)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        pac = f'function FindProxyForURL(u, h) {{ return "PROXY 127.0.0.1:{self.srv.server_address[1]}"; }}'
        self.prefs = {"network.proxy.type": 2, "network.proxy.autoconfig_url": f"data:text/plain,{pac}", "dom.security.https_only_mode": False,
                      "network.stricttransportsecurity.preloadlist": False, "network.proxy.allow_hijacking_localhost": True,
                      "extensions.update.enabled": False, "app.update.enabled": False}
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        Replay.current = None


async def show(pg, meta, store=None):
    """load one capture in a replay session, at its recorded viewport"""
    w, h = meta["viewport"]
    await pg.b.call("browsingContext.setViewport", context=pg.ctx, viewport={"width": w, "height": h})
    url = http_url(meta["url"])
    Replay.current = (url, Path(store or STORE) / meta["id"])
    await pg.goto("about:blank", settle=0)  # same URL + #fragment is a same-document jump: the old capture would stay up
    await pg.goto(url, settle=1.5)


async def freeze(pg, timeout=60):
    """freeze the open page via the lab hook → dict; None if it didn't finish"""
    await pg.eval("delete window.__glFrozen; document.dispatchEvent(new CustomEvent('gl-freeze'))")
    for _ in range(timeout * 2):
        if await pg.eval("typeof window.__glFrozen === 'string'"):
            break
        await asyncio.sleep(0.5)
    else:
        return None
    size = await pg.eval("window.__glFrozen.length")
    parts = [await pg.eval(f"window.__glFrozen.slice({i}, {i + CHUNK})") for i in range(0, size, CHUNK)]
    await pg.eval("delete window.__glFrozen")
    return json.loads("".join(parts))


def drift(a, b, tolerance=DRIFT_TOLERANCE):
    """share of the window that differs between two renders of the same page (0 = identical)"""
    size = (a.width // 4, a.height // 4)
    x = np.asarray(a.convert("RGB").resize(size, Image.BOX), dtype=np.int16)
    y = np.asarray(b.convert("RGB").resize(size, Image.BOX), dtype=np.int16)
    return float((np.abs(x - y).max(axis=2) > tolerance).mean())


async def settled(pg, tries=6, gap=1.5):
    """wait until the page stops changing (lazy images, open animations); gives up quietly on pages that never rest"""
    last = await pg.shot("#000")
    for _ in range(tries):
        await asyncio.sleep(gap)
        now = await pg.shot("#000")
        if drift(last, now) < 0.005:
            return True
        last = now
    return False


async def snapshot(pg, source, store, **extra):
    """freeze + the live reference render → id (None: freeze failed). Reference = default glass over black, same as `check`"""
    await pg.glass("dark", DEFAULT_ALPHA)
    await settled(pg)
    frozen = await freeze(pg)
    if not frozen:
        print("  freeze timed out", flush=True)
        return None
    live = await pg.shot("#000")  # after the walk, so lazy pages have loaded in both
    await pg.clear_backdrop()
    cid = save(frozen, source, store, **extra)
    live.save(Path(store) / cid / "live.png")
    s = frozen["stats"]
    print(f"  ↳ {cid} {extra.get('state', 'page')[:40]!r} {s['bytes'] / 1e6:.1f} MB, {s['assets']} assets ({s['assetsFailed']} failed), "
          f"{s['sheetsFailed']} sheets failed, {s['framesLost']} frames lost, {s['ms']} ms", flush=True)
    return cid


async def seed_session(xpi, hook, screens, scheme, store, log, triggers):
    got = []
    async with lab.session(xpi, log, scheme=scheme, also=[(RECORDER_ID, hook)]) as pg:
        for sc in screens:
            print(f"· {sc['id']}", flush=True)
            await pg.open(sc)
            if await pg.wall():
                print("  WALL: skipped", flush=True)
                continue
            if cid := await snapshot(pg, "seed", store, screen=sc["id"]):
                got.append(cid)
            if not sc.get("explore", True) or sc.get("auto"):
                continue

            async def one(key, t, layers):
                return await snapshot(pg, "seed", store, screen=sc["id"], state=t["label"])
            got += await explore.visit(pg, sc["id"], one, settle=sc.get("settle", 7), max_triggers=triggers, private=bool(sc.get("private")))
    return got


def seed(xpi, filt="", store=None, triggers=SEED_TRIGGERS):
    """the lab walks screens.json logged in → frozen pages + hidden UI"""
    store = Path(store or STORE)
    store.mkdir(parents=True, exist_ok=True)
    hook = recorder_xpi(store / "recorder-lab.xpi", hook=True)
    screens = [s for s in load_screens(filt) if not s.get("replay") and not s.get("test_logged_out") and not s["url"].startswith("http://127")]
    got = []
    for scheme in dict.fromkeys(s.get("scheme", "dark") for s in screens):
        got += asyncio.run(seed_session(xpi, hook, [s for s in screens if s.get("scheme", "dark") == scheme], scheme, store,
                                        store / f"seed-{scheme}.log", triggers))
    return got


async def check_session(xpi, metas, scheme, store, log):
    rows = []
    with Server() as server:
        async with lab.session(xpi, log, scheme=scheme, extra_prefs=server.prefs) as pg:
            for m in metas:
                await show(pg, m, store)
                await pg.glass("dark", DEFAULT_ALPHA)
                frozen = await pg.shot("#000")
                await pg.clear_backdrop()
                frozen.save(Path(store) / m["id"] / "frozen.png")
                d = drift(Image.open(Path(store) / m["id"] / "live.png"), frozen)
                rows.append({"id": m["id"], "drift": d, "ready": await pg.eval("document.documentElement.dataset.glReady") == "1"})
                print(f"  {m['id']:44s} drift {d:5.1%}  {m.get('screen', '')} {m.get('state', '')[:30]}", flush=True)
    return rows


def check(xpi, filt="", store=None):
    """frozen vs live pixels for every capture with a lab reference; writes drift into meta.json"""
    store = Path(store or STORE)
    patched = http_xpi(xpi, store / "glass-http.xpi")
    metas = [m for m in captures(filt, store) if (store / m["id"] / "live.png").exists()]
    rows = []
    for scheme in dict.fromkeys(m["scheme"] for m in metas):
        rows += asyncio.run(check_session(patched, [m for m in metas if m["scheme"] == scheme], scheme, store, store / "check.log"))
    for r in rows:
        p = store / r["id"] / "meta.json"
        p.write_text(json.dumps({**json.loads(p.read_text()), "drift": r["drift"]}, indent=1))
    return rows


def install_recorder(profile=None):
    """drop the recorder into the live Zen profile: picked up on Zen's next start, never disturbs the running session"""
    profile = Path(profile or lab.live_profile())
    target = profile / "extensions" / f"{RECORDER_ID}.xpi"
    recorder_xpi(target)
    return target


def prune(ids, store=None):
    for i in ids:
        shutil.rmtree(Path(store or STORE) / i, ignore_errors=True)
