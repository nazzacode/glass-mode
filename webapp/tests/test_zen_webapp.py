"""zen-webapp unit tests: fake HOME per test, no network, no real Zen (running-check, exec, fetch all injected)."""
import io, json, uuid
from pathlib import Path

import pytest

from webapp import zen_webapp as zw

APP = zw.FLATPAK_APP
NO_SYSTEM = Path("/nonexistent-flatpak-system")


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {"HOME": str(home), "PATH": str(tmp_path / "bin")}


def flatpak_root(env):
    return Path(env["HOME"]) / ".var/app" / APP / ".zen"


def write_ini(root, text):
    root.mkdir(parents=True, exist_ok=True)
    (root / "profiles.ini").write_text(text)


INSTALL_INI = """[Profile0]
Name=old
IsRelative=1
Path=old.default
Default=1

[Install1234ABCD]
Default=abc.Default (release)
Locked=1
"""
PROFILE_INI = """[Profile1]
Name=other
IsRelative=1
Path=other.x

[Profile0]
Name=main
IsRelative=1
Path=main.default
Default=1
"""


@pytest.fixture
def flatpak(env):
    """flatpak Zen with one profile; returns (env, profile dir)"""
    root = flatpak_root(env)
    write_ini(root, INSTALL_INI)
    prof = root / "abc.Default (release)"
    prof.mkdir()
    return env, prof


def run(env, *argv, running=False, fetch=None):
    """main() with captured output; exec recorded instead of replacing the process"""
    out, err, execs = io.StringIO(), io.StringIO(), []
    code = zw.main(list(argv), env=env, procs=lambda: [["/app/zen/zen", "--name", APP]] if running else [],
                   execvp=lambda f, a: execs.append(a), fetch=fetch or (lambda url: None),
                   out=out, err=err, flatpak_system=NO_SYSTEM)
    return code, out.getvalue(), err.getvalue(), execs


def registry(prof):
    return json.loads((prof / "taskbartabs/taskbartabs.json").read_text())


# ── ids ─────────────────────────────────────────────────────────────────────

def test_app_id_stable_uuid5():
    assert zw.app_id("chat") == zw.app_id("chat") == str(uuid.uuid5(zw.NAMESPACE, "chat"))
    assert zw.app_id("chat") != zw.app_id("mail")
    assert str(zw.NAMESPACE) == "6f1d9c8e-3b0a-5c2e-9a4f-7e5b2d1c0a93"  # changing it orphans every installed app


def test_slugify():
    assert zw.slugify("Google Calendar!") == "google-calendar"
    assert zw.slugify("  ÄB  c ") == "ab-c"


# ── apps.json editing (pure) ────────────────────────────────────────────────

def test_add_replaces_same_slug_and_sorts():
    apps = zw.add_app([], "b", "B", "https://b.com")
    apps = zw.add_app(apps, "a", "A", "https://a.com")
    apps = zw.add_app(apps, "b", "B2", "https://b2.com")
    assert [(a["slug"], a["name"]) for a in apps] == [("a", "A"), ("b", "B2")]


def test_add_rejects_non_http():
    with pytest.raises(ValueError):
        zw.add_app([], "x", "X", "file:///etc/passwd")
    with pytest.raises(ValueError):
        zw.add_app([], "Bad Slug", "X", "https://x.com")


def test_remove_app():
    apps = zw.add_app([], "a", "A", "https://a.com")
    assert zw.remove_app(apps, "a") == []
    with pytest.raises(KeyError):
        zw.remove_app(apps, "zz")


# ── registry merge ──────────────────────────────────────────────────────────

APPS = [{"slug": "chat", "name": "Chat", "url": "https://chat.example.com/app"}]


def test_entry_shape():
    e = zw.entry(APPS[0])
    assert e == {"id": zw.app_id("chat"), "scopes": [{"hostname": "chat.example.com"}], "userContextId": 0,
                 "startUrl": "https://chat.example.com/app", "name": "Chat",
                 "shortcutRelativePath": "webapp-chat.desktop"}


def test_merge_rules():
    mine = {"id": "u1", "scopes": [{"hostname": "own.org"}], "name": "Own", "shortcutRelativePath": "own.desktop"}
    managed_old = {"id": "u2", "scopes": [{"hostname": "gone.com"}], "shortcutRelativePath": "webapp-gone.desktop"}
    stray = {"id": "u3", "scopes": [{"hostname": "chat.example.com"}]}       # unpinned, collides → drop
    stray_ok = {"id": "u4", "scopes": [{"hostname": "elsewhere.net"}]}       # unpinned, no collision → keep
    out = zw.merged([mine, managed_old, stray, stray_ok], APPS)
    assert [t["id"] for t in out] == ["u1", "u4", zw.app_id("chat")]


