# zen-webapp

Turn websites into **web apps**: their own chromeless Zen Browser windows, with their own launcher entry, taskbar icon
and window class. No sidebar, no URL bar, just the page. With Transparent Web installed the page's liquid glass shows
straight through to your desktop.

Web apps share your normal Zen profile: same logins, extensions and settings.

## Install

Needs Linux, [Zen Browser](https://zen-browser.app) 1.23+ (Flatpak or native) and Python 3. No other dependencies.

1. Get the tool: clone this repo (or copy the `webapp/` folder somewhere permanent).
2. **Quit Zen**, then add an app:
   ```sh
   ./webapp/zen-webapp add "Hacker News" https://news.ycombinator.com --icon auto
   ```
3. Start Zen once (this loads the new prefs), then open "Hacker News" from your app launcher.

Check everything with `./webapp/zen-webapp doctor`.

Tip: put it on your PATH, e.g. `ln -s "$PWD/webapp/zen-webapp" ~/.local/bin/`.

## Commands

| command | does |
|---|---|
| `zen-webapp add NAME URL [--slug S] [--icon PATH\|auto]` | add or update an app, then sync |
| `zen-webapp remove SLUG` | remove an app, then sync |
| `zen-webapp list` | list your apps |
| `zen-webapp launch SLUG` | open the app window (what the launcher entry runs) |
| `zen-webapp sync` | write launcher entries + Zen profile files |
| `zen-webapp doctor` | show Zen install, profile, prefs, what is registered and what is pending |

`--slug` defaults to the name in lowercase-dashes (`Hacker News` → `hacker-news`). `--icon auto` downloads the site's
favicon from DuckDuckGo's icon service; if that fails the app just has no icon.

**Zen must be closed for profile changes.** Zen keeps its web-app list in memory and overwrites the file when it exits,
so while Zen runs `sync` only updates launcher entries and tells you what is pending. Quit Zen and run `zen-webapp sync`,
or simply launch any web app while Zen is closed (launch syncs first).

## How it works

Zen (like Firefox 157+) has a hidden feature, **Taskbar Tabs**: a site opened in a dedicated, minimal window.
`zen-webapp` drives it:

- **Your apps**: `~/.config/zen-webapps/apps.json` (`$XDG_CONFIG_HOME`), a list of `{slug, name, url}`.
- **Registry**: each app becomes an entry in `<profile>/taskbartabs/taskbartabs.json` with a fixed id
  (`uuid5` of the slug in a fixed namespace, so it never changes) and `shortcutRelativePath: webapp-<slug>.desktop`.
  That makes Zen give the window class `webapp-<slug>`, which matches the launcher entry, so docks/taskbars show the right
  icon and group windows. Your own taskbar tabs are kept.
- **Launcher entry**: `~/.local/share/applications/webapp-<slug>.desktop` (`$XDG_DATA_HOME`) running
  `zen-webapp launch <slug>` → `zen -taskbar-tab <id> -new-window <url> -container 0` (works into a running Zen too).
- **Prefs**: appended to `<profile>/user.js` once: `browser.taskbarTabs.enabled` (the feature) and
  `toolkit.legacyUserProfileCustomizations.stylesheets` (lets Zen load `userChrome.css`). Prefs you already set are left alone.
- **Styling**: [`userChrome.css`](userChrome.css) hides the toolbars and makes the window background transparent.
  Firefox renames these windows' root element, so Zen's own transparency rules miss them; this re-applies them. It is
  merged into `<profile>/chrome/userChrome.css` between `/* zen-webapp:begin */` and `/* zen-webapp:end */`; the rest of
  your file is never touched. Files are copied, not symlinked (the Flatpak sandbox can't follow symlinks out).

The profile is the one Zen starts with (`profiles.ini`: `[Install…] Default=`, else the profile with `Default=1`), found
under `~/.var/app/app.zen_browser.zen/.zen` (Flatpak) or `~/.zen` (native; binaries `zen`, `zen-browser`, `zen-beta`).

## Limitations

- **Linux only.** On Windows, Firefox exposes Taskbar Tabs in its own UI; untested with Zen there. macOS: untested.
- Taskbar Tabs is an experimental Firefox feature; a Zen update could change or remove it.
- One restart of Zen is needed after the first sync before the pref is active (`doctor` shows `prefs active`).
- Apps added while Zen is running open as plain windows (generic icon/class) until Zen has been closed and synced once.
- Uses the default profile only. Removing an app does not remove the userChrome block or prefs (harmless; delete the
  block between the markers by hand if you want).
