"""glasslab crawl: the whole app, not the home page. From a start URL, follow the app's own navigation (logged in, read-only
GET links, DANGER-filtered), one page per URL shape (/issue/GEN-12 and /issue/GEN-99 = one page), breadth first. Every
page: the screen checks at the default slider (unity, text, glass) + explore (every safe trigger's layer: blurred or
solid, no veil). Rows have the suite's shape → same summary + failure list. See docs/NORTH-STAR.md."""
import asyncio, json, re, time
from pathlib import Path
from urllib.parse import urlsplit

from . import explore, lab, suite

ID = re.compile(r"^(\d+|[0-9a-f]{8,}|[0-9a-f-]{20,}|[A-Z][A-Z0-9]*-\d+|[A-Za-z0-9_-]{20,})$")
# slugs ending in a hash (Linear: all-issues-f3aeb9154661, glass-mode-2b1f0a9c7e3d) are ids: one shape for all views / projects
SLUG_ID = re.compile(r"-[0-9a-f]{8,}$")


def shape(url):
    """URL → its page shape: id-like path segments become ':id', query dropped (filters, cursors)"""
    p, segs = urlsplit(url), []
    for s in (s for s in p.path.split("/") if s):
        if segs and segs[-1] == ":id" and "-" in s and not ID.match(s):  # title slug after an id (/issue/GEN-12/fix-the-thing); tabs (/overview) stay
            continue
        segs.append(":id" if ID.match(s) or SLUG_ID.search(s) else s)
    return f"{p.netloc}/{'/'.join(segs)}"



def page_id(name, url):
    s = shape(url).split("/", 1)[-1] or "home"
    return f"{name}@{re.sub(r'[^a-z0-9:]+', '-', s.lower()).strip('-').replace(':id', 'id')[:48] or 'home'}"


async def crawl_session(xpi, out, name, start, limit, depth, bounds, scheme, do_explore, settle):
    results, visited = [], []
    async with lab.session(xpi, out / f"zen-{scheme}.log", scheme=scheme) as pg:
        frontier, seen = [(start, 0)], {shape(start)}
        while frontier and len(visited) < limit:
            url, d = frontier.pop(0)
            sc = {"id": page_id(name, url), "url": url, "settle": settle}
            print(f"· {sc['id']}  {url}", flush=True)
            await pg.open(sc)
            if (here := await pg.eval("location.href")) and shape(here) != shape(url) and shape(here) in seen and d:
                print("  ↳ redirected to a page already covered, skipped", flush=True)
                continue
            visited.append(url)
            if d < depth:
                for l in await pg.probe("links", explore.DANGER, 80) or []:
                    if (s := shape(l["href"])) not in seen:
                        seen.add(s)
                        frontier.append((l["href"], d + 1))
            rows = await suite.measure_screen(pg, sc, out, bounds, alphas=[suite.DEFAULT_ALPHA])
            results += rows
            if do_explore and not rows[0]["wall"]:
                states = await explore.explore(pg, bounds, sc["id"], suite.MODES, suite.DEFAULT_ALPHA, out / "raw", settle=settle)
                results += suite.state_rows(states, sc["id"], suite.DEFAULT_ALPHA)
    return results, visited


def foreign_md(results):
    """the leftover-slab list: which foreign surfaces appear on how many pages/states → what to style next"""
    tally = {}
    for r in results:
        for k, n in r.get("surface_foreign", []):
            t = tally.setdefault(k, [0, set()])
            t[0] += n
            t[1].add(r["key"].split(".")[0])
    lines = ["| foreign surface | hits | pages / states |", "|---|---|---|"]
    for k, (n, where) in sorted(tally.items(), key=lambda x: -x[1][0])[:40]:
        lines.append(f"| `{k}` | {n} | {', '.join(sorted(where)[:6])}{' …' if len(where) > 6 else ''} |")
    return "\n".join(lines) + "\n"


def main(xpi, name, url, limit=15, depth=2, scheme="dark", do_explore=True, settle=7, out=None):
    out = Path(out or Path.home() / ".cache/glasslab/runs" / f"crawl-{name}-{time.strftime('%Y%m%d-%H%M%S')}")
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "shots").mkdir(exist_ok=True)
    bounds, _ = suite.backdrops()
    results, visited = asyncio.run(crawl_session(xpi, out, name, url, limit, depth, bounds, scheme, do_explore, settle))
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "summary.md").write_text(f"pages ({len(visited)}):\n" + "".join(f"- {u}\n" for u in visited) + "\n"
                                    + suite.summary_md(results) + "\n## leftover surfaces\n\n" + foreign_md(results))
    fails = [r["key"] for r in results if not r["ok"]]
    print(f"\ncrawl: {len(visited)} pages, {len(results)} rows, {len(fails)} failing\nrun: {out}\nfails: {fails or 'none'}")
    return 1 if fails else 0