def test_merge_idempotent():
    once = zw.merged([], APPS)
    assert zw.merged(once, APPS) == once


# ── userChrome block ────────────────────────────────────────────────────────

def test_userchrome_appends_and_preserves_user_css():
    user = '@import url("mine.css");\n#nav-bar { color: red; }\n'
    out = zw.merge_block(user, ".a{}")
    assert out.startswith(user)
    assert f"{zw.BEGIN}\n.a{{}}\n{zw.END}\n" in out


def test_userchrome_replace_idempotent():
    user = "/* top */\n"
    once = zw.merge_block(user + "\n/* after */\n", ".a{}")
    assert zw.merge_block(once, ".a{}") == once
    twice = zw.merge_block(once, ".b{}")
    assert ".a{}" not in twice and ".b{}" in twice and "/* top */" in twice and "/* after */" in twice
    assert twice.count(zw.BEGIN) == 1


def test_userchrome_empty_file():
    assert zw.merge_block("", ".a{}") == f"{zw.BEGIN}\n.a{{}}\n{zw.END}\n"


def test_unblock_removes_only_ours():
    user = "/* mine */\n"
    assert zw.unblock(zw.merge_block(user, ".a{}")) == user


def test_shipped_css_has_no_private_import():
    css = zw.CSS.read_text()
    assert ":root[taskbartab]" in css and "@import" not in css


# ── user.js ─────────────────────────────────────────────────────────────────

def test_prefs_added_once_and_keep_user_lines():
    user = 'user_pref("foo", 1);\n'
    once = zw.add_prefs(user)
    assert once.startswith(user)
    for p in zw.PREFS:
        assert once.count(f'user_pref("{p}"') == 1
    assert zw.add_prefs(once) == once


def test_prefs_respect_existing_user_setting():
    user = 'user_pref("browser.taskbarTabs.enabled", true);'  # no trailing newline
    out = zw.add_prefs(user)
    assert out.count("browser.taskbarTabs.enabled") == 1
    assert 'user_pref("browser.taskbarTabs.enabled", true);\nuser_pref("toolkit' in out


# ── desktop file ────────────────────────────────────────────────────────────

def test_desktop_file():
    text = zw.desktop_entry(APPS[0], Path("/opt/my tools/zen-webapp"), Path("/i/chat.ico"))
    lines = text.splitlines()
    assert lines[0] == "[Desktop Entry]"
    for want in ["Type=Application", "Name=Chat", 'Exec="/opt/my tools/zen-webapp" launch chat', "Icon=/i/chat.ico",
                 "StartupWMClass=webapp-chat", "Categories=Network;", "X-Zen-Webapp=true"]:
        assert want in lines


def test_desktop_file_no_icon():
    text = zw.desktop_entry(APPS[0], Path("/bin/zen-webapp"), None)
    assert "Icon=" not in text and "Exec=/bin/zen-webapp launch chat" in text


# ── zen detection / profile ─────────────────────────────────────────────────

def test_profile_install_default_wins(tmp_path):
    write_ini(tmp_path, INSTALL_INI)
    assert zw.profile(tmp_path) == tmp_path / "abc.Default (release)"


def test_profile_falls_back_to_default_1(tmp_path):
    write_ini(tmp_path, PROFILE_INI)
    assert zw.profile(tmp_path) == tmp_path / "main.default"


def test_profile_absolute_path(tmp_path):
    write_ini(tmp_path, "[Profile0]\nIsRelative=0\nPath=/abs/prof\nDefault=1\n")
    assert zw.profile(tmp_path) == Path("/abs/prof")


def test_profile_missing(tmp_path):
    assert zw.profile(tmp_path) is None


def test_find_flatpak(flatpak):
    env, prof = flatpak
    z = zw.find_zen(env, flatpak_system=NO_SYSTEM)
    assert z.kind == "flatpak" and z.cmd == ["flatpak", "run", APP] and z.root == flatpak_root(env)


def test_find_native(env, tmp_path):
    root = Path(env["HOME"]) / ".zen"
    write_ini(root, PROFILE_INI)
    bindir = Path(env["PATH"])
    bindir.mkdir()
    (bindir / "zen-browser").write_text("#!/bin/sh\n")
    (bindir / "zen-browser").chmod(0o755)
    z = zw.find_zen(env, flatpak_system=NO_SYSTEM)
    assert z.kind == "native" and z.cmd == [str(bindir / "zen-browser")] and zw.profile(z.root) == root / "main.default"


