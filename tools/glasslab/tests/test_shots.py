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
