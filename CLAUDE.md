# Glass Mode — agent guide

Claude runs this project; Nathan checks in rarely. Start here, in order:
1. `docs/NORTH-STAR.md` — the goal (one click → whole app glassed + verified; then any site live) and the verified bar.
2. `tasks.md` — claims board + backlog. Claim before working; keep it current.
3. `docs/GLASS.md` — design system (glass tiers `--g-*`), lab (`./glasslab`), how to add a site.

## Loop
- Change a site style → `./glasslab crawl NAME URL --build` (whole app, logged in) or `./glasslab test FILTER --build`.
  Look at the renders; a green row is a floor, not proof.
- Ship small: CHANGELOG entry (plain words) → commit → `npm run release -- patch "notes"` (inside `nix-shell`; clean
  tracked tree). Installed copies self-update daily.
- Every change that works: commit + push same turn.

## Traps
- CRLF files: `glass.css`, `data/ContentScripts.json`, `styles/websites/linear.app.css`, `CHANGELOG.md` → python with
  `newline=''`, or Edit. A whole-file diff = you broke line endings.
- Inline JS colours (style attributes, `--x-*` vars) bypass token remaps → target them structurally; the slab rule finds them.
- `backdrop-filter` makes an element the containing block for `position:fixed` children (menus get clipped).
- Headless renders never show blur; judge blur from computed style.
- Nathan's own Zen: never drive it, don't restart it unasked (relaunch steals focus). Headless agent Zen / lab only.
- Browsing data, corpus renders, launch kit = private (`launch/`, `~/.cache/glasslab`): never commit or publish.