def test_find_none(env):
    assert zw.find_zen(env, flatpak_system=NO_SYSTEM) is None


def test_running_anchored():
    flat = zw.Zen("flatpak", Path("/r"), ["flatpak", "run", APP])
    assert zw.is_running(flat, lambda: [["/app/zen/zen", "--name", APP, "-foo"]])
    assert not zw.is_running(flat, lambda: [["ssh", "host", f"cat ~/.var/app/{APP}/.zen/x"]])
    nat = zw.Zen("native", Path("/r"), ["/usr/bin/zen"])
    assert zw.is_running(nat, lambda: [["/usr/lib/zen/zen", "-contentproc"]])
    assert zw.is_running(nat, lambda: [["zen-browser"]])
    assert not zw.is_running(nat, lambda: [["/home/u/bin/zen-webapp", "list"], ["vim", "/x/zen"]])


# ── CLI round-trips ─────────────────────────────────────────────────────────

def test_add_list_remove_roundtrip(flatpak):
    env, prof = flatpak
    code, out, _, _ = run(env, "add", "My Chat", "https://chat.example.com/")
    assert code == 0
    cfg = json.loads((Path(env["HOME"]) / ".config/zen-webapps/apps.json").read_text())
    assert cfg == [{"slug": "my-chat", "name": "My Chat", "url": "https://chat.example.com/"}]
    desk = Path(env["HOME"]) / ".local/share/applications/webapp-my-chat.desktop"
    assert "StartupWMClass=webapp-my-chat" in desk.read_text()
    assert registry(prof)["taskbarTabs"][0]["id"] == zw.app_id("my-chat")
    assert zw.BEGIN in (prof / "chrome/userChrome.css").read_text()
    assert "restart Zen" in out  # first sync: pref only exists after a restart

    _, out, _, _ = run(env, "list")
    assert "my-chat" in out and "https://chat.example.com/" in out

    code, _, _, _ = run(env, "remove", "my-chat")
    assert code == 0 and not desk.exists() and registry(prof)["taskbarTabs"] == []


