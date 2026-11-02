"""corpus: freeze keeps live state and drops scripts + Glass Mode's own marks; drift; import; replay. No private text in fixtures."""
import asyncio, json, zipfile

import pytest
from PIL import Image

from tools.glasslab import corpus, lab
from tools.glasslab.tests.test_extension import xpi  # noqa: F401  (fixture)


def test_drift_ignores_antialiasing_but_sees_a_panel():
    a = Image.new("RGB", (400, 400), (20, 20, 20))
    assert corpus.drift(a, a) == 0
    assert corpus.drift(a, Image.new("RGB", (400, 400), (30, 30, 30))) == 0
    b = a.copy()
    b.paste((200, 200, 200), (0, 0, 200, 400))
    assert corpus.drift(a, b) == pytest.approx(0.5)


def test_import_moves_downloads_and_keeps_broken_ones(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    (inbox / "a.json").write_text(json.dumps({"url": "https://x.org/", "host": "x.org", "html": "<p>", "viewport": [800, 600], "scheme": "dark", "stats": {},
                                              "shot": "data:image/png;base64,iVBORw0KGgo=", "recorded": "t"}))
    (inbox / "bad.json").write_text("{")
    got = corpus.import_inbox(inbox, tmp_path / "store")
    assert len(got) == 1 and not (inbox / "a.json").exists() and (inbox / "bad.json").exists()
    assert (tmp_path / "store" / got[0] / "page.html").read_text() == "<p>"
    assert corpus.captures("", tmp_path / "store")[0]["id"] == got[0]


def test_save_writes_asset_table_with_types(tmp_path):
    cid = corpus.save({"url": "https://x.org/", "host": "x.org", "html": "", "viewport": [1, 1], "scheme": "dark", "stats": {},
                       "assets": {"a0": "data:image/png;base64,aGk=", "a1": "data:text/css,p%7B%7D"}}, "t", tmp_path)
    assert (tmp_path / cid / "assets/a0").read_bytes() == b"hi" and (tmp_path / cid / "assets/a1").read_bytes() == b"p{}"
    assert json.loads((tmp_path / cid / "assets.json").read_text()) == {"a0": "image/png", "a1": "text/css"}


def test_daily_recorder_build_has_no_page_trigger(tmp_path):
    with zipfile.ZipFile(corpus.recorder_xpi(tmp_path / "r.xpi")) as z:
        assert "lab-hook.js" not in z.namelist() and "content_scripts" not in json.loads(z.read("manifest.json"))


def test_http_build_opens_https_only_patterns(xpi, tmp_path):  # noqa: F811
    with zipfile.ZipFile(corpus.http_xpi(xpi, tmp_path / "x.xpi")) as z:
        scripts = json.loads(z.read("data/ContentScripts.json"))["supportedWebsites"]
    assert not any("https://" in m for s in scripts for m in s["matches"])


@pytest.mark.e2e
def test_freeze_then_replay_keeps_the_live_state(xpi, fixture_url, tmp_path):  # noqa: F811
    hook = corpus.recorder_xpi(tmp_path / "hook.xpi", hook=True)
    store = tmp_path / "store"

    async def frozen():
        async with lab.session(xpi, tmp_path / "a.log", also=[(corpus.RECORDER_ID, hook)]) as pg:
            await pg.goto(fixture_url("freeze.html"), settle=2)
            return await corpus.freeze(pg)
    f = asyncio.run(frozen())
    html = f["html"]
    assert "<script src" not in html and "ranScript" not in html and "onclick" not in html
    assert "hunter2" not in html and "typed text" in html
    assert "tz-initialized" not in html and "data-tz-" not in html and "--tz-glass-alpha" not in html
    assert f["stats"]["closedShadows"] == 1 and f["stats"]["canvases"] == 1
    cid = corpus.save(f, "test", store)
    meta = corpus.captures("", store)[0]

    probe = """JSON.stringify({ran: !!window.ranScript, ready: document.documentElement.dataset.glReady,
      injected: getComputedStyle(document.getElementById('injected')).color,
      adopted: getComputedStyle(document.getElementById('adopted')).color,
      shadow: getComputedStyle(document.getElementById('shadow-open').shadowRoot.getElementById('inside')).color,
      closed: !!document.getElementById('shadow-closed').shadowRoot?.getElementById('inclosed'),
      field: document.getElementById('field').value, tick: document.getElementById('tick').checked,
      modal: document.getElementById('modal').matches(':modal'), pop: document.getElementById('pop').matches(':popover-open'),
      scroll: document.getElementById('scroller').scrollTop,
      frame: !!document.getElementById('same').contentDocument?.getElementById('inframe')})"""

    async def replayed():
        with corpus.Server() as server:
            async with lab.session(None, tmp_path / "b.log", extra_prefs=server.prefs) as pg:
                await corpus.show(pg, meta, store)
                return json.loads(await pg.eval(probe))
    assert cid and asyncio.run(replayed()) == {
        "ran": False, "ready": "1", "injected": "rgb(1, 2, 3)", "adopted": "rgb(4, 5, 6)", "shadow": "rgb(7, 8, 9)", "closed": True,
        "field": "typed text", "tick": True, "modal": True, "pop": True, "scroll": 40, "frame": True}


@pytest.mark.e2e
def test_record_saves_a_download_that_imports_and_hotkeys_register(fixture_url, tmp_path):
    """background save path + the registered shortcuts. BiDi keys never reach browser-level commands, so the keypress itself is untested here"""
    hook = corpus.recorder_xpi(tmp_path / "hook.xpi", hook=True)
    downloads = lab.LAB / "dl"
    prefs = {"browser.download.folderList": 2, "browser.download.dir": str(downloads), "browser.download.useDownloadDir": True}

    async def go():
        async with lab.session(None, tmp_path / "c.log", extra_prefs=prefs, also=[(corpus.RECORDER_ID, hook)]) as pg:
            pg.ctx = (await pg.b.call("browsingContext.create", type="tab"))["context"]  # the lab's first context isn't a tab to tabs.query
            await pg.goto(fixture_url("freeze.html"), settle=2)
            await pg.eval("document.dispatchEvent(new CustomEvent('gl-commands'))")
            await asyncio.sleep(1)
            cmds = json.loads(await pg.eval("window.__glCommands"))
            await pg.eval("document.dispatchEvent(new CustomEvent('gl-record'))")
            for _ in range(40):
                if files := list((downloads / "glass-corpus").glob("*.json")):
                    await asyncio.sleep(1)  # let the write finish
                    return cmds, corpus.import_inbox(files[0].parent, tmp_path / "store")
                await asyncio.sleep(0.5)
            return cmds, []
    cmds, got = asyncio.run(go())
    assert {c["name"]: c["shortcut"] for c in cmds} == {"record": "Alt+Shift+R", "record-delayed": "Alt+Shift+D"}
    assert len(got) == 1
    meta = corpus.captures("", tmp_path / "store")[0]
    assert meta["source"] == "recorder" and meta["title"] == "freeze fixture" and meta["viewport"]
    assert (tmp_path / "store" / got[0] / "shot.png").stat().st_size > 1000
    assert "typed text" in (tmp_path / "store" / got[0] / "page.html").read_text()
