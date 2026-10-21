# Liquid Glass site styles

Glass Mode renders websites as translucent "liquid glass" over the blurred desktop (Zen + Hyprland blur), one shared design
system for every site, verified by a headless test suite (`glasslab`).

## Layout

| path | role |
|---|---|
| `styles/shared/glass.css` | **single source of truth**: tiers, alphas, colours, fills, text, status, paper, reduced-transparency |
| `styles/shared/gm3.css` | Google Material 3 token map, shared by Google apps (Calendar, Gmail, …) |
| `styles/websites/<host>.css` | per site: maps the site's own tokens/regions onto glass tiers. Nothing else |
| `data/ContentScripts.json` | site registry: `matches` (unanchored RegExp, first hit wins), `css`, optional `"glass": "dark"` (forced mode), `"glassUnless"` (selector on `<html>`: those pages keep auto, e.g. Linear app vs its dark-only marketing site) |
| `src/main/transparent-zen.ts` | sets `:root[data-tz-glass=dark\|light]` (auto = `prefers-color-scheme`) and `--tz-glass-alpha` (popup slider) |
| `styles/shared/auto-glass.css` + `src/main/modules/autoglass/` | auto glass: on-the-fly tiers for sites without a style (beta) |
| `tools/glasslab/` | test suite, explorer, discovery, `add` pipeline, showcase + site builder (`./glasslab …`), `screens.json`, `baseline.json`, JS `probes/` |
| `webapp/` | `zen-webapp`: web apps as chromeless Zen windows (Firefox Taskbar Tabs) |

## Design rules (Apple Liquid Glass, adapted)

1. **Two layers.** Glass is the navigation layer (sidebars, top bars, menus). Content (lists, reading panes, grids) sits on a near-solid material.
2. **Fixed blur → floors.** Apple's glass adapts to what's behind it; a compositor blur can't, so every text-bearing tier has a readability floor.
3. **Tiers, not one-offs.** Site files map onto tiers; they never invent an alpha or a colour.
4. **No glass on glass.** Panes are compensated so stacked layers land on their tier's total opacity; controls use thin fills.
5. **Solid text.** Primary / secondary / tertiary colours; selection = accent tint; status = accessible system colours.
6. **User content on paper.** HTML email and similar keep their own colours on `--g-paper`.
7. **Dark-only apps stay dark** (`"glass": "dark"` in the registry).
8. **If you restyle a control's fill, you own its label colour**; never recolour filled buttons you didn't re-fill.

## Tiers (`s` = slider 0.10–0.90)

| token | tier | dark | light |
|---|---|---|---|
| `--g-window` | page backdrop | `s` | `s` |
| `--g-frame` | app shell, sidebars, top bars (default `body`) | `.50 → .92` | `.65 → .92` |
| `--g-content` | pane inside the frame (compensated) | total `.78 → .96` | total `.80 → .96` |
| `--g-content-abs` | content tier, absolute (content-first `--g-body`) | same total | same total |
| `--g-popover` | menus, dialogs, tooltips (+ `--g-blur`) | `.85 → .96` | `.80 → .96` |

Tiers run linearly from their readability floor (slider 10 %) to their cap (90 %), so every slider step changes every
tier. (Until 2026-10-12 they were `clamp(floor, s + offset, cap)`, which left light mode flat below ~65 %.)
| `--g-fill` / `-hover` / `-selected` | rows, controls | white .05 / .07, accent .24 | white frost .55 / .72, accent .10 |
| `--g-paper` | user content with own colours | `rgba(250,250,252,.97)` | same |
| `--g-fg` / `-2` / `-3` | text | `#f2f2f5 / #dfdfe3 / #a8a8b0` | `#1c1c1e / #333338 / #55555c` |

Also `--g-line(-strong)`, `--g-accent`, `--g-red/orange/green/blue/purple`, `--g-scrim`, `--g-shadow`, `--g-highlight`,
`--g-radius-pane/card`, `--g-pad-card`. `--g-body` picks the body tint (default frame; content-first sites:
`var(--g-content-abs)`; sites that suppress body backgrounds: `transparent` + tint their shell).

## Adding a site

```sh
nix-shell                                   # node + python deps (or let ./glasslab enter it for you)
./glasslab wallpapers ~/Pictures/wallpapers  # once (optional): backdrops + contrast bounds from your own wallpapers
./glasslab add "Linear" https://linear.app/team/inbox            # the whole pipeline, one command
./glasslab add "Linear" https://linear.app/team/inbox --agent    # + agent loop on the failures
```