def test_xdg_dirs_respected(flatpak, tmp_path):
    env, _ = flatpak
    env = {**env, "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "XDG_DATA_HOME": str(tmp_path / "data")}
    run(env, "add", "A", "https://a.com", "--slug", "aa")
    assert (tmp_path / "cfg/zen-webapps/apps.json").exists()
    assert (tmp_path / "data/applications/webapp-aa.desktop").exists()


def test_sync_deferred_while_running(flatpak):
    env, prof = flatpak
    code, out, _, _ = run(env, "add", "Chat", "https://chat.example.com/", running=True)
    assert code == 0 and "deferred" in out
    assert not (prof / "taskbartabs").exists() and not (prof / "user.js").exists()
    assert (Path(env["HOME"]) / ".local/share/applications/webapp-chat.desktop").exists()  # desktop files: always
    run(env, "sync")
    assert registry(prof)["taskbarTabs"][0]["startUrl"] == "https://chat.example.com/"


def test_sync_keeps_user_registry_and_css(flatpak):
    env, prof = flatpak
    (prof / "taskbartabs").mkdir()
    own = {"id": "u1", "scopes": [{"hostname": "own.org"}], "userContextId": 0, "startUrl": "https://own.org",
           "name": "Own", "shortcutRelativePath": "own.desktop"}
    (prof / "taskbartabs/taskbartabs.json").write_text(json.dumps({"version": 1, "taskbarTabs": [own]}))
    (prof / "chrome").mkdir()
    (prof / "chrome/userChrome.css").write_text("/* mine */\n")
    run(env, "add", "Chat", "https://chat.example.com/")
    assert [t["id"] for t in registry(prof)["taskbarTabs"]] == ["u1", zw.app_id("chat")]
    assert (prof / "chrome/userChrome.css").read_text().startswith("/* mine */\n")
    _, out, _, _ = run(env, "sync")
    assert "nothing" in out


def test_sync_removes_stale_desktop_files_only_ours(flatpak):
    env, _ = flatpak
    apps_dir = Path(env["HOME"]) / ".local/share/applications"
    apps_dir.mkdir(parents=True)
    (apps_dir / "webapp-foreign.desktop").write_text("[Desktop Entry]\nName=Foreign\n")  # not ours (no marker)
    (apps_dir / "webapp-old.desktop").write_text("[Desktop Entry]\nName=Old\nX-Zen-Webapp=true\n")
    run(env, "sync")
    assert (apps_dir / "webapp-foreign.desktop").exists() and not (apps_dir / "webapp-old.desktop").exists()


def test_icon_auto_uses_injected_fetch(flatpak):
    env, _ = flatpak
    seen = []
    run(env, "add", "Chat", "https://chat.example.com/", "--icon", "auto",
        fetch=lambda url: seen.append(url) or b"\x00ICO")
    assert seen == ["https://icons.duckduckgo.com/ip3/chat.example.com.ico"]
    icon = Path(env["HOME"]) / ".local/share/zen-webapps/icons/chat.ico"
    assert icon.read_bytes() == b"\x00ICO"
    desk = (Path(env["HOME"]) / ".local/share/applications/webapp-chat.desktop").read_text()
    assert f"Icon={icon}" in desk


def test_icon_auto_failure_warns(flatpak):
    env, _ = flatpak

    def boom(url):
        raise OSError("offline")
    code, _, err, _ = run(env, "add", "Chat", "https://chat.example.com/", "--icon", "auto", fetch=boom)
    assert code == 0 and "icon" in err
    assert "Icon=" not in (Path(env["HOME"]) / ".local/share/applications/webapp-chat.desktop").read_text()


def test_icon_path_copied(flatpak, tmp_path):
    env, _ = flatpak
    src = tmp_path / "logo.png"
    src.write_bytes(b"PNG")
    run(env, "add", "Chat", "https://chat.example.com/", "--icon", str(src))
    assert (Path(env["HOME"]) / ".local/share/zen-webapps/icons/chat.png").read_bytes() == b"PNG"


def test_launch_flatpak(flatpak):
    env, prof = flatpak
    run(env, "add", "Chat", "https://chat.example.com/")
    code, _, _, execs = run(env, "launch", "chat")
    assert code == 0
    assert execs == [["flatpak", "run", APP, "-taskbar-tab", zw.app_id("chat"), "-new-window",
                      "https://chat.example.com/", "-container", "0"]]


def test_launch_running_unregistered_warns(flatpak):
    env, prof = flatpak
    run(env, "add", "Chat", "https://chat.example.com/", running=True)
    code, _, err, execs = run(env, "launch", "chat", running=True)
    assert code == 0 and len(execs) == 1 and "restart Zen" in err


def test_launch_unknown(flatpak):
    env, _ = flatpak
    code, _, err, execs = run(env, "launch", "nope")
    assert code != 0 and execs == [] and "nope" in err


def test_no_zen(env):
    code, _, err, _ = run(env, "sync")
    assert code != 0 and "Zen" in err


# ── doctor ──────────────────────────────────────────────────────────────────

def test_doctor_fresh_and_synced(flatpak):
    env, prof = flatpak
    run(env, "add", "Chat", "https://chat.example.com/", running=True)
    code, out, _, _ = run(env, "doctor", running=True)
    assert code == 0
    assert "flatpak" in out and str(prof) in out
    assert "running" in out and "pending" in out and "registry" in out
    _, out, _, _ = run(env, "doctor")
    assert "not running" in out
    run(env, "sync")
    (prof / "prefs.js").write_text('user_pref("browser.taskbarTabs.enabled", true);\n')
    _, out, _, _ = run(env, "doctor")
    assert "1/1" in out and "pending" not in out and "restart" not in out


def test_doctor_without_zen(env):
    code, out, _, _ = run(env, "doctor")
    assert code != 0 and "not found" in out


# ── review fixes ──
def test_running_flatpak_however_launched():
    """the sandboxed main process is /app/zen/zen whatever its flags (headless lab, -P profile); content procs aren't"""
    flat = zw.Zen("flatpak", Path("/r"), ["flatpak", "run", APP])
    assert zw.is_running(flat, lambda: [["/app/zen/zen", "-P", "work"]])
    assert zw.is_running(flat, lambda: [["/app/zen/zen", "--headless", "--profile", "/x"]])
    assert not zw.is_running(flat, lambda: [["/app/zen/zen", "-contentproc", "-childID", "3"]])


def test_control_characters_rejected():
    for name, url in [("Chat\nExec=rm -rf ~", "https://chat.example.com/"), ("Chat", "https://chat.example.com/\nExec=x")]:
        try:
            zw.add_app([], "chat", name, url)
        except ValueError:
            continue
        raise AssertionError(f"accepted {name!r} {url!r}")


def test_bad_slug_fails_before_any_icon_is_written(flatpak):
    env, _ = flatpak
    fetched = []
    code, _, err, _ = run(env, "add", "Chat", "https://chat.example.com/", "--slug", "../../.config/autostart/x",
                          "--icon", "auto", fetch=lambda url: fetched.append(url) or b"\x00ICO")
    assert code != 0 and fetched == []
    assert not any((Path(env["HOME"]) / ".config/autostart").glob("*"))
