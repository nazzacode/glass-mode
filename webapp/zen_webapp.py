"""zen-webapp: web apps as chromeless Zen windows via Firefox Taskbar Tabs (pref browser.taskbarTabs.enabled, Zen 1.23+ /
Firefox 157 on Linux). Shares the main profile (logins, extensions, glass).

Each app = one registry entry in <profile>/taskbartabs/taskbartabs.json with a stable id; its shortcutRelativePath
"webapp-<slug>.desktop" makes Zen set window class webapp-<slug> (= desktop file id) → proper taskbar icon/grouping.
Unknown id → Firefox mints a random uuid + generic class. Zen holds the registry in memory and rewrites it on exit →
the profile is only ever written while Zen is closed. Pure planning (what each file should contain) is split from IO so
`doctor` can show what is pending."""
import argparse, configparser, json, os, re, shutil, sys, unicodedata, uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

FLATPAK_APP = "app.zen_browser.zen"
NATIVE_BINS = ("zen", "zen-browser", "zen-beta")
# fixed forever: app id = uuid5(NAMESPACE, slug); changing it orphans every installed app's registry entry
NAMESPACE = uuid.UUID("6f1d9c8e-3b0a-5c2e-9a4f-7e5b2d1c0a93")
CSS = Path(__file__).resolve().parent / "userChrome.css"
EXE = Path(__file__).resolve().parent / "zen-webapp"
BEGIN, END = "/* zen-webapp:begin */", "/* zen-webapp:end */"
PREFS = {
    "browser.taskbarTabs.enabled": "web-app windows",
    "toolkit.legacyUserProfileCustomizations.stylesheets": "load chrome/userChrome.css",
}
ICON_URL = "https://icons.duckduckgo.com/ip3/{}.ico"
MARK = "X-Zen-Webapp=true"  # our .desktop files; stale ones with it get removed, foreign webapp-*.desktop never


# ── paths ───────────────────────────────────────────────────────────────────

def home(env):
    return Path(env["HOME"])


def config_dir(env):
    return Path(env.get("XDG_CONFIG_HOME") or home(env) / ".config") / "zen-webapps"


def data_dir(env):
    return Path(env.get("XDG_DATA_HOME") or home(env) / ".local/share")


def apps_file(env):
    return config_dir(env) / "apps.json"


def icons_dir(env):
    return data_dir(env) / "zen-webapps/icons"


def desktop_dir(env):
    return data_dir(env) / "applications"


def read(path):
    return path.read_text() if path.exists() else ""


# ── apps.json (pure edits) ──────────────────────────────────────────────────

def slugify(name):
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


def host(url):
    return urlsplit(url).hostname


def add_app(apps, slug, name, url, icon=None):
    if re.search(r"[\x00-\x1f\x7f]", name + url):   # a newline would inject keys (Exec=…) into the .desktop file
        raise ValueError("name/url contain control characters")
    if urlsplit(url).scheme not in ("http", "https") or not host(url):
        raise ValueError(f"not an http(s) url: {url}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise ValueError(f"bad slug {slug!r} (lowercase letters, digits, dashes)")
    app = {"slug": slug, "name": name, "url": url} | ({"icon": str(icon)} if icon else {})
    return sorted([a for a in apps if a["slug"] != slug] + [app], key=lambda a: a["slug"])


def remove_app(apps, slug):
    if slug not in {a["slug"] for a in apps}:
        raise KeyError(slug)
    return [a for a in apps if a["slug"] != slug]


def load_apps(env):
    return json.loads(read(apps_file(env)) or "[]")


def save_apps(env, apps):
    write_if_changed(apps_file(env), json.dumps(apps, indent=1) + "\n")


# ── registry ────────────────────────────────────────────────────────────────

def app_id(slug):
    return str(uuid.uuid5(NAMESPACE, slug))


def entry(a):
    return {"id": app_id(a["slug"]), "scopes": [{"hostname": host(a["url"])}], "userContextId": 0,
            "startUrl": a["url"], "name": a["name"], "shortcutRelativePath": f"webapp-{a['slug']}.desktop"}


def merged(old, apps):
    """keep the user's own taskbar tabs; replace managed (webapp-*) ones; drop unpinned strays (no shortcut) whose host
    collides with one of ours, else Firefox may route our host into the stray"""
    hosts = {host(a["url"]) for a in apps}
    managed = lambda t: t.get("shortcutRelativePath", "").startswith("webapp-")
    stray = lambda t: "shortcutRelativePath" not in t and {s.get("hostname") for s in t.get("scopes", [])} & hosts
    return [t for t in old if not managed(t) and not stray(t)] + [entry(a) for a in apps]


def registry_path(prof):
    return prof / "taskbartabs/taskbartabs.json"


def registry_tabs(prof):
    return json.loads(read(registry_path(prof)) or '{"taskbarTabs": []}').get("taskbarTabs", [])


# ── userChrome.css + user.js (pure text merges) ─────────────────────────────

BLOCK = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)


