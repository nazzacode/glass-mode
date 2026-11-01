"""replay: cache2 entry parsing, frozen page rewrite; wall gate: a bot check is never a pass."""
import gzip, struct

from tools.glasslab import replay
from tools.glasslab.metrics import is_wall


def entry(body, url="https://www.example.org/a", head=b"content-type: text/html\r\ncontent-encoding: gzip\r\n"):
    meta = b"\x00" * 8 + b"O^partitionKey=%28https%2Cexample.org%29,:" + url.encode() + b"\x00" + head
    return body + meta + struct.pack(">I", len(body))


def test_parse_entry_decodes_body_and_reads_key():
    e = replay.parse_entry(entry(gzip.compress(b"<p>hi</p>")))
    assert (e["url"], e["type"], e["body"]) == ("https://www.example.org/a", "text/html", b"<p>hi</p>")


def test_parse_entry_drops_partial_download():
    assert replay.parse_entry(entry(b"not gzip")) is None


def test_page_strips_scripts_and_tls_links():
    html = b'<a href="https://x.org/b">b</a><script src="a.js"></script><SCRIPT>1</SCRIPT><p>t</p>'
    assert replay.page(html, "x.org") == b'<a href="http://x.org/b">b</a><p>t</p>'


def test_capture_keeps_newest_and_only_host(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "STORE", tmp_path / "store")
    d = tmp_path / "entries"
    d.mkdir()
    import os
    for i, (body, url) in enumerate([(b"old", "https://x.org/"), (b"new", "https://x.org/"), (b"no", "https://y.org/x.org")]):
        f = d / str(i)
        f.write_bytes(entry(gzip.compress(body), url))
        os.utime(f, (i, i))
    assert replay.capture("x.org", d) == ["https://x.org/"]
    assert replay.lookup(tmp_path / "store/x.org", "http://x.org/")[0] == b"new"


def test_pac_routes_only_replayed_hosts():
    p = replay.pac_prefs(["x.org"], 1234)
    assert 'h == "x.org"' in p["network.proxy.autoconfig_url"] and "DIRECT" in p["network.proxy.autoconfig_url"]


def test_walls():
    assert is_wall("Just a moment...") and is_wall("Attention Required! | Cloudflare") and is_wall("Anything", True)
    assert is_wall("claude.ai", False, "claude.ai\nPerforming security verification\nThis website uses")
    assert not is_wall("serendipity synonyms - Power Thesaurus") and not is_wall(None)
