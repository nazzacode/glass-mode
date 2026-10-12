"""shots planning (pure): which screens, modes, wallpapers, private scopes; screens.json schema sanity"""
import json
from pathlib import Path

from tools.glasslab import shots, wallgen

SCREENS = [
    {"id": "mail-inbox", "url": "u", "private": ["body"], "showcase": True},
    {"id": "music-home", "url": "u", "modes": ["dark"], "showcase": {"wallpaper": "dusk"}},
    {"id": "tube-home", "url": "u", "showcase": {"modes": ["light"], "wallpaper": {"light": "tide"}}},
    {"id": "mail-thread", "url": "u", "private": ["body"]},
]


def test_only_showcase_screens_matching_filter():
    assert [s["id"] for s in shots.select(SCREENS)] == ["mail-inbox", "music-home", "tube-home"]
    assert [s["id"] for s in shots.select(SCREENS, "mail")] == ["mail-inbox"]


def test_modes_intersect_cli_screen_and_showcase():
    assert shots.modes(SCREENS[0], ["dark", "light"]) == ["dark", "light"]
    assert shots.modes(SCREENS[1], ["dark", "light"]) == ["dark"]        # forced-dark site
    assert shots.modes(SCREENS[2], ["dark", "light"]) == ["light"]       # showcase restricts
    assert shots.modes(SCREENS[0], ["light"]) == ["light"]


def test_wallpaper_per_mode():
    assert shots.wallpaper(SCREENS[0], "dark") == wallgen.for_mode("dark")
    assert shots.wallpaper(SCREENS[0], "light") == wallgen.for_mode("light")
    assert shots.wallpaper(SCREENS[1], "dark") == "dusk"
    assert shots.wallpaper(SCREENS[2], "light") == "tide"
    assert shots.wallpaper(SCREENS[2], "dark") == wallgen.for_mode("dark")


def test_private_scopes():
    assert shots.private(SCREENS[0]) == ["body"]
    assert shots.private(SCREENS[1]) is None


def test_registry_schema():
    data = json.loads((Path(shots.__file__).parent / "screens.json").read_text())["screens"]
    byid = {s["id"]: s for s in data}
    for s in data:
        if s["id"].split("-")[0] in ("gmail", "gcal", "reader", "claude"):
            assert s.get("private"), s["id"]                             # personal apps never shot unscrambled
        for m in shots.modes(s, ["dark", "light"]) if s.get("showcase") else []:
            assert shots.wallpaper(s, m) in wallgen.PRESETS
    for pub in ("youtube-home", "google-search"):
        assert byid[pub].get("showcase") and not byid[pub].get("private")
    assert len(shots.select(data)) >= 5


# ── shots --all: every screen + its hidden UI → test gallery tiles (site/tests) ─────────────────────────────────────
from PIL import Image

ALL = SCREENS + [{"id": "auto-docs", "url": "u", "auto": True}]


def test_all_selects_every_screen_matching_filter():
    assert [s["id"] for s in shots.select_all(ALL)] == ["mail-inbox", "music-home", "tube-home", "mail-thread", "auto-docs"]
    assert [s["id"] for s in shots.select_all(ALL, "mail")] == ["mail-inbox", "mail-thread"]


def test_all_modes_ignore_showcase_restriction():
    assert shots.test_modes(SCREENS[2], ["dark", "light"]) == ["dark", "light"]   # showcase-only limit ≠ tested modes
    assert shots.test_modes(SCREENS[1], ["dark", "light"]) == ["dark"]


def test_state_naming_public_uses_explore_key():
    st = shots.state_name(SCREENS[2], 0, "tube-home~settings", "Settings")
    assert st == {"stem": "tube-home~settings", "label": "Settings", "key": "tube-home~settings"}


def test_state_naming_private_never_carries_page_text():
    st = shots.state_name(SCREENS[0], 2, "mail-inbox~margaret-thornbury", "Margaret Thornbury")
    assert "margaret" not in json.dumps(st).lower()
    assert st["stem"] == "mail-inbox~ui-3" and st["label"] == "hidden UI 3"
    assert st["key"] is None and st["ref"] == shots.ref("mail-inbox~margaret-thornbury")


def test_ref_is_short_stable_hash():
    assert shots.ref("a~b") == shots.ref("a~b") != shots.ref("a~c") and len(shots.ref("a~b")) == 12


def test_entry_bookkeeping():
    e = shots.entry(SCREENS[0], "dark", {"stem": "mail-inbox", "label": None, "key": "mail-inbox"})
    assert e == {"file": "mail-inbox.dark.webp", "screen": "mail-inbox", "state": None, "mode": "dark",
                 "key": "mail-inbox.dark.45", "scrambled": True}
    p = shots.entry(SCREENS[0], "light", shots.state_name(SCREENS[0], 0, "mail-inbox~x", "x"))
    assert p["file"] == "mail-inbox~ui-1.light.webp" and p["key"] is None
    assert p["ref"] == shots.ref("mail-inbox~x") + ".light.45" and p["scrambled"] is True      # join key, no page text
    assert shots.entry(SCREENS[2], "light", {"stem": "tube-home", "label": None, "key": "tube-home"})["scrambled"] is False


def test_merge_index_replaces_reshot_screens_only():
    old = [{"file": "a.dark.webp", "screen": "a"}, {"file": "a~x.dark.webp", "screen": "a"}, {"file": "b.dark.webp", "screen": "b"}]
    new = [{"file": "a.dark.webp", "screen": "a"}]
    assert shots.merge_index(old, new, ["a"]) == [{"file": "a.dark.webp", "screen": "a"}, {"file": "b.dark.webp", "screen": "b"}]


def test_stale_tiles_of_reshot_screens():
    old = [{"file": "a.dark.webp", "screen": "a"}, {"file": "a~x.dark.webp", "screen": "a"}, {"file": "b.dark.webp", "screen": "b"}]
    assert shots.stale(old, [{"file": "a.dark.webp", "screen": "a"}], ["a"]) == ["a~x.dark.webp"]


def test_tile_is_compact_composite_on_blurred_wallpaper():
    black, white = Image.new("RGB", (400, 250), (0, 0, 0)), Image.new("RGB", (400, 250), (255, 255, 255))  # all clear glass
    black.paste((200, 30, 30), (200, 0, 400, 250)); white.paste((200, 30, 30), (200, 0, 400, 250))           # right: opaque red
    wall = wallgen.make("aurora", (640, 400))
    t = shots.tile(black, white, wall, width=320)
    assert t.size == (320, 200) and t.mode == "RGB"
    import numpy as np
    a = np.asarray(t, dtype=float)
    assert np.abs(a[100, 240] - (200, 30, 30)).max() <= 3                                      # opaque keeps colour
    bl = np.asarray(shots.showcase.blurred(shots.showcase.cover(wall, (320, 200))), dtype=float)
    assert np.abs(a[90:110, 40:80] - bl[90:110, 40:80]).mean() < 4                              # clear shows blurred wall