def merge_block(text, css):
    """our css between markers; replaced in place if present, else appended. User content untouched."""
    block = f"{BEGIN}\n{css.strip()}\n{END}\n"
    if BLOCK.search(text):
        return BLOCK.sub(lambda _: block, text, count=1)
    sep = "" if not text or text.endswith("\n\n") else "\n" if text.endswith("\n") else "\n\n"
    return text + sep + block


def unblock(text):
    """inverse of merge_block on a file that had none before"""
    return re.sub(r"\n?" + BLOCK.pattern, "", text, flags=re.S)


def add_prefs(text):
    """append missing prefs; an existing user_pref line for one (any value) is the user's call → left alone"""
    missing = [p for p in PREFS if f'user_pref("{p}"' not in text]
    lines = "".join(f'user_pref("{p}", true); // {PREFS[p]} (zen-webapp)\n' for p in missing)
    return text + ("\n" if text and not text.endswith("\n") and lines else "") + lines


def prefs_active(prof):
    """prefs.js is Firefox's own dump: the pref is live only once Zen has started with our user.js"""
    return f'user_pref("{next(iter(PREFS))}", true)' in read(prof / "prefs.js")


def profile_plan(prof, apps, css):
    """{path: wanted text} for everything sync writes into the profile"""
    tabs = merged(registry_tabs(prof), apps)
    return {registry_path(prof): json.dumps({"version": 1, "taskbarTabs": tabs}, indent=1) + "\n",
            prof / "chrome/userChrome.css": merge_block(read(prof / "chrome/userChrome.css"), css),
            prof / "user.js": add_prefs(read(prof / "user.js"))}


def pending(plan):
    return [p for p, text in plan.items() if read(p) != text or not p.exists()]


def write_if_changed(path, text):
    # plain files only: the flatpak sandbox can't follow symlinks out of it → copy, never link
    if path.exists() and read(path) == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return True


# ── desktop files + icons ───────────────────────────────────────────────────

def exec_quote(arg):
    """Desktop Entry spec Exec quoting (then the spec's string-level backslash escape)"""
    s = str(arg).replace("%", "%%")
    if not re.search(r'[\s"\'\\><~|&;$*?#()`]', s):
        return s
    inner = re.sub(r'(["`$\\])', r"\\\1", s)
    return '"' + inner.replace("\\", "\\\\") + '"'


def desktop_entry(a, exe, icon):
    lines = ["[Desktop Entry]", "Type=Application", f"Name={a['name']}", f"Comment={a['url']}",
             f"Exec={exec_quote(exe)} launch {a['slug']}", *([f"Icon={icon}"] if icon else []),
             f"StartupWMClass=webapp-{a['slug']}", "Categories=Network;", "Terminal=false", MARK]
    return "\n".join(lines) + "\n"


def desktop_path(env, slug):
    return desktop_dir(env) / f"webapp-{slug}.desktop"


def sync_desktop(env, apps, exe):
    """write ours, remove our stale ones; returns changed slugs"""
    wanted = {desktop_path(env, a["slug"]): desktop_entry(a, exe, a.get("icon")) for a in apps}
    stale = [p for p in desktop_dir(env).glob("webapp-*.desktop") if p not in wanted and MARK in read(p).splitlines()] \
        if desktop_dir(env).exists() else []
    for p in stale:
        p.unlink()
    return [p.stem for p, t in wanted.items() if write_if_changed(p, t)] + [p.stem for p in stale]


def fetch_url(url):
    with urlopen(Request(url, headers={"User-Agent": "zen-webapp"}), timeout=10) as r:
        return r.read()


def get_icon(env, slug, url, icon, fetch, err):
    """icon = None | 'auto' | path → stored icon path or None (network optional: failure just warns)"""
    if not icon:
        return None
    if icon == "auto":
        try:
            data = fetch(ICON_URL.format(host(url)))
        except Exception as e:  # any network/HTTP failure → no icon
            data, why = None, e
        else:
            why = "empty response"
        if not data:
            print(f"zen-webapp: warning: no icon fetched for {host(url)} ({why}); continuing without", file=err)
            return None
        dest = icons_dir(env) / f"{slug}.ico"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest
    src = Path(icon).expanduser()
    dest = icons_dir(env) / f"{slug}{src.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest


# ── zen detection ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Zen:
    kind: str   # flatpak | native
    root: Path  # dir holding profiles.ini
    cmd: list   # argv prefix that launches it


