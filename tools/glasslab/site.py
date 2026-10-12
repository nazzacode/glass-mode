"""glasslab site: the public project page (GitHub Pages) + README supported-sites table. Static, stdlib only.

Inputs: registry (data/ContentScripts.json), screens.json, numbers (baseline.json, or a run's results.json → numbers
only, never page text), beauty shots site/shots/<screen>.<mode>.webp (`glasslab shots`), test tiles site/tests/
(index.json from `glasslab shots --all`). Output: site/index.html (style: site/style.css, hand-written) + the README
table between START/END markers.

Privacy: tiles come ONLY from site/tests/index.json; a private screen's tile needs `scrambled: true` (set by shots after
the scrambler ran) and never shows a state label other than `hidden UI n`. Raw captures are never referenced."""
import html, json, re
from pathlib import Path
from urllib.parse import urlencode, urlparse

from .shots import ref
from .suite import DEFAULT_ALPHA, MODES, load_screens

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
SITE = ROOT / "site"
START, END = "<!-- sites:start -->", "<!-- sites:end -->"
STATUS_ORDER = ["verified", "pending", "untested", "auto"]
STATUS = {"verified": "verified glass", "pending": "tests pending", "untested": "upstream style, not yet tested",
          "auto": "auto glass benchmark"}
UPSTREAM = "https://github.com/frostybiscuit/transparent-zen"
A = int(DEFAULT_ALPHA * 100)
esc = lambda s: html.escape(str(s), quote=True)


# ── sources ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def glass_ts():
    return (ROOT / "src/shared/Glass.ts").read_text()


def repo(src=None):
    """REPO constant from src/shared/Glass.ts: one source for issues/releases links"""
    return re.search(r'REPO\s*=\s*"([^"]+)"', src if src is not None else glass_ts()).group(1)


