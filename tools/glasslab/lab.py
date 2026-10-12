"""Headless browser driver over WebDriver BiDi. Never touches the user's session or focus.

GLASSLAB_BROWSER=zen (default): Zen Flatpak, throwaway profile inside the sandbox, extension sideloaded unsigned, cookies
  copied from the live Zen profile → logged-in pages.
GLASSLAB_BROWSER=firefox: any Firefox ≥ 138 on PATH (or GLASSLAB_FIREFOX=path) — CI and contributors without Zen. Extension
  installed as a temporary add-on over BiDi (unsigned OK); cookies from a Zen profile if one exists, else logged out.
Same engine (Gecko), same CSS — results match except for login state."""
import asyncio, base64, configparser, contextlib, io, itertools, json, os, shutil, sqlite3, subprocess, time
from pathlib import Path

import websockets
from PIL import Image

APP = "app.zen_browser.zen"
SANDBOX = Path.home() / ".var/app" / APP
PORT = int(os.environ.get("GLASSLAB_PORT", 9333))  # one lab per port → parallel runs: GLASSLAB_PORT=9334 ./glasslab …
BROWSER = os.environ.get("GLASSLAB_BROWSER", "zen")
LAB = (SANDBOX / f"glasslab-{PORT}" if BROWSER == "zen"     # throwaway profile (the sandbox can only read its own dir)
       else Path.home() / ".cache/glasslab" / f"{BROWSER}-{PORT}")
EXT_ID = "transparent-zen@nazzacode"
PROBES = Path(__file__).parent / "probes"
KEY = {"Escape": "\uE00C", "Backspace": "\uE003", "Control": "\uE009", "Tab": "\uE004", "Enter": "\uE007"}  # WebDriver key values
MODIFIERS = {KEY["Control"]}
PREFS = {
    "xpinstall.signatures.required": False,
    "extensions.autoDisableScopes": 0,
    "extensions.enabledScopes": 15,
    "browser.tabs.allow_transparent_browser": True,
    "widget.transparent_windows": True,
    "zen.widget.linux.transparency": True,
    "browser.shell.checkDefaultBrowser": False,
    "zen.welcome-screen.seen": True,
    "browser.aboutwelcome.enabled": False,
    "remote.prefs.recommended": True,
    "ui.systemUsesDarkTheme": 1,
    "devtools.console.stdout.content": True,
}


def live_profile():
    """the profile Zen actually launches (profiles.ini [Install…] Default=), not a hard-coded name; None if no Zen"""
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    ini.read(SANDBOX / ".zen/profiles.ini")
    return next((SANDBOX / ".zen" / ini[s]["Default"] for s in ini.sections() if s.startswith("Install") and "Default" in ini[s]), None)


def command():
    common = ["--headless", "--no-remote", "--profile", str(LAB), f"--remote-debugging-port={PORT}"]
    if BROWSER == "zen":
        return ["flatpak", "run", "--command=/app/zen/zen", APP, *common]
    return [os.environ.get("GLASSLAB_FIREFOX", "firefox"), *common]


def setup(xpi):
    shutil.rmtree(LAB, ignore_errors=True)
    (LAB / "extensions").mkdir(parents=True)
    if xpi and BROWSER == "zen":  # None → plain browser (fixture pages carry their own style); firefox: BiDi install
        shutil.copy(xpi, LAB / "extensions" / f"{EXT_ID}.xpi")
    (LAB / "user.js").write_text("".join(f'user_pref("{k}", {json.dumps(v)});\n' for k, v in PREFS.items()))
    live = live_profile()
    if live is None:
        print("glasslab: no Zen profile → logged-out pages", flush=True)
        return
    # live Zen holds an exclusive lock → copy raw db + WAL, then fold the WAL in on the copy
    for ext in ("", "-wal"):
        if (live / f"cookies.sqlite{ext}").exists():
            shutil.copy(live / f"cookies.sqlite{ext}", LAB / f"cookies.sqlite{ext}")
    if (LAB / "cookies.sqlite").exists():
        db = sqlite3.connect(LAB / "cookies.sqlite")
        db.execute("pragma wal_checkpoint(truncate)")
        db.close()


def kill():
    """by profile path, anchored on the binary (an unanchored pattern also matches ssh/editor argv mentioning the path)"""
    binary = "/app/zen/zen" if BROWSER == "zen" else r"\S*firefox\S*"
    subprocess.run(["pkill", "-f", f"^{binary} .*--profile {LAB}"], check=False)


class Bidi:
    def __init__(self, ws):
        self.ws, self.ids = ws, itertools.count(1)

    async def call(self, method, **params):
        i = next(self.ids)
        await self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            m = json.loads(await self.ws.recv())
            if m.get("id") == i:
                if m.get("type") == "error":
                    raise RuntimeError(f"{method}: {m.get('message')}")
                return m["result"]

    async def eval(self, ctx, expr):
        r = await self.call("script.evaluate", expression=expr, target={"context": ctx}, awaitPromise=True)
        return r.get("result", {}).get("value")