def find_zen(env, which=shutil.which, flatpak_system=Path("/var/lib/flatpak")):
    """flatpak (user or system install; profile always under ~/.var/app) first, then native (binary on PATH)"""
    sandbox = home(env) / ".var/app" / FLATPAK_APP
    installs = [data_dir(env) / "flatpak/app" / FLATPAK_APP, flatpak_system / "app" / FLATPAK_APP, sandbox]
    if any(p.exists() for p in installs):
        return Zen("flatpak", sandbox / ".zen", ["flatpak", "run", FLATPAK_APP])
    binary = next((b for b in (which(n, path=env.get("PATH")) for n in NATIVE_BINS) if b), None)
    if binary:
        roots = [home(env) / ".zen", config_dir(env).parent / "zen"]
        return Zen("native", next((r for r in roots if (r / "profiles.ini").exists()), roots[0]), [binary])
    return None


def profile(root):
    """the profile Zen launches: profiles.ini [Install…] Default=, else [Profile*] Default=1"""
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    ini.read(root / "profiles.ini")
    install = [ini[s]["Default"] for s in ini.sections() if s.startswith("Install") and "Default" in ini[s]]
    if install:
        return root / install[0]  # absolute Default= stays absolute (Path join)
    for s in ini.sections():
        if s.startswith("Profile") and ini[s].get("Default") == "1" and "Path" in ini[s]:
            return root / ini[s]["Path"] if ini[s].get("IsRelative", "1") == "1" else Path(ini[s]["Path"])
    return None


def proc_cmdlines():
    out = []
    for p in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            out.append(p.read_bytes().decode(errors="replace").split("\0")[:-1])
        except OSError:  # raced exit / permission
            pass
    return out


def is_running(zen, procs):
    """anchored on argv[0]: unanchored matches hit profile paths in other argv (ssh, editors, this tool). Never pkill."""
    if zen.kind == "flatpak":  # the sandboxed main process, whatever its flags; content processes don't count
        return any(c and c[0] == "/app/zen/zen" and "-contentproc" not in c for c in procs())
    return any(c and Path(c[0]).name in NATIVE_BINS + ("zen-bin",) for c in procs())


# ── commands ────────────────────────────────────────────────────────────────

class Fail(Exception):
    pass


def locate(ctx):
    zen = find_zen(ctx.env, flatpak_system=ctx.flatpak_system)
    if not zen:
        raise Fail("Zen not found (flatpak app.zen_browser.zen, or zen/zen-browser/zen-beta on PATH)")
    prof = profile(zen.root)
    if not prof:
        raise Fail(f"no Zen profile in {zen.root} (start Zen once)")
    return zen, prof


def cmd_sync(ctx):
    apps = load_apps(ctx.env)
    desk = sync_desktop(ctx.env, apps, ctx.exe)
    zen, prof = locate(ctx)
    if is_running(zen, ctx.procs):
        todo = pending(profile_plan(prof, apps, CSS.read_text()))
        ctx.say(f"desktop files: {', '.join(desk) or 'up to date'}")
        if todo:
            ctx.say("Zen running → profile sync deferred (Zen rewrites its registry on exit). "
                    "Quit Zen, then `zen-webapp sync` (or launch an app while Zen is closed).")
        return 0
    plan = profile_plan(prof, apps, CSS.read_text())
    changed = [p.name for p, t in plan.items() if write_if_changed(p, t)]
    ctx.say(f"synced: {', '.join(changed + desk) or 'nothing'}")
    if not prefs_active(prof):
        ctx.say("note: prefs set in user.js → restart Zen once (or just start it) so web apps open as app windows")
    return 0


def cmd_add(ctx, a):
    slug = a.slug or slugify(a.name)
    add_app([], slug, a.name, a.url)   # validate slug/name/url BEFORE anything is written (the slug names the icon file)
    icon = get_icon(ctx.env, slug, a.url, a.icon, ctx.fetch, ctx.err) if a.icon else None
    save_apps(ctx.env, add_app(load_apps(ctx.env), slug, a.name, a.url, icon))
    ctx.say(f"added {slug} → {a.url}")
    return cmd_sync(ctx)


def cmd_remove(ctx, a):
    apps = load_apps(ctx.env)
    gone = next((x for x in apps if x["slug"] == a.slug), None)
    if not gone:
        raise Fail(f"unknown app {a.slug!r} (see zen-webapp list)")
    save_apps(ctx.env, remove_app(apps, a.slug))
    icon = Path(gone.get("icon", "")) if gone and gone.get("icon") else None
    if icon and icon.parent == icons_dir(ctx.env) and icon.exists():
        icon.unlink()
    ctx.say(f"removed {a.slug}")
    return cmd_sync(ctx)


