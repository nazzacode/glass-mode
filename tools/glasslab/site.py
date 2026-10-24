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


def verdict(s):
    """table status from the numbers, never a label: passes / N of M checks fail / not tested yet"""
    p = [v for v in s.get("pass", {}).values() if v]
    if not p:
        return "not tested yet"
    ok, tot = sum(a for a, _ in p), sum(b for _, b in p)
    v = "passes" if ok == tot else f"{tot - ok} of {tot} checks fail"
    return f"auto glass, {v}" if s["status"] == "auto" else v


def readme_table(sites, repo):
    md = lambda s: str(s).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
    lines = [f"Generated by `./glasslab site` from the test baseline (default opacity {A} %). "
             f"[Request a site]({issue_url('site-request', repo=repo)}) · tested screens: see the project page.", "",
             "| Site | Status | Screens tested | Hidden UI tested | Pass dark | Pass light |", "|---|---|---|---|---|---|"]
    for s in sites:
        lines.append(f"| {md(s['name'])} | {verdict(s)} | {len(s['screens']) or '—'} | {s['states'] or '—'} | "
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


# ── copy: one source for the site and the README ─────────────────────────────────────────────────────────────────
# Nathan's brief for docs: no sales, tight docs, sidebar + feature list, one good shot first. Plain sentences; the
# tests forbid em-dashes and sales words here.
COPY = {
    "title": "Glass Mode",
    "lead": "A browser extension that turns websites into frosted glass over your desktop. Text stays readable. Works in Zen Browser.",
    "fork": "Hand-tuned for {n} sites, with text contrast tested on every screen.",
    "features": [
        "Hand-tuned styles for {n} sites: {examples}.",
        "Other sites: automatic glass (beta).",
        "One slider: opacity. Alt+Shift+Up and Down change it from any page.",
        "Light and dark glass. Auto follows your system theme.",
        "Linux: run any site as its own app window.",
    ],
    "requirements": "Requirements: Zen Browser on Linux (Hyprland, KDE or GNOME) or Windows 11. macOS is untested.",
    "why": [
        "Transparent desktops stop at the browser. Every website paints a solid box over your wallpaper, and making "
        "pages simply see-through leaves text unreadable over a busy background.",
        "Glass Mode gives each site frosted panels and menus. Text contrast is measured on every screen and menu, "
        "against the brightest and darkest wallpaper.",
        "It needs Zen because Zen has built-in window transparency, so your desktop can show through a web page. "
        "Chrome-based browsers can't do this. Firefox is untested.",
    ],
    "install": [
        "Download [glass-mode.xpi]({repo}/releases/latest/download/glass-mode.xpi) and open it in Zen. "
        "It is signed by Mozilla.",
        "In `about:config`, set `browser.tabs.allow_transparent_browser` to `true`, then the setting for your system:",
    ],
    "install_os": [
        "Linux: `zen.widget.linux.transparency` = `true`. Your compositor does the blur: Hyprland out of the box, KDE "
        "with [kwin-effects-forceblur](https://github.com/taj-ny/kwin-effects-forceblur), GNOME with "
        "[Blur my Shell](https://extensions.gnome.org/extension/3193/blur-my-shell/).",
        "Windows 11: `widget.windows.mica` = `true`.",
    ],
    "install_note": "Turn off Dark Reader for glass sites. It repaints them solid.",
    "use": [
        "Press Alt+Shift+G in any page to open the glass panel. It also works in web-app windows, which have no toolbar.",
        "Alt+Shift+Up and Alt+Shift+Down make glass more or less opaque.",
    ],
    "opacity": "Low opacity shows more desktop; high is nearly solid. Reading panes stay more opaque than sidebars, "
               "so text stays readable at every step.",
    "modes": "Auto follows your system theme. Dark glass suits dark wallpapers, light glass bright ones.",
    "faq": [
        "**Permissions.** It needs access to every site to style it. It collects nothing and sends nothing. The "
        "settings page only asks GitHub whether a newer version exists.",
        "**Performance.** Site styles are plain CSS. The blur comes from your compositor, not the browser. Automatic "
        "glass reads the page once, then only what changes.",
        "**Which sites?** {n} styled and tested, listed below. Every other site can use automatic glass.",
        "**Something unreadable?** Open the panel and choose Report a problem. It opens a pre-filled issue.",
    ],
    "webapps": [
        "`webapp/zen-webapp` opens a site in its own Zen window, with a launcher entry and taskbar icon. It uses your "
        "normal Zen profile, so you stay logged in.",
    ],
    "webapps_cmd": './webapp/zen-webapp add "WhatsApp" https://web.whatsapp.com/ --icon auto',
    "sites": "Each site is tested in light and dark, including its menus, dropdowns and dialogs.",
    "add": [
        "Missing a site? Turn on automatic glass in the toolbar popup, or [request the site]({request}).",
        "To add one yourself:",
    ],
    "add_cmd": './glasslab add "Linear" https://linear.app/            # style, register, test\n'
               './glasslab add "Linear" https://linear.app/ --agent    # an agent fixes what fails',
    "add_after": ["With `--agent`, edits are kept only if the test scores go up. Full guide: [docs/GLASS.md](docs/GLASS.md)."],
    "how": [
        "Each style maps a site's own colours onto four shared layers: page, sidebar, content and menu.",
        "A test lab opens every screen and menu in a headless browser, measures text contrast against the brightest "
        "and darkest wallpaper, and checks every surface is glass. It never clicks anything that sends or deletes.",
        "Sites without a style get the same layers, guessed from the page's layout.",
    ],
    "credits": [
        "Glass Mode by nazzacode. Originally based on [Transparent Zen](https://github.com/frostybiscuit/transparent-zen) "
        "by FrostyBiscuit. MIT licence.",
    ],
}
EXAMPLES = ["Gmail", "Google Calendar", "Spotify", "WhatsApp", "GitHub", "DuckDuckGo"]
README_SHOTS = {"hero": "wiki-article.light", "panel": "panel.dark", "light": "ddg-search.light", "dark": "ddg-search.dark",
                "strip": ["opacity-10", "opacity-45", "opacity-90"], "gallery": ["spotify-artist.dark", "linear-home.dark"]}

GROUPS = [("Start", [("overview", "Overview"), ("install", "Install"), ("control", "Control"), ("web-apps", "Web apps")]),
          ("Project", [("add", "Add a site"), ("testing", "How it works"), ("credits", "Credits")])]
DOT = {"verified": "live", "pending": "partial", "untested": "planned", "auto": "planned"}


def gh(repo, path=""):
    return f"https://github.com/{repo}{path}"


def fill(text, c):
    names = {s["name"] for s in c["sites"]}
    ex = [e for e in EXAMPLES if e in names] or EXAMPLES
    return text.format(n=sum(s["status"] == "verified" for s in c["sites"]), repo=gh(c["repo"]),
                       request=issue_url("site-request", repo=c["repo"]), examples=", ".join(ex[:-1]) + " and " + ex[-1])


def inline(text):
    """tiny markdown → html: `code`, [text](url); everything else escaped"""
    out, pos = [], 0
    for m in re.finditer(r"`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)", text):
        out.append(esc(text[pos:m.start()]))
        out.append(f"<code>{esc(m[1])}</code>" if m[1] else f'<a href="{esc(m[3])}">{esc(m[2])}</a>')
        pos = m.end()
    return "".join(out) + esc(text[pos:])


def paras(lines, c):
    return "".join(f"<p>{inline(fill(l, c))}</p>" for l in lines)


def bold(html_):
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", html_)


# ── page ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def view_name(screen, names):
    """'gmail-inbox' → ('Gmail', 'inbox')"""
    return names.get(screen, screen), screen.split("-", 1)[1].replace("-", " ") if "-" in screen else screen


def pct(v):
    return f"{round(v * 100)}%"


def picture(shot, alt):
    """dark + light pair → <picture> following the viewer's scheme"""
    d, l = shot["dark"], shot["light"]
    img = f'<img src="shots/{esc(d or l)}" alt="{esc(alt)}" width="1280" height="800" decoding="async" loading="lazy">'
    return f'<picture><source srcset="shots/{esc(l)}" media="(prefers-color-scheme: light)">{img}</picture>' if d and l \
        else f"<picture>{img}</picture>"


def hero_shot(c):
    by = {s["screen"]: s for s in c["shots"]}
    return next((by[k] for k in (README_SHOTS["hero"].split(".")[0], "gmail-inbox", "spotify-artist") if k in by),
                c["shots"][0] if c["shots"] else None)


def overview(c):
    hero = hero_shot(c)
    fig = f'<figure class="hero">{picture(hero, "Glass Mode")}</figure>' if hero else ""
    feats = "".join(f"<li>{inline(fill(f, c))}</li>" for f in COPY["features"])
    names = c["names"]
    grid = "".join(f'<figure>{picture(s, view_name(s["screen"], names)[0])}<figcaption>{esc(view_name(s["screen"], names)[0])}'
                   f'</figcaption></figure>' for s in c["shots"] if s is not hero)
    return (f'<article id="overview"><h1>{esc(COPY["title"])}</h1><p class="sub">{esc(COPY["lead"])}</p>'
            f'<p>{inline(fill(COPY["fork"], c))}</p>{fig}<ul>{feats}</ul><p>{esc(COPY["requirements"])}</p>'
            f'<h2>Why</h2>{paras(COPY["why"], c)}<h2>FAQ</h2>{bold(paras(COPY["faq"], c))}' + (f'<h2>Gallery</h2><div class="grid">{grid}</div>' if grid else "") + "</article>")


def steps(lines, c):
    return "<ol>" + "".join(f"<li>{inline(fill(l, c))}</li>" for l in lines) + "</ol>"


def rate(p):
    return f'<span class="{"ok" if p and p[0] == p[1] else "warn" if p else "dim"}">{frac(p)}</span>'


def thumbs(s, c):
    """card image per mode: beauty shot > default-state test tile > any tile; a missing mode borrows the other"""
    mine = lambda xs: [x for x in xs if x["screen"] in s["screens"]]
    shots_, tiles = mine(c["shots"]), mine(c["tiles"])
    pick = lambda m: next((f"shots/{x[m]}" for x in shots_ if x[m]), None) or next(
        (f"tests/{t['file']}" for t in sorted(tiles, key=lambda t: t["state"] is not None) if t["mode"] == m), None)
    got = {m: pick(m) for m in MODES}
    return {m: got[m] or next((v for v in got.values() if v), None) for m in MODES}


def data_attrs(s):
    return (f'data-name="{esc(s["name"].lower())}" data-host="{esc((s["host"] or "").lower())}" '
            f'data-status="{esc(s["status"])}"')


def card_html(s, c):
    t = thumbs(s, c)
    img = (f'<img src="{esc(t["dark"])}" data-dark="{esc(t["dark"])}" data-light="{esc(t["light"])}" alt="{esc(s["name"])}" '
           f'width="960" height="600" loading="lazy" decoding="async">' if t["dark"] else '<div class="noimg">no screenshot yet</div>')
    return (f'<figure class="card" {data_attrs(s)}>{img}<figcaption><a href="#site-{esc(s["id"])}"><span class="dot '
            f'{DOT[s["status"]]}"></span>{esc(s["name"])}</a><small>{esc(verdict(s))}</small></figcaption></figure>')


CHIPS = [("verified", "tested", True), ("pending", "pending", True), ("auto", "auto", False)]


def seg(key, opts, label):
    """button group; aria-pressed marks the chosen one (the script keeps it in sync)"""
    return (f'<div class="seg" data-key="{key}" role="group" aria-label="{label}">'
            + "".join(f'<button type="button" value="{v}" aria-pressed="{str(on).lower()}">{t}</button>' for v, t, on in opts)
            + "</div>")


def sites_page(c):
    listed = [s for s in c["sites"] if s["screens"]]
    n = {k: sum(s["status"] == k for s in listed) for k, _, _ in CHIPS}
    chips = seg("status", [(k, f'<span class="dot {DOT[k]}"></span>{t} <span class="dim">{n[k]}</span>', on)
                           for k, t, on in CHIPS if n[k]], "Status")
    bar = (f'<div class="bar"><input type="search" id="q" placeholder="Search {len(listed)} sites" aria-label="Search sites" '
           f'autocomplete="off">{chips}{seg("mode", [("dark", "Dark", True), ("light", "Light", False)], "Glass")}'
           f'<select id="sort" aria-label="Sort"><option value="status">Status</option><option value="name">A to Z</option>'
           f'<option value="shuffle">Shuffle</option></select>'
           f'{seg("view", [("grid", "Grid", True), ("table", "Table", False)], "View")}</div>')
    rows = "".join(
        f'<tr {data_attrs(s)}><td><a href="#site-{esc(s["id"])}">{esc(s["name"])}</a></td><td><span class="dot {DOT[s["status"]]}"></span>'
        f'{esc(verdict(s))}</td><td>{len(s["screens"]) or "–"}</td><td>{s["states"] or "–"}</td>'
        f'<td>{rate(s["pass"].get("dark"))}</td><td>{rate(s["pass"].get("light"))}</td></tr>'
        for s in listed)
    return (f'<article id="sites" class="wide"><h1>Sites</h1><p class="sub">Every styled site and what the lab checked at the '
            f'default opacity ({c["opacity"].get("default", A)} %). Click a picture to flip through them; click a name for its screens and menus.</p>'
            f'{bar}<p class="count dim" aria-live="polite"></p>'
            f'<div class="grid cards">{"".join(card_html(s, c) for s in listed)}</div>'
            f'<div class="tbl" hidden><table><thead><tr><th>Site</th><th>Status</th><th>Screens</th><th>Hidden UI</th><th>Dark</th>'
            f'<th>Light</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p class="empty" hidden>No site matches.</p>'
            f'<p><a href="{esc(issue_url("site-request", repo=c["repo"]))}">Request a site</a></p></article>')


def tile_html(t, names):
    _, view = view_name(t["screen"], names)
    title = esc(t["state"]) if t["state"] else esc(view)
    n = t["n"]
    nums = (f'<span class="{"ok" if n["ok"] else "bad"}">{"pass" if n["ok"] else "fail"}</span> contrast {pct(n["contrast"])} '
            f'· surface {pct(n["surface"])}' if n else '<span class="dim">not measured</span>')
    return (f'<figure class="tile"><img src="tests/{esc(t["file"])}" alt="{esc(view)} {title} ({t["mode"]})" loading="lazy" '
            f'decoding="async" width="960" height="600"><figcaption><b>{title}</b> <span class="dim">{t["mode"]}</span>'
            f'<br>{nums}</figcaption></figure>')


def site_page(s, c):
    shots = [x for x in c["shots"] if x["screen"] in s["screens"]]
    tiles = [t for t in c["tiles"] if t["screen"] in s["screens"]]
    pd, pl = s["pass"].get("dark"), s["pass"].get("light")
    return (f'<article id="site-{esc(s["id"])}"><a class="back" href="#sites">All sites</a><span class="status"><span class="dot {DOT[s["status"]]}"></span>'
            f'{esc(verdict(s))}</span><h1>{esc(s["name"])}</h1><p class="sub">{esc(s["host"] or "")}. Passing at '
            f'default opacity: dark {frac(pd)}, light {frac(pl)}.'
            + (" Dark only." if s.get("forced") == "dark" else "") + "</p>"
            + "".join(f"<figure>{picture(x, s['name'])}</figure>" for x in shots)
            + (f'<h2>Tested screens and hidden UI</h2><div class="grid tiles">{"".join(tile_html(t, c["names"]) for t in tiles)}</div>'
               if tiles else "")
            + f'<p><a href="{esc(issue_url("site-bug", s["host"], c["repo"]))}">Report a problem on {esc(s["name"])}</a></p></article>')


def text_page(id_, title, lines, c, extra=""):
    return f'<article id="{id_}"><h1>{esc(title)}</h1>{paras(lines, c)}{extra}</article>'


def pre(text):
    return f"<pre><code>{esc(text)}</code></pre>"


def sidebar(c):
    """topics + one Sites link; the site list itself lives in the gallery (it only grows)"""
    groups = "".join(f'<div class="group">{g}</div>' + "".join(f'<a href="#{i}">{t}</a>' for i, t in items) for g, items in GROUPS)
    n = sum(bool(s["screens"]) for s in c["sites"])
    return (f'<nav class="pane"><div class="brand"><b>{esc(COPY["title"])}</b><small>Glass for Zen Browser</small>'
            f'<small><a href="{gh(c["repo"])}">GitHub</a> · <a href="{gh(c["repo"], "/releases/latest")}">Download</a></small></div>'
            f'{groups}<div class="group">Sites</div><a href="#sites">All sites <span class="dim">{n}</span></a></nav>')


SCRIPT = (HERE / "site.js").read_text()


def render(c):
    listed = [s for s in c["sites"] if s["screens"]]
    articles = "".join([
        overview(c),
        f'<article id="install"><h1>Install</h1>{steps(COPY["install"], c)}<ul>'
        + "".join(f"<li>{inline(fill(l, c))}</li>" for l in COPY["install_os"]) + f"</ul><p>{inline(COPY['install_note'])}</p></article>",
        text_page("control", "Control", COPY["use"] + [COPY["opacity"], COPY["modes"]], c),
        text_page("web-apps", "Web apps", COPY["webapps"], c, pre(COPY["webapps_cmd"]) + '<p><a href="'
                  + gh(c["repo"], "/blob/master/webapp/README.md") + '">webapp/README.md</a></p>'),
        sites_page(c), *(site_page(s, c) for s in listed),
        text_page("add", "Add a site", COPY["add"], c, pre(COPY["add_cmd"]) + paras(COPY["add_after"], c)),
        text_page("testing", "How it works", COPY["how"], c),
        text_page("credits", "Credits", COPY["credits"], c),
    ])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(COPY["title"])}</title>
