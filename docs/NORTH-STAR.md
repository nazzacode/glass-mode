# North star

**One click: paste a site → out comes a beautiful glass version of the WHOLE app, verified, shipped.**

Not the home page. Every page a user reaches and every layer they open (menus, modals, lanes, drawers, toasts), in
both glass modes, over any wallpaper. Nathan turns it on, says "perfect", never turns it off.

## What "verified" means (the bar every site passes before release)

1. **No leftover slabs.** Every big surface is a glass tier (`--g-*`). A Linear/Gmail panel colour that survives the
   remap (inline styles, JS-computed colours, gradients) is a fail, not an exemption. Only chip-sized data colours
   (labels, avatars, event chips) are exempt. One foreign element covering ≥ 2 % of the window fails the page, however
   good the average (a black box in an otherwise glass page is what people see).
2. **Text reads.** Every text run meets APCA targets over the darkest and brightest wallpaper, never worse than the
   site's own native contrast.
3. **Layers over content are blurred or solid.** A popup, menu, modal or sticky bar with page content under it is
   either frosted (`backdrop-filter` + popover tint) or opaque enough on its own. Text on text = fail.
4. **No veils.** A layer never frosts the whole viewport (modal wrappers, focus traps): only the panel is glass, the
   scrim stays a light dim.
5. **Whole app covered.** The lab crawls the site's own navigation (logged in, read-only) and opens every safe trigger
   on every page it reaches, not just hand-listed screens.
6. **Human taste.** Numbers are the floor. A/B votes and Nathan's eye decide thickness, blur, defaults.

## Pipeline (one click = all of this, unattended)

| stage | command | state |
|---|---|---|
| discover what paints the site (causal token test) | `glasslab discover` | works |
| scaffold style + registry + screen | `glasslab new-site` | works (registry insert order needs fixing) |
| agent improves the CSS against the lab report | `glasslab add --agent` | works on listed screens |
| **logged-in lab** (cookies + site storage from Nathan's Zen) | `lab.setup` | 2026-11-16 |
| **crawl** the app's own nav, measure every page + opened layer | `glasslab crawl` | 2026-11-16 |
| checks 1–5 on every page/state | `suite` / `explore` / probes | slab rule, blurred-or-solid, veil, animation settle: 2026-11-16 |
| A/B taste votes | `glasslab vote` | built, 0 votes |
| release + self-update | `npm run release` | works |
| in-browser "add this site" button → runs the above | — | not started |

## Known blind spots (fix in this order)

- Crawl doesn't yet open per-item views behind a click that isn't a link (issue peek panels, row expanders).
- Bot-walled sites (Cloudflare) can't be crawled headless → recorder captures from real use (`glasslab corpus`).
- Agent loop (`add --agent`) only sees listed screens → feed it crawl results.
- No in-browser button yet; today "one click" = one command.