def cmd_list(ctx):
    apps = load_apps(ctx.env)
    for x in apps:
        ctx.say(f"{x['slug']:<16} {x['name']:<20} {x['url']}")
    if not apps:
        ctx.say("no web apps (zen-webapp add NAME URL)")
    return 0


def cmd_launch(ctx, a):
    app = next((x for x in load_apps(ctx.env) if x["slug"] == a.slug), None)
    if not app:
        raise Fail(f"unknown app {a.slug!r} (see zen-webapp list)")
    zen, prof = locate(ctx)
    if not is_running(zen, ctx.procs):
        cmd_sync(ctx.quiet())
    elif not any(t["id"] == app_id(app["slug"]) for t in registry_tabs(prof)):
        print(f"zen-webapp: {app['name']} not registered yet (Zen running) → generic window/icon. "
              "Fix: quit Zen, `zen-webapp sync`, restart Zen.", file=ctx.err)
    # -taskbar-tab works as a remote command into a running Zen too
    ctx.execvp(zen.cmd[0], zen.cmd + ["-taskbar-tab", app_id(app["slug"]), "-new-window", app["url"], "-container", "0"])
    return 0


def cmd_doctor(ctx):
    zen = find_zen(ctx.env, flatpak_system=ctx.flatpak_system)
    row = lambda k, v: ctx.say(f"{k:<11}{v}")
    if not zen:
        row("zen", "not found (install the app.zen_browser.zen flatpak, or put zen on PATH)")
        return 1
    row("zen", f"{zen.kind} ({' '.join(zen.cmd)})")
    prof = profile(zen.root)
    if not prof:
        row("profile", f"not found in {zen.root} (start Zen once)")
        return 1
    apps = load_apps(ctx.env)
    ours = {t["id"] for t in registry_tabs(prof)}
    row("profile", prof)
    row("apps", f"{len(apps)} in {apps_file(ctx.env)}")
    row("registry", f"{sum(app_id(x['slug']) in ours for x in apps)}/{len(apps)} apps registered")
    row("userChrome", "installed" if BEGIN in read(prof / "chrome/userChrome.css") else "missing")
    in_userjs = all(f'user_pref("{p}"' in read(prof / "user.js") for p in PREFS)
    row("prefs", "active" if prefs_active(prof) else
        f"{'in user.js' if in_userjs else 'missing'}, not active yet → restart Zen once")
    up = is_running(zen, ctx.procs)
    row("zen state", "running" if up else "not running")
    todo = pending(profile_plan(prof, apps, CSS.read_text()))
    if todo:
        row("pending", ", ".join(p.name for p in todo) + (" (applied once Zen is closed + `zen-webapp sync`)" if up
                                                          else " → run `zen-webapp sync`"))
    return 0


@dataclass
class Ctx:
    env: dict
    procs: object
    execvp: object
    fetch: object
    out: object
    err: object
    flatpak_system: Path
    exe: Path

    def say(self, msg):
        print(msg, file=self.out)

    def quiet(self):
        return Ctx(**{**self.__dict__, "out": open(os.devnull, "w")})


def parser():
    p = argparse.ArgumentParser(prog="zen-webapp", description="web apps as chromeless Zen windows (Taskbar Tabs)")
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="add (or update) a web app")
    add.add_argument("name")
    add.add_argument("url")
    add.add_argument("--slug", help="id used for files + window class (default: from NAME)")
    add.add_argument("--icon", help="image path, or 'auto' to fetch the site's favicon")
    sub.add_parser("remove", help="remove a web app").add_argument("slug")
    sub.add_parser("list", help="list web apps")
    sub.add_parser("launch", help="open a web app window").add_argument("slug")
    sub.add_parser("sync", help="write desktop files + Zen profile (profile part only while Zen is closed)")
    sub.add_parser("doctor", help="show setup state and what is pending")
    return p


def main(argv, env=os.environ, procs=proc_cmdlines, execvp=os.execvp, fetch=fetch_url, out=sys.stdout,
         err=sys.stderr, flatpak_system=Path("/var/lib/flatpak"), exe=EXE):
    a = parser().parse_args(argv)
    ctx = Ctx(dict(env), procs, execvp, fetch, out, err, flatpak_system, exe)
    run = {"add": lambda: cmd_add(ctx, a), "remove": lambda: cmd_remove(ctx, a), "list": lambda: cmd_list(ctx),
           "launch": lambda: cmd_launch(ctx, a), "sync": lambda: cmd_sync(ctx), "doctor": lambda: cmd_doctor(ctx)}
    try:
        return run[a.cmd]()
    except (Fail, ValueError) as e:
        print(f"zen-webapp: {e}", file=err)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