<meta name="description" content="{esc(COPY["lead"])}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;14..32,400;14..32,500&family=JetBrains+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="shell">
{sidebar(c)}
<main class="pane">{articles}</main>
</div>
<dialog id="lightbox" aria-label="Gallery"><img alt=""><p></p><button value="-1" aria-label="Previous">‹</button>
<button value="1" aria-label="Next">›</button><button value="close" aria-label="Close">×</button></dialog>
<script>
{SCRIPT}</script>
</body>
</html>
"""


# ── README: same copy, markdown ─────────────────────────────────────────────────────────────────────────────────────
def md_lines(lines, c, prefix=""):
    return "\n\n".join(prefix + fill(l, c) for l in lines)


def shot(name, alt, width=None):
    """README image from site/shots (webp); empty when the file isn't there"""
    f = SITE / "shots" / f"{name}.webp"
    if not f.is_file():
        return ""
    return f'<img src="site/shots/{name}.webp" alt="{alt}" width="{width}">' if width else f"![{alt}](site/shots/{name}.webp)"


def readme_md(c):
    R = README_SHOTS
    site_url = f"https://{c['repo'].split('/')[0]}.github.io/{c['repo'].split('/')[1]}/"
    strip = [shot(n, f"opacity {n[-2:]} %") for n in R["strip"]]
    gallery = [g for g in (shot(n, n.split("-")[0].split(".")[0].title()) for n in R["gallery"]) if g]
    bullets = lambda lines: "\n".join(f"- {fill(l, c)}" for l in lines)
    md = [f"# {COPY['title']}", "", COPY["lead"], "", fill(COPY["fork"], c), "",
          f"Website, every site and test results: [{site_url}]({site_url})", "", shot(R["hero"], "Wikipedia as light glass"), "",
          bullets(COPY["features"]), "", COPY["requirements"], "",
          "## Why", "", md_lines(COPY["why"], c), "",
          "## Install", "", "\n".join(f"{i}. {fill(l, c)}" for i, l in enumerate(COPY["install"], 1)), "",
          bullets(COPY["install_os"]), "", COPY["install_note"], "",
          "## Use", "", shot(R["panel"], "The glass panel", 420), "", md_lines(COPY["use"], c), ""]
    if all(strip):
        md += ["| 10 % | 45 % (default) | 90 % |", "|---|---|---|", "| " + " | ".join(strip) + " |", "", COPY["opacity"], ""]
    if shot(R["dark"], "x") and shot(R["light"], "x"):
        md += ["| Dark | Light |", "|---|---|", f"| {shot(R['dark'], 'DuckDuckGo, dark glass')} | {shot(R['light'], 'DuckDuckGo, light glass')} |",
               "", COPY["modes"], ""]
    if len(gallery) >= 2:
        md += ["## Gallery", "", "| | |", "|---|---|", f"| {gallery[0]} | {gallery[1]} |", "",
               f"Every site, screen and menu: [{site_url}]({site_url})", ""]
    md += ["## FAQ", "", md_lines(COPY["faq"], c), "",
           "## Sites", "", fill(COPY["sites"], c), "", "<details><summary>All sites and test results</summary>", "",
           START, readme_table(c["sites"], c["repo"]).strip(), END, "", "</details>", "",
           "## How it works", "", bullets(COPY["how"]), "",
           "## Web apps (Linux)", "", md_lines(COPY["webapps"], c), "", "```sh", COPY["webapps_cmd"], "```", "",
           "## Add a site", "", md_lines(COPY["add"], c), "", "```sh", COPY["add_cmd"], "```", "", md_lines(COPY["add_after"], c), "",
           "## Credits", "", md_lines(COPY["credits"], c), ""]
    return "\n".join(md)


def main(run=None, out=None):
    out = Path(out or SITE)
    out.mkdir(parents=True, exist_ok=True)
    reg, screens, numbers, rp = registry(), load_screens(), load_numbers(run), repo()
    c = context(reg, screens, numbers, load_tiles(out / "tests", screens, numbers), load_shots(out / "shots", screens), rp)
    (out / "index.html").write_text(render(c))
    readme = ROOT / "README.md"
    crlf = "\r\n" in readme.read_bytes().decode()
    text = readme_md(c)
    readme.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode())
    print(f"site: {out / 'index.html'}  ({len(c['sites'])} sites, {len(c['tiles'])} test tiles, {len(c['shots'])} shots)\n"
          f"README.md regenerated from the same copy")
    return 0