def opacity(src=None):
    m = re.search(r"OPACITY\s*=\s*\{([^}]*)\}", src if src is not None else glass_ts())
    return {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", m.group(1))}


def registry():
    return json.loads((ROOT / "data/ContentScripts.json").read_text())["supportedWebsites"]


def numbers_from_results(results):
    """run rows → numbers only: contrast (worst bound), surface, text, ok, glass share or layer opacity. No page text."""
    keep = ("glass", "opacity")
    return {r["key"]: {"contrast": min(r["contrast"]), "surface": r["surface"], "text": r["text"], "ok": r["ok"],
                       **{k: r[k] for k in keep if k in r}} for r in results}


def load_numbers(run=None):
    if run:
        return numbers_from_results(json.loads((Path(run) / "results.json").read_text()))
    bl = HERE / "baseline.json"
    return json.loads(bl.read_text()) if bl.exists() else {}


# ── model ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def parse_key(key):
    """'<screen>[~<state>].<mode>.<α>' → (screen, state|None, mode, α)"""
    head, mode, a = key.rsplit(".", 2)
    screen, _, state = head.partition("~")
    return screen, state or None, mode, int(a)


def site_for(url, reg):
    """first registry entry whose (unanchored) match hits, like the extension"""
    return next((r for r in reg if any(re.search(m, url) for m in r["matches"])), None)


def host(url):
    h = urlparse(url).hostname or ""
    return h[4:] if h.startswith("www.") else h


def host_of_entry(r):
    """best-effort host from the registry match patterns (for entries without a test screen)"""
    cands = [c.replace("\\", "") for m in r["matches"] for c in re.findall(r"[a-z0-9-]+(?:\\?\.[a-z0-9-]+)+", m)]
    h = max(cands, key=len, default="")
    return h[4:] if h.startswith("www.") else h


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "site"


def pass_rates(keys, numbers):
    """{mode: (ok, n)} over result keys at the default slider"""
    out = {}
    for k in keys:
        mode = parse_key(k)[2]
        ok, n = out.get(mode, (0, 0))
        out[mode] = (ok + bool(numbers[k]["ok"]), n + 1)
    return {m: out[m] for m in MODES if m in out}


def build_sites(reg, screens, numbers):
    """sites database rows: registry entries (verified / untested) + screens without a style (auto / pending)"""
    at_default = [k for k in numbers if parse_key(k)[3] == A]
    rows = {}
    for r in reg:
        rows[r["name"]] = {"name": r["name"], "host": host_of_entry(r), "status": "untested", "screens": [],
                           "favicon": r.get("favicon"), "forced": r.get("glass")}
    for sc in screens:
        r = None if sc.get("auto") else site_for(sc["url"], reg)
        name = r["name"] if r else host(sc["url"])
        row = rows.setdefault(name, {"name": name, "host": host(sc["url"]), "status": "auto" if sc.get("auto") else "pending",
                                     "screens": [], "favicon": None, "forced": None})
        if r and not row["screens"]:
            row["host"] = host(sc["url"])                            # first screen names the host
        row["screens"].append(sc["id"])
    for row in rows.values():
        mine = [k for k in at_default if parse_key(k)[0] in row["screens"]]
        if row["status"] == "untested" and row["screens"]:
            row["status"] = "verified" if mine else "pending"       # styled + tested vs styled, results pending
        row["states"] = len({parse_key(k)[:2] for k in mine if parse_key(k)[1]})
        row["pass"] = pass_rates(mine, numbers)
        row["id"] = slug(row["name"])
    return sorted(rows.values(), key=lambda r: (STATUS_ORDER.index(r["status"]), r["name"].lower()))


def load_tiles(tiles_dir, screens, numbers):
    """index.json rows that are safe to publish (file exists, known screen, private ⇒ scrambled), with their numbers"""
    idx = Path(tiles_dir) / "index.json"
    if not idx.exists():
        return []
    by_id = {s["id"]: s for s in screens}
    refs = {}
    for k in numbers:
        scr, st, mode, a = parse_key(k)
        if st:
            refs[f"{ref(f'{scr}~{st}')}.{mode}.{a}"] = k
    out = []
    for e in json.loads(idx.read_text())["tiles"]:
        sc = by_id.get(e["screen"])
        if not sc or not (Path(tiles_dir) / e["file"]).is_file():
            continue
        if sc.get("private") and e.get("scrambled") is not True:
            continue
        state = e.get("state")
        if sc.get("private") and state is not None and not re.fullmatch(r"hidden UI \d+", state):
            state = "hidden UI"
        key = e.get("key") or refs.get(e.get("ref"))
        out.append({**e, "state": state, "n": numbers.get(key) if key else None})
    return out


def load_shots(shots_dir, screens):
    """beauty shots per screen (screens.json order): {screen, dark, light} file names (None when missing)"""
    d = Path(shots_dir)
    rows = [{"screen": s["id"], **{m: (f"{s['id']}.{m}.webp" if (d / f"{s['id']}.{m}.webp").is_file() else None) for m in MODES}}
            for s in screens]
    return [r for r in rows if r["dark"] or r["light"]]


def issue_url(kind, site_host=None, repo=None):
    """prefilled GitHub issue form (.github/ISSUE_TEMPLATE/<kind>.yml; field ids = query params), like Glass.ts issueUrl"""
    q = {"template": f"{kind}.yml"}
    if kind == "site-bug":
        q.update(site=site_host, url=f"https://{site_host}/", title=f"[{site_host}] ")
    else:
        q.update(title="Add ")
    return f"https://github.com/{repo}/issues/new?{urlencode(q)}"


def context(reg, screens, numbers, tiles, shots_, repo):
    sites = build_sites(reg, screens, numbers)
    return {"sites": sites, "screens": screens, "tiles": tiles, "shots": shots_, "repo": repo, "opacity": opacity(),
            "names": {sc: s["name"] for s in sites for sc in s["screens"]}}


# ── README table ─────────────────────────────────────────────────────────────────────────────────────────────────────
def frac(p):
    return f"{p[0]}/{p[1]}" if p else "—"


def readme_table(sites, repo):
    md = lambda s: str(s).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
    lines = [f"Generated by `./glasslab site` from the test baseline (default opacity {A} %). "
             f"[Request a site]({issue_url('site-request', repo=repo)}) · tested screens: see the project page.", "",
             "| Site | Status | Screens tested | Hidden UI tested | Pass dark | Pass light |", "|---|---|---|---|---|---|"]
    for s in sites:
        lines.append(f"| {md(s['name'])} | {STATUS[s['status']]} | {len(s['screens']) or '—'} | {s['states'] or '—'} | "
                     f"{frac(s['pass'].get('dark'))} | {frac(s['pass'].get('light'))} |")
    return "\n".join(lines) + "\n"


def replace_block(text, block):
    """swap what's between the markers (idempotent); no markers → text unchanged"""
    i, j = text.find(START), text.find(END)
    if i < 0 or j < i:
        return text
    return text[:i + len(START)] + "\n" + block.strip() + "\n" + text[j:]


def update_readme(raw, block):
    """replace_block on raw README text, keeping its line endings (the README is CRLF)"""
    crlf = "\r\n" in raw
    new = replace_block(raw.replace("\r\n", "\n"), block)
    return new.replace("\n", "\r\n") if crlf else new


# ── page ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def view_name(screen, names):
    """'gmail-inbox' → ('Gmail', 'inbox')"""
    return names.get(screen, screen), screen.split("-", 1)[1].replace("-", " ") if "-" in screen else screen


def pct(v):
    return f"{round(v * 100)}%"


def mark(ok):
    return '<span class="ok">pass</span>' if ok else '<span class="bad">fail</span>'


def gh(repo, path=""):
    return f"https://github.com/{repo}{path}"


def picture(shot, alt, cls=""):
    """dark + light pair → <picture> following the OS scheme"""
    d, l = shot["dark"], shot["light"]
    src = d or l
    alt_ = f' alt="{esc(alt)}"'
    if d and l:
        return (f'<picture class="{cls}"><source srcset="shots/{esc(l)}" media="(prefers-color-scheme: light)">'
                f'<img src="shots/{esc(d)}"{alt_} width="1280" height="800" decoding="async"></picture>')
    return f'<picture class="{cls}"><img src="shots/{esc(src)}"{alt_} width="1280" height="800" decoding="async"></picture>'


def hero(c):
    shot = next((s for s in c["shots"] if s["dark"] and s["light"]), c["shots"][0] if c["shots"] else None)
    pic = picture(shot, "{} {} as liquid glass over a blurred wallpaper".format(*view_name(shot["screen"], c["names"])), "hero-shot") if shot else ""
    verified = sum(s["status"] == "verified" for s in c["sites"])
    return f"""<section class="hero wrap-wide">
  <h1>Websites, as glass.</h1>
  <p class="lede">A Zen Browser extension that turns the sites you live in (mail, calendar, chat, music) into translucent
  glass over your blurred desktop. One design system for every site, and a test lab that keeps every screen readable on any wallpaper.</p>
  <p class="cta"><a class="btn" href="#install">Install</a> <a class="btn quiet" href="{gh(c['repo'])}">Source on GitHub</a>
  <span class="meta">Free · MIT · {verified} verified sites</span></p>
</section>
<figure class="hero-fig wrap-wide">{pic}</figure>"""


def gallery(c):
    figs = []
    for s in c["shots"]:
        site_name, view = view_name(s["screen"], c["names"])
        imgs = "".join(f'<img class="{m[0]}" src="shots/{esc(s[m])}" alt="{esc(site_name)} {esc(view)}, {m} glass" '
                       f'loading="lazy" decoding="async" width="1280" height="800">' for m in MODES if s[m])
        only = "" if s["dark"] and s["light"] else f' data-only="{"dark" if s["dark"] else "light"}"'
        figs.append(f'<figure class="shot"{only}><div class="frame">{imgs}</div><figcaption><b>{esc(site_name)}</b> {esc(view)}</figcaption></figure>')
    return f"""<section id="gallery" class="wrap-wide">
  <input type="radio" name="gm" id="gm-dark" class="sr"><input type="radio" name="gm" id="gm-light" class="sr">
  <div class="head"><h2>Gallery</h2>
    <div class="seg" role="group" aria-label="Glass mode"><label for="gm-dark">Dark</label><label for="gm-light">Light</label></div></div>
  <p class="note wrap-in">Real captures through the extension, composited onto our own wallpapers. Personal apps are shot with every word and photo scrambled.</p>
  <div class="grid">{''.join(figs)}</div>
</section>"""


def install(c):
    rel = gh(c["repo"], "/releases/latest")
    return f"""<section id="install">
  <h2>Install</h2>
  <ol class="steps">
    <li><h3>Let Zen be transparent</h3>
      <p>In <a href="https://zen-browser.app">Zen Browser</a> open <code>about:config</code> and set to <code>true</code>:</p>
      <dl class="os"><dt>Linux</dt><dd><code>browser.tabs.allow_transparent_browser</code> · <code>zen.widget.linux.transparency</code>.
        The blur comes from your compositor: Hyprland blurs out of the box; KDE needs <a href="https://github.com/taj-ny/kwin-effects-forceblur">kwin-effects-forceblur</a>.</dd>
      <dt>Windows 11</dt><dd><code>browser.tabs.allow_transparent_browser</code> · <code>widget.transparent-windows</code> · <code>widget.windows.mica</code>.
        Optional: <a href="https://github.com/MicaForEveryone/MicaForEveryone">MicaForEveryone</a> with Acrylic for zen.</dd></dl></li>
    <li><h3>Add the extension</h3>
      <p>Download the <code>.xpi</code> from <a href="{rel}">GitHub Releases</a>, then in Zen: <code>about:addons</code> → ⚙ → <i>Install Add-on From File</i>.</p></li>
    <li><h3>Optional: web apps</h3>
      <p>Give a site its own chromeless window and launcher entry, glass straight through to the desktop (Linux):</p>
      <pre><code>./webapp/zen-webapp add "Gmail" https://mail.google.com --icon auto</code></pre></li>
  </ol>
</section>"""


def control(c):
    o = c["opacity"]
    return f"""<section id="control">
  <h2>One control</h2>
  <p>Everything follows a single variable: how much of the desktop shows through. Text, menus and panels keep their
  readability floors whatever you choose.</p>
  <dl class="keys">
    <dt>Popup slider</dt><dd>opacity {o.get('min', 10)}–{o.get('max', 90)} %, default {o.get('default', 45)} %</dd>
    <dt><kbd>Alt</kbd> <kbd>Shift</kbd> <kbd>↑</kbd> / <kbd>↓</kbd></dt><dd>more / less glass, in {o.get('step', 5)} % steps, in any window (web apps too)</dd>
    <dt><kbd>Alt</kbd> <kbd>Shift</kbd> <kbd>G</kbd></dt><dd>glass mode: auto → dark → light</dd>
  </dl>
</section>"""


def rate_cell(p):
    if not p:
        return '<span class="dim">—</span>'
    ok, n = p
    cls = "ok" if ok == n else "warn" if ok >= 0.75 * n else "bad"
    return f'<span class="{cls}">{ok}/{n}</span>'


def sites_table(c):
    has_tiles = {c["names"].get(t["screen"]) for t in c["tiles"]}
    rows = []
    upstream = [s for s in c["sites"] if s["status"] == "untested"]
    for s in (s for s in c["sites"] if s["status"] != "untested"):
        tests = f'<a href="#t-{s["id"]}">screens</a>' if s["name"] in has_tiles else ""
        report = f'<a href="{esc(issue_url("site-bug", s["host"], c["repo"]))}">report a problem</a>' if s["host"] else ""
        forced = ' <span class="tag">dark only</span>' if s.get("forced") == "dark" else ""
        rows.append(f'<tr class="st-{s["status"]}"><td data-l="Site"><b>{esc(s["name"])}</b>{"" if s["host"] == s["name"] else f" <small>{esc(s['host'])}</small>"}{forced}</td>'
                    f'<td data-l="Status"><span class="pill {s["status"]}">{STATUS[s["status"]]}</span></td>'
                    f'<td data-l="Screens" class="num">{len(s["screens"]) or "—"}</td>'
                    f'<td data-l="Hidden UI" class="num">{s["states"] or "—"}</td>'
                    f'<td data-l="Dark" class="num">{rate_cell(s["pass"].get("dark"))}</td>'
                    f'<td data-l="Light" class="num">{rate_cell(s["pass"].get("light"))}</td>'
                    f'<td data-l="" class="links">{" · ".join(x for x in (tests, report) if x)}</td></tr>')
    return f"""<section id="sites" class="wrap-mid">
  <div class="head"><h2>Sites</h2><a class="btn small" href="{esc(issue_url('site-request', repo=c['repo']))}">Request a site</a></div>
  <p>Every supported site and what the test lab checked, at the default opacity. <b>Hidden UI</b> = menus, dropdowns,
  dialogs and suggestions the explorer opened and tested. Pass = screens and states that meet every readability and
  consistency target. Sites without a style get <b>auto glass</b>; a few are measured as a benchmark.</p>
  <table class="db"><thead><tr><th>Site</th><th>Status</th><th>Screens</th><th>Hidden UI</th><th>Dark</th><th>Light</th><th></th></tr></thead>
  <tbody>{''.join(rows)}</tbody></table>
  {upstream_list(upstream, c["repo"])}
</section>"""


def upstream_list(sites, repo):
    if not sites:
        return ""
    items = " · ".join(f'<a href="{esc(issue_url("site-bug", s["host"], repo))}" title="report a problem on {esc(s["host"])}">'
                       f'{esc(s["name"])}</a>' for s in sites)
    return (f'<p class="upstream"><b>Also styled, from upstream, not yet on the glass system or tested:</b> {items}. '
            f'Click one to report a problem.</p>')


def tile_html(t, names):
    _, view = view_name(t["screen"], names)
    title = esc(t["state"]) if t["state"] else esc(view)
    sub = (esc(view) if t["state"].startswith("hidden UI") else f"{esc(view)} · hidden UI") if t["state"] else "screen"
    n = t["n"]
    if n:
        extra = (f'<span>layer α {n["opacity"]:.2f}</span>' if "opacity" in n else
                 f'<span>glass {pct(n["glass"])}</span>' if "glass" in n else "")
        nums = (f'{mark(n["ok"])}<span title="characters meeting their APCA target on the darkest and brightest wallpaper">'
                f'contrast {pct(n["contrast"])}</span><span title="surfaces that are glass tiers">surface {pct(n["surface"])}</span>{extra}')
    else:
        nums = '<span class="dim">not measured yet</span>'
    return (f'<figure class="tile"><img src="tests/{esc(t["file"])}" alt="{esc(view)} {title} ({t["mode"]})" loading="lazy" '
            f'decoding="async" width="960" height="600"><figcaption><div class="t"><b>{title}</b><span class="mode {t["mode"]}">{t["mode"]}</span></div>'
            f'<div class="sub">{sub}</div><div class="nums">{nums}</div></figcaption></figure>')


def tests(c):
    order = {s["id"]: i for i, s in enumerate(c["screens"])}
    groups = []
    all_n = [t["n"] for t in c["tiles"] if t["n"]]
    for s in c["sites"]:
        mine = sorted((t for t in c["tiles"] if t["screen"] in s["screens"]),
                      key=lambda t: (order[t["screen"]], t["state"] is not None, t["file"].rsplit(".", 2)[0], MODES.index(t["mode"])))
        if not mine:
            continue
        p = " · ".join(f"{m} {rate_cell(s['pass'][m])}" for m in MODES if m in s["pass"])
        groups.append(f'<section class="group" id="t-{s["id"]}"><div class="ghead"><h3>{esc(s["name"])}</h3>'
                      f'<span class="pill {s["status"]}">{STATUS[s["status"]]}</span><span class="rates">{p}</span>'
                      f'<a class="rep" href="{esc(issue_url("site-bug", s["host"], c["repo"]))}">report a problem</a></div>'
                      f'<div class="tiles">{"".join(tile_html(t, c["names"]) for t in mine)}</div></section>')
    ok = sum(bool(n["ok"]) for n in all_n)
    summary = (f'<p class="summary"><b>{len(c["tiles"])}</b> captures · <b>{len({t["screen"] for t in c["tiles"]})}</b> screens · '
               f'<b>{sum(t["state"] is not None for t in c["tiles"])}</b> hidden-UI states · '
               f'<b>{ok}/{len(all_n)}</b> measured captures pass</p>') if c["tiles"] else '<p class="summary dim">No test captures yet: <code>./glasslab shots --all</code>.</p>'
    return f"""<section id="tests" class="wrap-wide">
  <div class="wrap-in"><h2>Tested screens</h2>
  <p>Every screen the lab tests, and every menu or dialog it opened, at the default opacity in each mode: the exact
  capture composited onto a blurred wallpaper. Numbers: <b>contrast</b> = share of text meeting its APCA target on both the
  darkest and brightest wallpaper; <b>surface</b> = share of surfaces that are design-system glass; <b>glass</b> = share of the
  window the desktop shows through; <b>layer α</b> = how opaque a menu is (≥ 0.80 where page sits beneath it).</p>
  {summary}</div>
  {''.join(groups)}
</section>"""


DIAGRAM = """<svg class="diagram" viewBox="0 0 880 200" role="img" aria-label="Test pipeline: capture over black and white, exact alpha, composite on blurred wallpapers, score contrast and unity">
  <defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="currentColor"/></marker></defs>
  <g class="box"><rect x="4" y="22" width="120" height="66" rx="5" class="blk"/><text x="64" y="60">over black</text>
  <rect x="4" y="112" width="120" height="66" rx="5" class="wht"/><text x="64" y="150" class="ink">over white</text></g>
  <path d="M128 55 L178 92 M128 145 L178 108" class="ln" marker-end="url(#ar)"/>
  <g class="box"><rect x="184" y="70" width="140" height="60" rx="5"/><text x="254" y="96">exact colour</text><text x="254" y="114">+ alpha</text></g>
  <path d="M328 100 L372 100" class="ln" marker-end="url(#ar)"/>
  <g class="box"><rect x="378" y="70" width="160" height="60" rx="5" class="wall"/><text x="458" y="96">on blurred</text><text x="458" y="114">wallpapers</text></g>
  <path d="M542 92 L588 46 M542 100 L588 100 M542 108 L588 154" class="ln" marker-end="url(#ar)"/>
  <g class="box"><rect x="594" y="18" width="282" height="52" rx="5"/><text x="735" y="49">APCA contrast · darkest + brightest</text>
  <rect x="594" y="76" width="282" height="48" rx="5"/><text x="735" y="105">surface + text unity (glass tiers)</text>
  <rect x="594" y="130" width="282" height="52" rx="5"/><text x="735" y="161">explorer: menus, dialogs (read-only)</text></g>
</svg>"""


def how(c):
    return f"""<section id="how" class="wrap">
  <h2>How it works</h2>
  <p>Every site style maps the site's own colours onto one shared set of glass tiers: frame (sidebars, top bars),
  content panes, popovers, fills and text. Each tier has a readability floor, because a compositor blur can't adapt to
  what's behind it the way Apple's glass does.</p>
  <p>The test lab opens each screen headless, captures it over pure black
  and pure white to recover the exact colour and alpha of every pixel, composites that onto blurred wallpapers, and scores
  every text run with APCA against the darkest and brightest wallpaper. Surfaces must be design-system tiers, text must
  use the shared inks, and glass may never read worse than the site did natively. An explorer then opens menus,
  dropdowns, dialogs and search suggestions (read-only: never sends, deletes or posts) and scores each one the same way.</p>
  {DIAGRAM}
</section>"""


def add(c):
    return f"""<section id="add" class="wrap">
  <h2>Add a site in one command</h2>
  <pre><code>./glasslab add "Linear" https://linear.app/ --agent</code></pre>
  <p>Discovers what actually paints the page, scaffolds a style onto the glass tiers, then tests every screen and menu.
  With <code>--agent</code> a coding agent iterates until the tests pass. Or <a href="{esc(issue_url('site-request', repo=c['repo']))}">request a site</a>:
  a maintainer labels it and CI opens the pull request. Details in <a href="{gh(c['repo'], '/blob/release/docs/GLASS.md')}">docs/GLASS.md</a>.</p>
</section>"""


def footer(c):
    return f"""<footer class="wrap">
  <p>Built on <a href="{UPSTREAM}">Transparent Zen</a> by FrostyBiscuit. MIT licensed.
  <a href="{gh(c['repo'])}">{esc(c['repo'])}</a> · <a href="{gh(c['repo'], '/issues')}">issues</a></p>
</footer>"""


def render(c):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transparent Zen · liquid glass for Zen Browser</title>
<meta name="description" content="A Zen Browser extension that renders websites as translucent liquid glass over your blurred desktop, with every screen tested for readability.">
<meta name="color-scheme" content="dark light">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="top wrap-wide"><a class="name" href="#">Transparent Zen</a>
  <nav><a href="#gallery">Gallery</a><a href="#install">Install</a><a href="#sites">Sites</a><a href="#tests">Tests</a><a href="{gh(c['repo'])}">GitHub</a></nav></header>
<main>
{hero(c)}
{gallery(c) if c['shots'] else ''}
<div class="pair wrap">{install(c)}{control(c)}</div>
{sites_table(c)}
{tests(c)}
{how(c)}
{add(c)}
</main>
{footer(c)}
</body>
</html>
"""


def main(run=None, out=None):
    out = Path(out or SITE)
    out.mkdir(parents=True, exist_ok=True)
    reg, screens, numbers, rp = registry(), load_screens(), load_numbers(run), repo()
    c = context(reg, screens, numbers, load_tiles(out / "tests", screens, numbers), load_shots(out / "shots", screens), rp)
    (out / "index.html").write_text(render(c))
    readme = ROOT / "README.md"
    text = readme.read_bytes().decode()
    new = update_readme(text, readme_table(c["sites"], rp))
    if new != text:
        readme.write_bytes(new.encode())
    print(f"site: {out / 'index.html'}  ({len(c['sites'])} sites, {len(c['tiles'])} test tiles, {len(c['shots'])} shots)"
          + ("" if START in text else f"\nREADME: no {START} … {END} markers → table not written"))
    return 0