class Page:
    """one browsing context + helpers used by every command"""

    def __init__(self, b, ctx):
        self.b, self.ctx = b, ctx

    async def eval(self, expr):
        return await self.b.eval(self.ctx, expr)

    async def probe(self, name, *args):
        """run probes/<name>.js (a function expression) with JSON args; probes return JSON strings"""
        lib, src = (PROBES / "_lib.js").read_text(), (PROBES / f"{name}.js").read_text()
        call = f"(() => {{ {lib}\nreturn ({src})({', '.join(json.dumps(a) for a in args)}); }})()"
        return json.loads(await self.eval(call) or "null")

    async def actions(self, *sources):
        """real (trusted) input via BiDi: sources = input.performActions sources"""
        await self.b.call("input.performActions", context=self.ctx, actions=list(sources))
        await self.b.call("input.releaseActions", context=self.ctx)

    async def click(self, x, y):
        await self.actions({"type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"}, "actions": [
            {"type": "pointerMove", "x": int(x), "y": int(y)}, {"type": "pointerDown", "button": 0}, {"type": "pointerUp", "button": 0}]})

    async def keys(self, *keys):
        """press keys in order (each = one key value: 'a', KEY['Escape'] …); KEY['Control'] etc. stay held until the end"""
        mods = [k for k in keys if k in MODIFIERS]
        acts = [{"type": "keyDown", "value": k} for k in mods]
        for k in keys:
            if k not in MODIFIERS:
                acts += [{"type": "keyDown", "value": k}, {"type": "keyUp", "value": k}]
        acts += [{"type": "keyUp", "value": k} for k in reversed(mods)]
        await self.actions({"type": "key", "id": "kbd", "actions": acts})

    async def goto(self, url, settle=7, act=None):
        try:
            await self.b.call("browsingContext.navigate", context=self.ctx, url=url, wait="complete")
        except RuntimeError as e:
            print(f"  nav: {e}")
        await asyncio.sleep(settle)
        if act:
            await self.eval(act)
            await asyncio.sleep(4)

    async def shot(self, backdrop=None):
        """screenshot; backdrop via CSSOM (Google pages enforce Trusted Types + CSP: no injected <style>)"""
        if backdrop:
            await self.eval(f"document.documentElement.style.setProperty('background','{backdrop}','important')")
            await asyncio.sleep(0.35)
        s = await self.b.call("browsingContext.captureScreenshot", context=self.ctx)
        return Image.open(io.BytesIO(base64.b64decode(s["data"])))

    async def clear_backdrop(self):
        await self.eval("document.documentElement.style.removeProperty('background')")

    async def glass(self, mode, alpha):
        await self.eval(f"document.documentElement.dataset.tzGlass='{mode}';"
                        f"document.documentElement.style.setProperty('--tz-glass-alpha','{alpha}')")
        await asyncio.sleep(0.4)

    async def detach_styles(self):
        """native render: remove the extension's stylesheets (headless → <link data-tz-file>), remember them"""
        await self.eval("window.__tz=[...document.querySelectorAll('link[data-tz-file]')];window.__tz.forEach(l=>l.remove());"
                        "document.documentElement.classList.remove('tz-initialized')")
        await asyncio.sleep(0.6)

    async def attach_styles(self):
        await self.eval("(window.__tz||[]).forEach(l=>document.head.append(l));document.documentElement.classList.add('tz-initialized')")
        await asyncio.sleep(0.8)


@contextlib.asynccontextmanager
async def session(xpi, log_path, viewport=(1400, 1000)):
    """start the headless browser with a fresh lab profile → Page; always cleaned up"""
    kill()
    time.sleep(1)
    setup(xpi)
    proc = subprocess.Popen(command(), stdout=open(log_path, "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                ws = await websockets.connect(f"ws://127.0.0.1:{PORT}/session", max_size=2**27)
                break
            except OSError:
                await asyncio.sleep(1)
        else:
            raise SystemExit(f"glasslab: {BROWSER} did not open the BiDi port (log: {log_path})")
        b = Bidi(ws)
        await b.call("session.new", capabilities={})
        if xpi and BROWSER != "zen":
            await b.call("webExtension.install", extensionData={"type": "archivePath", "path": str(Path(xpi).resolve())})
        ctx = (await b.call("browsingContext.getTree"))["contexts"][0]["context"]
        if BROWSER != "zen":  # Firefox's first context needs -remote-allow-system-access to resize → use a fresh tab
            ctx = (await b.call("browsingContext.create", type="tab"))["context"]
        await b.call("browsingContext.setViewport", context=ctx, viewport={"width": viewport[0], "height": viewport[1]})
        yield Page(b, ctx)
        await ws.close()
    finally:
        proc.terminate()  # zen: reaches only the flatpak wrapper; the sandboxed zen lives on → kill by profile
        kill()