`add` = `new-site` (below) → build → `test` (screens + hidden UI) → `~/.cache/glasslab/add/<site>/report.md` (what to fix,
worst first). With `--agent`, an LLM (`GLASSLAB_AGENT`, default Claude Code) edits **only** the site's CSS from a fixed
prompt (these rules + current CSS + report); every round is re-tested and kept only if the score improves, else reverted,
and anything else it touched is restored. Deterministic core, monotone loop. CI does the same for public pages when a
maintainer labels a site request `add-site` (`.github/workflows/add-site.yml` → pull request).

`new-site` opens the page headless with your Zen cookies (log in to the site in Zen first), then:

1. **Discovers causally** what paints the page: each candidate design token is set to a sentinel colour inline and only
   counts if the element actually changes (equal values aren't proof; Gmail *looks* GM3 but hard-codes).
2. **Scaffolds** `styles/websites/<host>.css`: driving tokens mapped to tiers (largest pane → content, narrow tall →
   frame, names → popover/fills/text roles), token scope from where the site redefines tokens, and `TODO` blocks for
   hard-coded leftovers. A token-less site gets the *neutralise → re-tier by role → text* template.
3. **Registers** the site (`^https?://(www\.)?host/`) and adds a test screen to `screens.json`.

Then iterate:

```sh
npm run build && ./glasslab test linear     # look at the run's sheet-*.jpg too, not only the numbers
./glasslab discover https://linear.app/…    # any time a screen shows the site's own colours
./glasslab test --save-baseline linear      # when it passes: numbers-only baseline (safe to commit)
./glasslab test --compare                   # before committing any shared change: no regressions anywhere
```

Add more screens per site (list, detail, dialog, settings) — each new screen catches new surfaces.
Keep `act` scripts **read-only** (never send, archive, mark read; open only already-read items).

Selector preference when no token exists: ARIA role → id → `data-testid` → long-stable classes (Gmail `zA/zE/a3s`) →
semantic framework classes (Encore `encore-text-*`). Never hashed classes.

## Test suite

Two halves: **pytest** (`python3 -m pytest`; `-m "not e2e"` = pure maths, `-m e2e` = fixture pages in a real browser,
`GLASSLAB_BROWSER=firefox` without Zen; CI runs both) proves the lab and the extension; **`./glasslab test`** measures
real sites.

`./glasslab test [FILTER]` — every screen × dark/light × slider 10 / 45 / 90 %:

- **Capture**: the page over pure black and pure white → exact per-pixel colour and alpha → composited offline onto the
  blurred wallpapers (`sheet-<screen>.jpg`, `shots/`). CSP-proof (no backdrop injected into the page).
- **Contrast**: every visible text run, APCA through its real paint stack (incl. covering pseudo-elements) over the
  darkest and brightest blurred-wallpaper patch (`wallpapers` bounds, p5/p95). Target: Lc 75 body · 60 labels and
  controls · 45 large text, relaxed to the site's **native** contrast ×0.9 where its own design is lower — glass may
  never read worse than the original site. Pass ≥ 90 % of characters.
- **Surface unity**: topmost painted surface on a 20×14 grid must be a `glass.css` tier colour. Pass ≥ 90 %.
- **Text unity**: neutral (low-chroma) text must be a shared foreground. Pass ≥ 85 %.
- **Exemptions** (reported, not scored): text on site data colours (calendar chips, labels), images/gradients, accent
  fills — **void if glass changed the text's colour**; a screen fails if > 10 % of its text is exempted for images.
- Native twins are matched by selector + text + position. Results: `~/.cache/glasslab/runs/<time>/{summary.md,results.json}`
  (local: contains page text). `./glasslab report` → local HTML report with galleries. Never publish runs/reports.

- **Hidden UI** (`explore.py`, after each screen, default slider, every mode): finds controls that reveal UI
  (`aria-haspopup`, `aria-expanded=false`, comboboxes, search fields), activates each with real input (BiDi), diffs what
  became visible, and scores each floating layer like a screen + **opacity**: a layer over page text needs ≥ 0.80
  (popover tier) or the page bleeds through; a drawer over clear glass may stay thin. Read-only by construction: never
  navigation links, submit buttons, or labels matching `DANGER` (send, delete, archive, buy, sign out, …); search fields
  get typed text, never Enter. Restores via Escape → re-clicking an expanded toggle → blur → reload. Rows
  `<screen>~<state>.<mode>.45`.
- **Glass share**: share of the window where the desktop shows through (catches "styled but still opaque").
- `--no-explore` skips hidden UI; screens with `"auto": true` measure auto glass on sites without a style (benchmark).

Exit code ≠ 0 on any failure at the default slider or any regression (`--compare`). Extremes are reported.

Debugging a failing state: `python3 -m tools.glasslab.inspect_layer URL "label regex" [dark|light]` dumps the layer's
element chain with computed paint; `--gradients URL` and `--ancestry URL SELECTOR` find hard-coded fades and scopes.

## Auto glass (sites without a style)

`src/main/modules/autoglass/`: `classify.ts` (pure, `npm run test:unit`) decides, `engine.ts` measures and marks
(`data-tz-tier`, `data-tz-ink`), `styles/shared/auto-glass.css` maps marks onto the same tiers. Surfaces: page/full-bleed/
bars/sidebars → frame (root tint), panes and cards on the page → content, floating (popup role, top layer, positioned +
shadow/z-index) → popover, small neutral → fill, translucent full-screen → scrim, chromatic → kept (brand, chips, data).
Text: neutral colours ranked by APCA distance from the site's own page colour → `--g-fg/-2/-3` (frame text one rank
stronger; tertiary only ≥ 24px); chromatic text → status ink by hue; text on kept surfaces untouched. Content-first pages
(most text without a pane) take the content tint. One pass, then mutated subtrees only, + two re-scans for UI shown by
style changes. Design notes: `docs/research/auto-glass-algorithm.md`.

