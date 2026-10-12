"""site generator (pure): sites database rows, tile safety (private screens only via scrambled shots tiles), links +
escaping, README table between markers (idempotent)."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from tools.glasslab import shots, site

REGISTRY = [
    {"name": "Mail <Pro>", "matches": ["^https?://mail\\.example\\.com/"], "css": ["./styles/websites/mail.css"],
     "favicon": "https://icons.example/mail.ico"},
    {"name": "Tube", "matches": ["[^ ]*://www.tube.com/[^ ]*"], "css": ["./styles/websites/tube.css"], "glass": "dark"},
    {"name": "Old Site", "matches": ["[^ ]*://[^ ]*.?old-site.org/[^ ]*"], "css": ["./styles/websites/old.css"]},
    {"name": "Chat", "matches": ["^https?://chat\\.example\\.com/"], "css": ["./styles/websites/chat.css"]},
    {"name": "Shadowed", "matches": ["^https?://mail\\.example\\.com/inbox"], "css": ["./styles/websites/x.css"]},
]
SCREENS = [
    {"id": "mail-inbox", "url": "https://mail.example.com/inbox", "private": ["body"], "showcase": True},
    {"id": "mail-thread", "url": "https://mail.example.com/inbox", "private": ["body"]},
    {"id": "tube-home", "url": "https://www.tube.com/", "modes": ["dark"], "showcase": True},
    {"id": "auto-docs", "url": "https://docs.example.org/x", "auto": True},
    {"id": "news-front", "url": "https://news.example.net/"},
    {"id": "chat-home", "url": "https://chat.example.com/"},
]
N = lambda ok, c=0.95, s=0.97, t=0.9: {"contrast": c, "surface": s, "text": t, "ok": ok}
NUMBERS = {
    "mail-inbox.dark.10": N(False), "mail-inbox.dark.45": N(True), "mail-inbox.light.45": N(False, c=0.62),
    "mail-thread.dark.45": N(True), "mail-thread.light.45": N(True),
    "mail-inbox~search-margaret.dark.45": N(True), "mail-inbox~search-margaret.light.45": N(True),
    "tube-home.dark.45": N(True), "tube-home~settings.dark.45": N(False, s=0.4),
    "auto-docs.dark.45": N(True), "auto-docs.light.45": N(True),
}


def by_name(rows):
    return {r["name"]: r for r in rows}


def test_repo_from_glass_ts_single_source():
    assert site.repo('export const REPO = "a/b"; // x') == "a/b"
    assert site.repo() == "nazzacode/transparent-zen"


def test_site_for_first_hit_wins():
    assert site.site_for("https://mail.example.com/inbox", REGISTRY)["name"] == "Mail <Pro>"
    assert site.site_for("https://elsewhere.com/", REGISTRY) is None


def test_parse_key():
    assert site.parse_key("mail-inbox.dark.45") == ("mail-inbox", None, "dark", 45)
    assert site.parse_key("mail-inbox~search-margaret.light.45") == ("mail-inbox", "search-margaret", "light", 45)


def test_sites_database_rows():
    rows = by_name(site.build_sites(REGISTRY, SCREENS, NUMBERS))
    mail = rows["Mail <Pro>"]
    assert mail["status"] == "verified" and mail["screens"] == ["mail-inbox", "mail-thread"]
    assert mail["states"] == 1                                       # hidden UI states (distinct, any mode)
    assert mail["pass"] == {"dark": (3, 3), "light": (2, 3)}         # default slider only (dark.10 ignored)
    assert mail["host"] == "mail.example.com"
    assert rows["Tube"]["pass"] == {"dark": (1, 2)} and rows["Tube"]["forced"] == "dark"
    assert rows["Old Site"]["status"] == "untested" and rows["Old Site"]["host"] == "old-site.org"
    assert rows["Old Site"]["screens"] == [] and rows["Old Site"]["pass"] == {}
    assert rows["docs.example.org"]["status"] == "auto"
    assert rows["news.example.net"]["status"] == "pending"
    assert rows["Chat"]["status"] == "pending" and rows["Chat"]["screens"] == ["chat-home"]   # styled, no results yet
    assert rows["Shadowed"]["status"] == "untested"                  # first registry hit wins → no screens of its own
    order = [r["status"] for r in site.build_sites(REGISTRY, SCREENS, NUMBERS)]
    assert order == sorted(order, key=site.STATUS_ORDER.index)


def test_numbers_from_run_never_carry_page_text():
    results = [{"key": "mail-inbox.dark.45", "screen": "mail-inbox", "mode": "dark", "alpha": 0.45, "contrast": [0.97, 0.91],
                "surface": 0.98, "text": 0.93, "ok": True, "glass": 0.41, "texts": 10, "exempt_img_share": 0,
                "failing": [{"sel": "span.from", "t": "Margaret Thornbury", "lc": [40, 50], "target": 60}],
                "text_foreign": [["rgb(1,2,3) span", 5]], "surface_foreign": []},
               {"key": "mail-inbox~search.dark.45", "screen": "mail-inbox", "state": "Search Margaret", "mode": "dark",
                "alpha": 0.45, "contrast": [0.9], "surface": 0.95, "text": 0.9, "ok": False, "opacity": 0.7,
                "layers": [{"sel": "div", "t": "Margaret"}], "failing": []}]
    n = site.numbers_from_results(results)
    assert "margaret" not in json.dumps(n).lower()
    assert n["mail-inbox.dark.45"] == {"contrast": 0.91, "surface": 0.98, "text": 0.93, "ok": True, "glass": 0.41}
    assert n["mail-inbox~search.dark.45"]["opacity"] == 0.7


@pytest.fixture
def tiles_dir(tmp_path):
    d = tmp_path / "tests"
    d.mkdir()
    st = shots.state_name(SCREENS[0], 0, "mail-inbox~search-margaret", "Search Margaret")
    rows = [shots.entry(SCREENS[0], "dark", {"stem": "mail-inbox", "label": None, "key": "mail-inbox"}),
            shots.entry(SCREENS[0], "dark", st),
            {"file": "mail-thread.dark.webp", "screen": "mail-thread", "state": None, "mode": "dark",
             "key": "mail-thread.dark.45", "scrambled": False},                      # private but not scrambled → never
            {"file": "tube-home.dark.webp", "screen": "tube-home", "state": None, "mode": "dark", "key": "tube-home.dark.45",
             "scrambled": False},
            {"file": "tube-home~settings.dark.webp", "screen": "tube-home", "state": "Settings <menu>", "mode": "dark",
             "key": "tube-home~settings.dark.45", "scrambled": False},
            {"file": "gone.dark.webp", "screen": "gone", "state": None, "mode": "dark", "key": None, "scrambled": False},
            {"file": "tube-home.light.webp", "screen": "tube-home", "state": None, "mode": "light", "key": None,
             "scrambled": False}]                                                    # listed, file missing
    for r in rows[:6]:
        (d / r["file"]).write_bytes(b"RIFF")
    (d / "mail-thread.dark.45.black.png").write_bytes(b"raw")                       # a raw capture lying around
    (d / "index.json").write_text(json.dumps({"tiles": rows}))
    return d


def test_tiles_only_safe_existing_and_known(tiles_dir):
    t = site.load_tiles(tiles_dir, SCREENS, NUMBERS)
    files = [x["file"] for x in t]
    assert files == ["mail-inbox.dark.webp", "mail-inbox~ui-1.dark.webp", "tube-home.dark.webp", "tube-home~settings.dark.webp"]


def test_tiles_join_numbers_public_by_key_private_by_ref(tiles_dir):
    t = {x["file"]: x for x in site.load_tiles(tiles_dir, SCREENS, NUMBERS)}
    assert t["tube-home~settings.dark.webp"]["n"] == NUMBERS["tube-home~settings.dark.45"]
    assert t["mail-inbox~ui-1.dark.webp"]["n"] == NUMBERS["mail-inbox~search-margaret.dark.45"]
    assert t["mail-inbox~ui-1.dark.webp"]["state"] == "hidden UI 1"


def test_private_tile_label_never_page_text(tmp_path):
    (tmp_path / "mail-inbox~ui-1.dark.webp").write_bytes(b"x")
    (tmp_path / "index.json").write_text(json.dumps({"tiles": [
        {"file": "mail-inbox~ui-1.dark.webp", "screen": "mail-inbox", "state": "Margaret Thornbury", "mode": "dark",
         "key": None, "ref": "x", "scrambled": True}]}))
    assert site.load_tiles(tmp_path, SCREENS, NUMBERS)[0]["state"] == "hidden UI"


def test_no_tiles_dir_is_fine(tmp_path):
    assert site.load_tiles(tmp_path / "nope", SCREENS, NUMBERS) == []


def test_issue_links_prefilled():
    u = urlparse(site.issue_url("site-bug", "mail.example.com", repo="a/b"))
    q = parse_qs(u.query)
    assert u.netloc == "github.com" and u.path == "/a/b/issues/new"
    assert q["template"] == ["site-bug.yml"] and q["site"] == ["mail.example.com"] and q["title"] == ["[mail.example.com] "]
    assert q["url"] == ["https://mail.example.com/"]
    r = parse_qs(urlparse(site.issue_url("site-request", repo="a/b")).query)
    assert r["template"] == ["site-request.yml"]


@pytest.fixture
def html(tiles_dir, tmp_path):
    shots_dir = tmp_path / "shots"
    shots_dir.mkdir()
    for f in ("tube-home.dark.webp", "mail-inbox.dark.webp", "mail-inbox.light.webp"):
        (shots_dir / f).write_bytes(b"x")
    ctx = site.context(REGISTRY, SCREENS, NUMBERS, site.load_tiles(tiles_dir, SCREENS, NUMBERS),
                       site.load_shots(shots_dir, SCREENS), repo="a/b")
    return site.render(ctx)


def test_page_escapes_and_links(html):
    assert "Mail &lt;Pro&gt;" in html and "Mail <Pro>" not in html
    assert "Settings &lt;menu&gt;" in html
    assert "https://github.com/a/b/issues/new?template=site-bug.yml" in html
    assert "template=site-request.yml" in html
    assert 'id="t-mail-pro"' in html and 'href="#t-mail-pro"' in html
    assert "https://github.com/a/b/releases/latest" in html
    assert "FrostyBiscuit" in html


def test_page_only_references_safe_tiles(html):
    assert "tests/mail-inbox~ui-1.dark.webp" in html
    assert "mail-thread.dark.webp" not in html and ".png" not in html and "gone.dark" not in html
    assert "search-margaret" not in html and "Search Margaret" not in html


def test_page_beauty_shots(html):
    assert "shots/mail-inbox.dark.webp" in html and "shots/mail-inbox.light.webp" in html
    assert "shots/tube-home.dark.webp" in html


def test_readme_table_and_markers():
    rows = site.build_sites(REGISTRY, SCREENS, NUMBERS)
    table = site.readme_table(rows, repo="a/b")
    assert "| Mail &lt;Pro&gt; |" in table or "| Mail <Pro> |" in table
    assert "Old Site" in table and "3/3" in table
    text = "intro\n<!-- sites:start -->\nold\n<!-- sites:end -->\nrest\n"
    once = site.replace_block(text, table)
    assert once.startswith("intro\n<!-- sites:start -->\n") and once.endswith("<!-- sites:end -->\nrest\n")
    assert "old" not in once and table.strip() in once
    assert site.replace_block(once, table) == once                   # idempotent
    assert site.replace_block("no markers here\n", table) == "no markers here\n"


def test_readme_line_endings_kept():
    raw = "a\r\n<!-- sites:start -->\r\nold\r\n<!-- sites:end -->\r\nb\r\n"
    out = site.update_readme(raw, "| x |\n| y |\n")
    assert out == "a\r\n<!-- sites:start -->\r\n| x |\r\n| y |\r\n<!-- sites:end -->\r\nb\r\n"
    assert site.update_readme(out, "| x |\n| y |\n") == out
    assert site.update_readme("a\n" + raw.replace("\r\n", "\n"), "z") .count("\r") == 0


def test_real_readme_has_markers_once():
    text = (Path(site.ROOT) / "README.md").read_text()
    assert text.count(site.START) == 1 and text.count(site.END) == 1
