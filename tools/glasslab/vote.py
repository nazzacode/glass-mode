"""A vs B: Nathan's taste decides what the numbers can't. `./glasslab vote build` renders frozen corpus pages (corpus.py) under each
question's variants over his real wallpapers; `./glasslab vote` serves them on localhost, blind, one click per vote;
`./glasslab vote results` ranks. Local only: renders show private pages. Votes: ~/.cache/glasslab/vote/votes.jsonl"""
import asyncio, http.server, itertools, json, math, random, re, time
from pathlib import Path

from PIL import Image

from . import corpus, lab
from .metrics import composite
from .suite import AUTO, DEFAULT_ALPHA, load_screens

HERE = Path(__file__).parent
ROOT = Path.home() / ".cache/glasslab/vote"
WALLS = Path.home() / ".cache/glasslab/vote-walls"
PORT = 8765
MAX_PER_HOST = 4
MAX_DRIFT = 0.10   # worse than this against the live page: not the page Nathan would see, don't ask about it
WIDTH = 1400


def questions():
    return json.loads((HERE / "questions.json").read_text())["questions"]


def walls():
    """darkest, median, brightest of Nathan's wallpapers (blurred like the compositor): `glasslab wallpapers` into WALLS"""
    meta = json.loads((WALLS / "bounds.json").read_text())
    ws = sorted(meta["wallpapers"], key=lambda w: w["median"])
    picks = {"dark": ws[0], "mid": ws[len(ws) // 2], "bright": ws[-1]}
    return {k: Image.open(WALLS / f"{w['name']}.png") for k, w in picks.items()}


def eligible(metas, only, max_per_host=MAX_PER_HOST):
    """captures a question can ask about: pages = base views, panels = open hidden UI + anything Nathan recorded. Broken freezes out"""
    fits = {"pages": lambda m: not m.get("state"), "panels": lambda m: bool(m.get("state")) or m["source"] == "recorder"}[only]
    good = [m for m in metas if fits(m) and m.get("drift", 0) <= MAX_DRIFT]
    good.sort(key=lambda m: (m["source"] != "recorder", m["host"], m["id"]))  # real use first
    return [m for _, ms in itertools.groupby(good, key=lambda m: m["host"]) for m in itertools.islice(ms, max_per_host)]


def pair_key(v):
    return (v["q"], v["capture"], v["mode"], v["wall"], *sorted((v["left"], v["right"])))


def next_pair(pairs, votes, rng=random):
    """fewest votes first, earliest question first, random within: every page gets asked before any is asked twice. Sides shuffled"""
    seen = {}
    for v in votes:
        seen[pair_key(v)] = seen.get(pair_key(v), 0) + 1
    if not pairs:
        return None
    least = min(seen.get(pair_key(p), 0) for p in pairs)
    fresh = [p for p in pairs if seen.get(pair_key(p), 0) == least]
    first_q = fresh[0]["q"]
    p = rng.choice([x for x in fresh if x["q"] == first_q])
    return {**p, "left": p["right"], "right": p["left"]} if rng.random() < 0.5 else dict(p)


def wilson(wins, n, z=1.96):
    """lower bound of the true win rate: 3/3 must not outrank 40/50"""
    if not n:
        return 0.0
    p = wins / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def standings(votes, by=None):
    """{question: {group: [{variant, wins, losses, same, bad, low}]}} ranked by lower bound. by = a vote field ('wall', 'mode') or None"""
    tally = {}
    for v in votes:
        for side in (v["left"], v["right"]):
            t = tally.setdefault(v["q"], {}).setdefault(v.get(by) if by else "all", {}).setdefault(side, dict.fromkeys(("wins", "losses", "same", "bad"), 0))
            pick = v["pick"]
            t["wins" if pick == side else "same" if pick == "same" else "bad" if pick == "bad" else "losses"] += 1
    return {q: {g: sorted(({"variant": k, **t, "low": round(wilson(t["wins"] + t["same"] / 2, t["wins"] + t["losses"] + t["same"]), 3)} for k, t in vs.items()),
                          key=lambda r: -r["low"]) for g, vs in gs.items()} for q, gs in tally.items()}


def read_votes(path=None):
    path = Path(path or ROOT / "votes.jsonl")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def undo_last(path=None):
    path = Path(path or ROOT / "votes.jsonl")
    lines = path.read_text().splitlines() if path.exists() else []
    path.write_text("".join(f"{x}\n" for x in lines[:-1]))


# ── build ───────────────────────────────────────────────────────────────────────────────────────────────────────────
async def set_variant(pg, css, mode):
    await pg.eval(f"""(() => {{ let s = document.getElementById('gl-variant'); if (!s) {{ s = document.createElement('style'); s.id = 'gl-variant'; document.head.append(s); }}
                      s.textContent = {json.dumps(css)}; }})()""")
    await pg.glass(mode, DEFAULT_ALPHA)


async def render(pg, m, q, mode, backs, out):
    """one capture × mode: every variant over every wall → webp + pairs; a variant that changes nothing isn't a question"""
    frames = {}
    for name, css in q["variants"].items():
        await set_variant(pg, css, mode)
        frames[name] = (await pg.shot("#000"), await pg.shot("#fff"))
        await pg.clear_backdrop()
    ref = next(iter(frames))
    if all(corpus.drift(frames[ref][0], f[0], 2) < 0.005 for f in frames.values()):
        print(f"  {m['id']} {mode}: variants identical on this page, skipped", flush=True)
        return []
    pairs = []
    for wall, back in backs.items():
        for name, (black, white) in frames.items():
            img = composite(black, white, back)
            img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS).save(out / f"{q['id']}.{m['id']}.{mode}.{wall}.{name}.webp", quality=88)
        pairs += [{"q": q["id"], "ask": q["ask"], "capture": m["id"], "host": m["host"], "state": m.get("state", ""), "mode": mode, "wall": wall, "left": a, "right": b}
                  for a, b in itertools.combinations(frames, 2)]
    return pairs


async def build_session(xpi, metas_by_q, scheme, backs, out, log):
    autos = {s["id"] for s in load_screens() if s.get("auto")}
    pairs = []
    with corpus.Server() as server:
        async with lab.session(xpi, log, scheme=scheme, extra_prefs=server.prefs) as pg:
            for q, metas in metas_by_q:
                for m in metas:
                    await corpus.show(pg, m)
                    if m.get("screen") in autos:
                        await pg.eval(AUTO)
                        await asyncio.sleep(1.5)
                    for mode in q["modes"]:
                        print(f"· {q['id']} {m['id']} {mode}", flush=True)
                        pairs += await render(pg, m, q, mode, backs, out)
    return pairs


def build(xpi, filt=""):
    out = ROOT / "renders"
    out.mkdir(parents=True, exist_ok=True)
    patched = corpus.http_xpi(xpi, ROOT / "glass-http.xpi")
    backs, metas, pairs = walls(), corpus.captures(filt), []
    for scheme in dict.fromkeys(m["scheme"] for m in metas):
        chosen = [(q, eligible([m for m in metas if m["scheme"] == scheme], q["only"])) for q in questions()]
        pairs += asyncio.run(build_session(patched, chosen, scheme, backs, out, ROOT / "build.log"))
    (ROOT / "pairs.json").write_text(json.dumps(pairs))
    return pairs


# ── serve ───────────────────────────────────────────────────────────────────────────────────────────────────────────
PAGE = (HERE / "vote.html")


class Handler(http.server.BaseHTTPRequestHandler):
    def reply(self, body, kind="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if kind != "image/webp" else "max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self.reply(PAGE.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/next":
            votes = read_votes()
            pairs = json.loads((ROOT / "pairs.json").read_text())
            return self.reply(json.dumps({"pair": next_pair(pairs, votes), "done": len(votes), "total": len(pairs)}).encode())
        if self.path == "/results":
            return self.reply(json.dumps(results()).encode())
        name = self.path.removeprefix("/r/")
        f = ROOT / "renders" / name
        if self.path.startswith("/r/") and re.fullmatch(r"[\w.\-]+\.webp", name) and f.exists():
            return self.reply(f.read_bytes(), "image/webp")
        return self.reply(b"{}", code=404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/undo":
            undo_last()
        elif self.path == "/vote":
            with (ROOT / "votes.jsonl").open("a") as f:
                f.write(json.dumps({**body, "t": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        self.reply(b"{}")

    def log_message(self, *a):
        pass


def results(votes=None):
    votes = read_votes() if votes is None else votes
    return {"votes": len(votes), "overall": standings(votes), "by_wall": standings(votes, "wall"), "by_mode": standings(votes, "mode"),
            "bad": [{k: v.get(k) for k in ("q", "capture", "host", "state", "mode", "wall", "note")} for v in votes if v["pick"] == "bad"]}


def serve(port=PORT):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)  # never beyond this machine: the renders show private pages
    print(f"vote: http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()