## Showcase + site

`./glasslab shots` (beauty shots: one window centred on an owned procedural wallpaper, compositor blur behind it;
private screens — `"private": [selectors]` — scrambled in-page first, iframes covered) → `site/shots/`.
`./glasslab shots --all` → every screen + hidden-UI state as tiles in `site/tests/`. `./glasslab site [--run RUN]` →
`site/index.html` + the README sites table from the registry, `screens.json`, baseline numbers (never page text).

## Gotchas (each cost an evening)

- Google pages enforce Trusted Types + CSP: inject nothing as HTML; probes use CSSOM only.
- Google redefines GM3 tokens on inner elements → GM3 overrides need `:root, :root *`. GM3 uses *surface* and *inverse*
  tokens as label colours on chips → inline-coloured subtrees restore Google's light tokens (calendar.google.css).
- Some sites suppress `body` backgrounds (YouTube) → `--g-body: transparent`, tint the app shell instead.
- `:root *` custom-property blocks cost memory on huge DOMs: scope tokens where the site declares them (`discover`
  › redefinedAt; Reader: `:root, body, #document-text-content`).
- Spotify paints text from hashed classes (no tokens) → Encore semantic classes; forced dark.
- Cloudflare-protected sites (claude.ai) may serve a bot check to the headless lab; open the site in Zen to refresh
  its clearance cookie, then rerun.
- Material state layers are full-colour boxes (or `::before`) at 8 % opacity: probes multiply element + ancestor
  opacity, else text measures Lc 0.
- Google's popup menus have no role (`.vH6rvf[jsname=xl07Ob]`, positioned + shadow): neutralise rules must exempt them.
- The Google apps launcher is a cross-origin iframe (`ogs.google.com`): the manifest runs the extension in those frames
  only; probes can't see inside — inspect via a BiDi child-frame context.
- The lab's black/white backdrop sits UNDER `<html>`'s own paint (auto glass tints the root), and upstream's 250 ms root
  background transition is suspended while capturing — else probes read a mid-fade colour.
- Lab limits (know them when reading numbers): headless Gecko doesn't render `backdrop-filter` (popover shots show the
  page beneath unblurred; real Zen blurs it); the lab profile prefers the DARK site theme (`ui.systemUsesDarkTheme`), so
  "light" runs are light glass over a site's dark theme — check light glass over the light theme by hand; cross-origin
  iframes are reported `unmeasured`; WhatsApp keeps its session in IndexedDB (lab can't log in); some apps create data
  just by being opened (NotebookLM made an empty notebook) — keep screens to pages that only display.
- Sites that follow `prefers-color-scheme` render dark in the lab by default: `"scheme": "light"` on a screen runs it in
  a light-theme session (one browser session per scheme). Test both when the site has its own light/dark theme.
- Logins kept on another machine, or apps that keep the session in IndexedDB/localStorage (Linear): copy that profile's
  `cookies.sqlite` + `storage/default/<origin>` into a dir and run with `GLASSLAB_LOGINS=dir` (merged into the lab profile).
  Public pages of such an app get `"test_logged_out": [domain]` (cookies deleted, run last in the session).
- Linear's app paints from a runtime theme engine (`.theme-provider-<hash>` → StyleX `--sx-<hash>` vars) plus inline
  dynamic styles; `discover` misses vars that feed relative colours, so its site file names vars from a full causal map
  (every var → sentinel on every provider, diff all elements) — see the comment in `linear.app.css`.
- SPAs that assign `html.className` (Discord) wipe the extension's root classes: `src/main/modules/RootMarks.ts` re-adds them.
- Content scripts are classic scripts: a shared chunk import kills them (and the background, unless it's a module) —
  `tests/test_build.py` guards it.
