"""replay: real pages from the user's own Zen HTTP cache, served to the lab with no request to the site. For sites whose
bot checks stop a headless browser. `./glasslab replay HOST` captures into ~/.cache/glasslab/replay/<host> (local: may hold
private page text, never commit). A screen with `"replay": "<host>"` then loads over a PAC-routed local proxy; other
hosts stay direct. Scripts are stripped: the frozen server render, so measures surfaces, not hidden UI."""
import contextlib, gzip, http.server, json, re, struct, threading, zlib
from pathlib import Path
from urllib.parse import urlsplit

from . import lab

STORE = Path.home() / ".cache/glasslab/replay"
HEAD = re.compile(rb"content-(type|encoding): *([^\r\n\x00]+)", re.I)
SCRIPT = re.compile(r"<script\b.*?</script>", re.I | re.S)


def decode(body, encoding):
    if encoding == "gzip":
        return gzip.decompress(body)
    if encoding == "deflate":
        return zlib.decompress(body)
    if encoding == "br":
        import brotli
        return brotli.decompress(body)
    return body


def parse_entry(raw):
    """one cache2 entry (body, metadata, big-endian u32 metadata offset) → {url, type, body}; None if unusable"""
    off = struct.unpack(">I", raw[-4:])[0]
    meta = raw[off:]
    url = re.search(rb"https?://[^\x00\s]+", meta)
    if not url:
        return None
    head = {k.decode().lower(): v.decode("latin1").strip() for k, v in HEAD.findall(meta)}
    try:
        body = decode(raw[:off], head.get("encoding", "").lower())
    except Exception:  # partial entry: never fully downloaded
        return None
    return {"url": url.group(0).decode("latin1"), "type": head.get("type", ""), "body": body}


def cache_dir():
    profile = lab.live_profile()
    return lab.SANDBOX / "cache/zen" / profile.name / "cache2/entries"


def capture(host, entries=None):
    """newest cached copy of every URL on host → store; returns the page URLs captured"""
    entries = Path(entries or cache_dir())
    out = STORE / host
    (out / "files").mkdir(parents=True, exist_ok=True)
    index = {}
    needle = host.encode()
    for f in sorted(entries.iterdir(), key=lambda p: p.stat().st_mtime):  # oldest first: newer overwrites
        raw = f.read_bytes()
        if needle not in raw or len(raw) < 4:
            continue
        e = parse_entry(raw)
        if not e or urlsplit(e["url"]).hostname != host or not e["body"]:
            continue
        name = f"{len(index):04d}" if e["url"] not in index else index[e["url"]]["file"]
        (out / "files" / name).write_bytes(e["body"])
        index[e["url"]] = {"file": name, "type": e["type"]}
    (out / "index.json").write_text(json.dumps(index, indent=0))
    return [u for u, i in index.items() if i["type"].startswith("text/html")]


def page(body, host):
    """frozen render: no scripts, same-host links over plain http (the proxy can't terminate TLS)"""
    return SCRIPT.sub("", body.decode("utf-8", "replace")).replace(f"https://{host}", f"http://{host}").encode()


def lookup(store, url):
    """(body, type) of the captured url, http or https; None if it was never cached"""
    u = urlsplit(url)
    i = json.loads((store / "index.json").read_text())
    hit = i.get(f"https://{u.netloc}{u.path}" + (f"?{u.query}" if u.query else "")) or i.get(url)
    if not hit:
        return None
    body = (store / "files" / hit["file"]).read_bytes()
    return (page(body, u.netloc) if hit["type"].startswith("text/html") else body), hit["type"]


class Proxy(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        host = urlsplit(self.path).netloc
        got = lookup(STORE / host, self.path) if (STORE / host / "index.json").exists() else None
        self.send_response(200 if got else 404)
        self.send_header("Content-Type", got[1] if got else "text/plain")
        self.send_header("Content-Length", str(len(got[0]) if got else 0))
        self.end_headers()
        if got:
            self.wfile.write(got[0])

    def log_message(self, *a):
        pass


def pac_prefs(hosts, port):
    """route only the replayed hosts through the proxy; nothing else in the session changes"""
    cond = " || ".join(f'h == "{h}"' for h in hosts)
    pac = f'function FindProxyForURL(u, h) {{ return ({cond}) ? "PROXY 127.0.0.1:{port}" : "DIRECT"; }}'
    return {"network.proxy.type": 2, "network.proxy.autoconfig_url": f"data:text/plain,{pac}", "dom.security.https_only_mode": False}


@contextlib.contextmanager
def serving(hosts):
    """yields the prefs for lab.session; {} when no screen replays"""
    if not hosts:
        yield {}
        return
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield pac_prefs(sorted(hosts), srv.server_address[1])
    finally:
        srv.shutdown()
