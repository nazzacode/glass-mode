How to turn an arbitrary website into tiered liquid glass automatically, offline (generate a site file) and live (content script). Written 2026-10-12 for review. It is opinionated: each section ends in a decision you can veto. Sources are at the bottom.

## TL;DR

1. **Use one engine for both modes.** Offline is the live engine run in glasslab, with time to discover, open hidden UI and verify, then frozen into a site file. Hand-written site files become thin overrides on top of it.
2. **Rewrite stylesheets, not elements.** Take Dark Reader's skeleton: parse every sheet (`<style>`, `<link>` refetched when CORS blocks it, `@import`, adopted sheets, inline `style=`), type each colour by the property it paints, and replace it with a **role variable** (`background-color:#fff` → `var(--tzb-2)`). Retype custom properties by how they are used. New DOM then costs nothing, and the slider or a mode flip only rewrites the `:root` table.
3. **Assign tiers to surfaces, not colours.** A colour → colour function (Dark Reader, Force Dark) can't tell a white page from a white menu. A small **surface pass** classifies the few elements and rules that paint large or floating regions (window/frame/content/popover/fill/scrim/paper) from geometry, out-of-flow positioning, the top layer, ARIA roles and selector words. It writes them as `data-tz-tier` attributes or rule-level overrides.
4. **Map text by rank, not by inversion.** Group neutral text colours by APCA distance from the site's own base surface (1-D k-means, k ≤ 3) and map the groups to `--g-fg/-2/-3`. This works whatever the site's polarity. Tier floors already guarantee those three pass. Chromatic text keeps its hue and has its OKLCH lightness solved until it passes against the worst-case backdrop. **Text is remapped only if its backdrop was remapped** (GLASS.md rule 8, made mechanical).
5. **Mutations are cheap by construction.** Watch for new sheets and inline styles (incremental, hash-cached), plus newly visible out-of-flow, top-layer or role-bearing roots. Never re-walk the page. Budget: ≤ 2 ms/frame, ≤ 200 `getComputedStyle` calls per batch, the rest in idle time.

## The problem, decomposed

| sub-problem | why it's hard | what decides it |
|---|---|---|
| **Surface detection** | Paint is spread over wrappers. Half the `div`s with a background are invisible or redundant. Pseudo-elements paint too. | Grid hit-test (as `unity.js` does) + area + stacking |
| **Tier classification** | The same `#fff` is page, pane, card and menu. Tier is about *role*, not colour. | Geometry, flow, top layer, ARIA, selector words |
| **Colour/token remapping** | Hard-coded colours vs tokens. Primitives (`--gray-10`) are shared by unrelated roles. Gradients, shadows, SVG fills. | Property typing + causal tests |
| **Text legibility** | The backdrop is the user's wallpaper and changes. The compositor blur can't adapt, unlike Apple's. | Floors (already calibrated) + rank mapping + an OKLCH solve |
| **Dynamic content** | SPAs, infinite feeds, portals, CSS-in-JS injecting `<style>` at runtime | Sheet-level rewrite + targeted root checks |
| **Hidden UI states** | Menus, dialogs and hover states aren't in the DOM, or aren't visible, when you look | Classify **rules** as well as elements. In the lab, act scripts open them |
| **Performance** | Dark Reader on heavy pages; our upstream re-walks everything on every mutation | Do the work once per sheet; touch DOM rarely |

## Prior art, and what to steal from each

**Dark Reader, dynamic theme** ([blog](https://darkreader.org/blog/dynamic-theme/), [source](https://github.com/darkreader/darkreader/tree/main/src/inject/dynamic-theme)). This is the reference architecture for doing it live.
- *Rewrites CSS rules, not elements.* For every sheet it builds a modified copy. When `cssRules` throws a CORS `SecurityError` it refetches the text through the background script (`bgFetch`), keeps a `corsCopies` copy, and inlines `@import`s up to depth 32 ([style-manager.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/style-manager.ts)). **Steal it whole.**
- *Types variables by usage.* Each custom property gets a bitmask: BG / TEXT / BORDER / BG_IMG, inferred from the consuming property (`background-color` and `box-shadow` → bg, `color`/`fill`/`stroke` → text, `border*`/`outline*` → border). Ambiguous `background` is resolved by walking the `var()` reference graph. The engine then emits parallel `--darkreader-bg--x` / `--darkreader-text--x` variables, so a token used both as text and as bg gets two values ([variables.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/variables.ts)). **Steal it.** It is the live analogue of our causal discovery, and it is cheaper.
- *Adopted sheets and shadow DOM.* For each constructed sheet, an override sheet is inserted after it in `adoptedStyleSheets`, cached in a WeakMap ([adopted-style-manger.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/adopted-style-manger.ts)). A main-world proxy patches `insertRule`/`replace`/`replaceSync`, the `adoptedStyleSheets` setters and `attachShadow`, and signals the content script with DOM events ([stylesheet-proxy.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/stylesheet-proxy.ts)). **Steal it, but only the parts we need.** It is the only way to see CSS-in-JS `insertRule` calls and closed shadow roots.
- *Colour transform.* HSL lightness remap: bg L∈[0,.5]→[0,.4], light bg inverted toward the pole; fg pushed to L ≥ .55; neutrals take the pole's hue; hue hacks for yellow and blue ([modify-colors.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/modify-colors.ts)). **Don't steal it.** It is pointwise, so it has no notion of tier. The hue hacks are there because HSL lightness isn't perceptual. Use OKLCH.
- *Images.* Downscale to 32×32 and classify dark/light/transparent at 70 % of pixels; > 512² counts as large and is skipped ([image.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/image.ts)). **Steal it** for deciding whether a background image means "paper" or "leave alone".
- *Per-site fixes.* A crowdsourced `dynamic-theme-fixes` config exists because the automatic result is never perfect. The equivalent for us is the thin site override.

**Chromium Auto Dark / Force Dark** ([intent to experiment](https://groups.google.com/a/chromium.org/g/blink-dev/c/E29o9uJ8VRs/m/oKi03ed_BAAJ), [dark_mode_filter.h](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/platform/graphics/dark_mode_filter.h)). It works at *paint* time. Each paint op has a role (`kForeground, kListSymbol, kBackground, kSVG, kBorder, kSelection`). Foreground is inverted only below a brightness threshold, background only above one ([dark_mode_settings.h](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/platform/graphics/dark_mode_settings.h)). Borders are adjusted only if they stay readable against their background. Images are classified icon / separator / photo, first by size, then by a small ML model, and only icons get filtered. Developers opt out per element with `color-scheme: only`. **Steal three things:** (a) *role by property*, (b) *threshold polarity*: only touch colours that are on the wrong side, (c) *opt-out primitive*: our `data-tz-keep`. Even Google's version ships with known misclassifications. Expect ours to need overrides too.

**Stylus / userstyles** ([Catppuccin userstyles](https://userstyles.catppuccin.com/contributing/creating-userstyles/)). Still entirely hand-written: a LESS template, a palette library and per-site rules. The best ecosystem (Catppuccin) is "tokens + palette mixin + site map", which is exactly our GLASS.md design. **Lesson:** nobody auto-generates good themes. The scalable unit is a *shared palette with a thin per-site map*, and that map is the thing we should generate.

**Midnight Lizard** ([repo](https://github.com/Midnight-Lizard/Midnight-Lizard)). It walks computed styles per element with role-specific settings (bg, text, buttons, links, borders, images), and has a "simplified mode" for heavy sites. Per-element walking is the model our upstream `DynamicTransparency.ts` uses, and it is slow for the same reason. **Lesson: don't.**

**Apple materials / Liquid Glass** ([HIG Materials](https://developer.apple.com/design/human-interface-guidelines/materials), [NSVisualEffectView](https://developer.apple.com/documentation/appkit/nsvisualeffectview), [Glass.clear](https://developer.apple.com/documentation/swiftui/glass/clear), [WWDC25 design lab](https://developer.apple.com/forums/thread/791070)). Materials are named by *role*: titlebar, sidebar, headerView, menu, popover, sheet, contentBackground, windowBackground, underPageBackground. Apple says to pick by role, "not based on the apparent colors". Liquid Glass belongs to the navigation layer, never the content layer. Nested glass becomes a vibrant fill. Clear glass needs a dimming layer for legibility. Apple raised nav-bar opacity after beta 1 complaints ([Wikipedia](https://en.wikipedia.org/wiki/Liquid_Glass)). **Steal:** our tiers already *are* this hierarchy. The algorithm's job is only role detection. The role vocabulary (sidebar/header/menu/popover/sheet/content/under-page) is the label set for classification.

**UI recognition from pixels/DOM** ([Screen Recognition, Zhang et al. 2021](https://arxiv.org/abs/2101.04893)). Apple detects 13 element classes from pixels at 71 % mAP. They needed pixels because 59 % of screens had missing accessibility metadata. **Lesson:** ARIA is a strong signal when present and often absent. Treat roles as high-precision, low-recall evidence, and let geometry and flow do the rest. [Mozilla Readability](https://github.com/mozilla/readability) gives a cheap "main content" score (text density, link density) for the content tier when there's no `role=main`.

**Top layer / popover** ([web.dev dialog+popover](https://web.dev/articles/baseline-in-action-dialog-popover), [MDN Popover API](https://developer.mozilla.org/en-US/docs/Web/API/Popover_API), [MDN stacking context](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_positioned_layout/Stacking_context)). `dialog:modal`, `:popover-open` and `::backdrop` are free, certain popover signals with ready-made selectors. Most sites still use portals: a `div` appended to `body`, `position:absolute|fixed`, high z-index, shadow, radius. That pattern is the main heuristic.

**APCA** ([apca-w3](https://github.com/Myndex/apca-w3), [intro](https://github.com/Myndex/apca-introduction)). Lc 90 preferred / 75 min body, 60 labels, 45 large. Polarity-aware. We already use it. **Keep it as the verifier, not the generator.** The generator works in OKLCH, which is easier to solve in, and checks with APCA.

**LLM + verifier loops** ([Design2Code](https://arxiv.org/abs/2403.03163), [VisRefiner](https://arxiv.org/abs/2511.08195), [Amazon critic loop](https://cdn.amazon.science/e2/87/68ecc1e04ecc9e2e92bcd5fd3750/scipub-approval152129-45356067-visionguided-iterative-refinement-for-frontend-code-generation.pdf)). Render → compare → revise gains up to ~18 % over 3 rounds, but self-revision without a hard signal often degrades. **Lesson:** an LLM is useful only for the *residue* (naming a selector, picking a tier for a foreign surface), only with a numeric verifier (glasslab), and only with output constrained to `selector { prop: var(--g-*) }`.

## Recommended algorithm

### Data flow

```
sheets ──parse──► declarations[(rule, prop, value)] ──type──► colour slots (bg|text|border|shadow|fill/stroke|img)
                                                                      │
DOM sample (grid hit-test, ≤280 pts) ──► surfaces[] ──classify──► tier per surface/rule
                                                                      │
             palette: cluster slot colours (OKLab) → roles by rank ◄──┘
                                                                      │
             emit: :root role table  +  rewritten sheets  +  tier attrs/rules  +  keep-marks
                                                                      │
             verify (lab) / spot-check (live: visible text runs only)
```

### 1. Sheet pass (live and offline)

```
for sheet in all_sheets(document, shadowRoots, adopted):          # CORS → bgFetch text; hash → cache hit = skip
  for rule in walk(sheet):                                         # @media/@supports/@layer/@container recursed
    for (prop, val) in rule.style if is_colour_prop(prop):
      slot  = TYPE[prop]                                           # bg | text | border | shadow | svg
      state = pseudo_state(rule.selectorText)                      # :hover :active :focus [aria-selected] .active .selected
      if uses_var(val): record_usage(vars_in(val), slot); continue # rewrite the TOKEN, not this decl
      emit(rule, prop, f"var(--tz-{slot}-{palette.id(val, slot, state)})")
for token in custom_props: for slot in usage_bits(token): emit_root(f"--tz-{slot}--{token}", ...)
```

- **Group by `(rule, slot)`, not just by value.** If a rule sets *both* a chromatic background and a text colour (a `.btn-primary`), record it as a **pair**. If the bg is kept, the text is kept.
- **Pseudo-state from selectors** is free, strong evidence: `:hover` → `--g-fill-hover`, `[aria-selected=true]`/`.active`/`:checked` → `--g-fill-selected`, whatever the colour.
- **Gradients and `url()` backgrounds:** run the image classifier. Large/photo → keep (exempt). Subtle near-neutral gradient → treat as its average colour. Logo/icon → keep.
- **Inline `style=`** goes through the same function. Inline *background* colours on small elements are data colours (calendar chips): keep. The lab already exempts them.

### 2. Palette → roles (rank, not inversion)

Work in OKLab. Let **B** be the site's base surface: the colour with the largest painted area in the hit-test grid (usually html/body or the app shell).

- **Neutral backgrounds** (chroma < 0.03) are sorted by |ΔL| from B:
  - |ΔL| ≈ 0, area ≥ 50 % → `window` (body tint; GLASS.md handles it).
  - Small ΔL, large area → the tier given by the surface pass (frame/content). Default `--g-content`.
  - Small area → `--g-fill`. Raised (lighter than B in dark sites, or carrying a shadow) → `--g-card`.
  - States from selectors override all of these.
- **Chromatic backgrounds:** high chroma and small area → accent/data, keep the colour, and the paired text is kept. Large area (a brand header bar) → frame tier, tinted (open question 3).
- **Neutral text:** 1-D k-means (k ≤ 3) on APCA Lc(text, B), weighted by character count. Highest-contrast cluster → `--g-fg`, then `--g-fg-2`, then `--g-fg-3`. Polarity doesn't matter: a light site's `#222/#555/#888` and a dark site's `#eee/#aaa/#777` land in the same slots. This generalises the rank rule `discover.py` already uses for hard-coded text.
- **Chromatic text:** snap to the nearest status hue (red/orange/green/blue/purple) if the name or selector suggests status or link (`a`, `:visited`, `error|warning|success`). Otherwise keep hue and chroma and **solve L** in OKLCH by bisection until APCA meets the run's floor over *both* wallpaper bounds through the tier alpha. The tier is known, so the backdrop composite is known. Bounds come from `glasslab wallpapers` and ship as constants.
- **Borders:** rank by contrast → `--g-line` / `--g-line-strong`. **Shadows:** popovers → `--g-shadow`. Everything else drops to none (one material, no fake depth).

### 3. Surface pass (tier classification)

Candidates are the topmost painted element at each grid point (reuse `unity.js`), plus `:modal`, `:popover-open`, `[role=dialog|alertdialog|menu|listbox|tooltip]`, and `body > *` that is out of flow. Usually 10–40 elements. Features per surface: area share, edge contact (which viewport edges it touches), aspect, `position`, z-index or stacking-context root, `box-shadow`, radius, `overflow:auto` (scroll pane), ARIA role/landmark tag, Readability-ish text density, portal (direct body child), depth in the surface tree.

Rules, first match wins:

| tier | rule |
|---|---|
| **scrim** | fixed, ≥ 90 % viewport, translucent or dark, no text → `--g-scrim` |
| **popover** | top layer ∨ floating role ∨ (out-of-flow ∧ (shadow ∨ z ≥ 10 ∨ portal) ∧ area < 60 % ∧ ¬edge-bar) |
| **frame** | landmark `nav/header/aside/banner/complementary/toolbar` ∨ touches ≥ 3 edges with a thin dimension (sidebar/top bar) ∨ sticky edge bar |
| **content** | `main/article/[role=main]` ∨ top Readability candidate ∨ largest scroll container not touching 3 edges |
| **paper** | user content with its own colours: email bodies, `iframe[srcdoc]`, contenteditable documents with inline colours |
| **fill / card** | small surface nested in content; radius or border → fill; shadow or lighter → card |
| **window** | html/body and full-viewport wrappers at depth 0 → transparent; the body carries the tint |

**No glass on glass:** walk the surface tree top-down. A child whose tier ≤ its parent's becomes transparent. A content pane inside a frame uses the compensated `--g-content` (already in `glass.css`).

The output is `data-tz-tier=<tier>` on the element plus a static sheet `[data-tz-tier=content]{background-color:var(--g-content)!important}`. When the element matched a rule with a stable selector, the tier is *also* written onto that rule's slot so that later instances of it (the next menu) are correct before they're ever classified.

**Hidden states via rules.** Score every rule that is never visible in the sample: selector words (`menu|dropdown|popover|tooltip|modal|dialog|sheet|toast`) plus declarations (`position:absolute|fixed` + `z-index` + `box-shadow` / `max-height+overflow:auto`). A score ≥ 2 pre-assigns popover to that rule's bg slot. Offline, the act scripts open menus and dialogs and the element pass confirms or rejects each guess.

### 4. Text legibility pass

By construction, neutral text → `--g-fg*` and tier floors already pass in the lab. What's left: text on kept chips (exempt, as now), chromatic text (solved above), and text whose remapped backdrop came out wrong. Live: once settled, run a cheap `text.js` over **visible** runs only (cap 300). Each failure gets an inline override, `color` from the OKLCH solve. Offline: the full suite.

### 5. Mutation handling (live)

```
MutationObserver(childList, subtree, attributes: [style, class, open, popover, role, aria-expanded])
on batch (rAF-coalesced):
  new <style>/<link>/adopted change → sheet pass on that sheet only (hash cache)
  style attr with colour           → inline rewrite (same function)
  added roots: only the root, not descendants:
     if out-of-flow ∨ top-layer ∨ role∈floating ∨ body-child → classify (≤ 200 gCS calls / batch)
  toggle / dialog open events      → classify target
  class change: only on elements already known as latent surfaces
budget: 2 ms/frame foreground; spill to requestIdleCallback; never a full walk
```

Upstream re-walks the whole tree 100 ms after *any* mutation. That is the thing to kill. Sheet-level rewriting means new feed items, list rows and messages need no work at all.

### 6. Startup

At `document_start`: inject the generic base (`html, body` transparent, body frame tint, `color-scheme`), apply the cached role table and rewritten sheets for this origin if there is one (the cache *is* an auto site file), then run the sheet pass. The surface pass runs at DOMContentLoaded and again after the first idle. First visit may flash the site's opaque colours for one sheet pass. Accept it rather than hiding the page. The cache makes every later visit flash-free.

### 7. Offline mode = live engine + time + verifier

```
glasslab auto <url>:
  run engine in headless Zen (cookies) → role table, tier map
  causal discovery (existing) confirms tokens; override engine typing where they disagree
  act scripts: open each menu/dialog/screen → surface pass → confirm hidden-state guesses
  freeze → styles/websites/<host>.css:  token map + tier rules with stable selectors
           (ARIA → id → data-testid → long-stable class; never hashed)
  ./glasslab test → failures list (foreign surfaces + selectors, failing runs + Lc)
  optional LLM repair: input = failures + DOM excerpt; output grammar = selector{prop:var(--g-*)}
           accept iff suite score ↑ and --compare shows no regression; max 3 rounds
```

The lint rule from GLASS.md rule 3 is enforced mechanically: no literal colours or alphas in generated files.

## How it plugs into the test suite

The existing gates stay: contrast ≥ 90 % of characters, surface unity ≥ 90 %, text unity ≥ 85 %, exemptions void if glass recoloured them. Add:

1. **Glassiness:** share of grid points whose composited alpha is ≤ its tier target + .05. This catches the Substack failure (78–100 % opaque) that unity misses when the site's own colour happens to be near a tier.
2. **Tier accuracy:** hand-label each of the 14 screens once (`selector → tier`, ~20 lines each). Report a confusion matrix. Popover recall is the headline number.
3. **Auto vs hand:** run every screen with *auto only* (site file disabled) and record pass/fail and deltas. A hand file is justified only where auto fails. Goal: auto passes ≥ 10/14 screens at slider 45.
4. **Native fidelity:** mean ΔE_OK of kept chromatic fills (accent, chips) native vs glass. It should be ≈ 0, which proves we don't trample data colours.
5. **Perf:** in lab, time from `document_start` to first glass. Count long tasks > 50 ms. Measure ms of engine work per second while auto-scrolling a feed (Reddit, YouTube) for 20 s. Budget: < 5 % main-thread time.
6. **Stability:** run `test` twice. The tier map must be identical (determinism).

## Risks and open questions (yours to decide)

1. **Main-world injection.** Seeing `insertRule` (CSS-in-JS: Emotion, styled-components) and closed shadow roots needs Dark Reader's page-world proxy. It is invasive and fights CSP and Trusted Types. Proposal: ship without it, with a rAF poll of `sheet.cssRules.length` for known `<style>` tags, and add the proxy only if CSS-in-JS sites fail.
2. **Scope of auto.** Default-on for every site (opt-out list), or opt-in per site from the popup? Proposal: opt-in until the auto-vs-hand gate (metric 3) passes ≥ 10/14.
3. **Tinted glass.** Should a brand-coloured shell (YouTube red, GitHub dark blue) keep a low-chroma tint of its hue in `--g-rgb` for that site, or always neutral? Neutral is more Apple and easier to verify. Tint is more recognisable.
4. **Light-designed images on dark glass.** Logos and diagrams with dark ink on transparency become illegible. Options: paper backing for `img` with ≥ 10 % transparency classified as light-on-transparent (Dark Reader's classifier), or leave them alone. Proposal: paper backing, gated by `isTransparent ∧ isDark`.
5. **Canvas/WebGL apps** (Google Docs body, Figma, maps). Not fixable. Treat as paper and exempt. Accept it.
6. **Cross-origin CSS refetch** needs `<all_urls>` host permission and doubles CSS network on a cold cache. Fine for a personal build. Mention it if this goes upstream.
7. **iframes.** `all_frames: true` runs the engine per frame. Embedded third-party frames (ads, embeds) should probably get window tier only, with no text remap.
8. **LLM in the loop.** Offline only, never live. Worth it only for the residue after deterministic passes, and only behind the verifier. Decide whether Claude API cost per site is acceptable (it is small: a few thousand tokens × ≤ 3 rounds).
9. **Polarity mismatch with forced mode** (light site in dark glass). Rank mapping handles text. Content that embeds its own colours (code blocks, syntax highlighting) needs the chromatic-text solve on every token. Check it on GitHub first: it is the hardest case.
10. **Upstream divergence.** This replaces `DynamicTransparency.ts` wholesale. Keep the old one behind a setting for one release, or delete it?

## Sources

- Dark Reader: [dynamic theme announcement](https://darkreader.org/blog/dynamic-theme/) · [dynamic-theme source dir](https://github.com/darkreader/darkreader/tree/main/src/inject/dynamic-theme) · [variables.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/variables.ts) · [modify-colors.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/modify-colors.ts) · [style-manager.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/style-manager.ts) · [adopted-style-manger.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/adopted-style-manger.ts) · [stylesheet-proxy.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/stylesheet-proxy.ts) · [image.ts](https://github.com/darkreader/darkreader/blob/main/src/inject/dynamic-theme/image.ts)
- Chromium: [Auto Dark Mode intent to experiment](https://groups.google.com/a/chromium.org/g/blink-dev/c/E29o9uJ8VRs/m/oKi03ed_BAAJ) · [dark_mode_filter.h](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/platform/graphics/dark_mode_filter.h) · [dark_mode_filter.cc](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/platform/graphics/dark_mode_filter.cc) · [dark_mode_settings.h](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/platform/graphics/dark_mode_settings.h) · [force-dark flag modes](https://disciple.tools/news/disciple-tools-dark-mode/)
- Apple: [HIG Materials](https://developer.apple.com/design/human-interface-guidelines/materials) · [NSVisualEffectView](https://developer.apple.com/documentation/appkit/nsvisualeffectview) · [Glass.clear](https://developer.apple.com/documentation/swiftui/glass/clear) · [WWDC25 design group lab](https://developer.apple.com/forums/thread/791070) · [Meet Liquid Glass notes](https://wwdcnotes.com/documentation/wwdc25-219-meet-liquid-glass/) · [Liquid Glass (Wikipedia)](https://en.wikipedia.org/wiki/Liquid_Glass)
- Userstyles: [Catppuccin creating userstyles](https://userstyles.catppuccin.com/contributing/creating-userstyles/) · [Midnight Lizard](https://github.com/Midnight-Lizard/Midnight-Lizard)
- UI recognition: [Screen Recognition (arXiv 2101.04893)](https://arxiv.org/abs/2101.04893) · [Mozilla Readability](https://github.com/mozilla/readability)
- Layers: [web.dev dialog + popover](https://web.dev/articles/baseline-in-action-dialog-popover) · [MDN Popover API](https://developer.mozilla.org/en-US/docs/Web/API/Popover_API) · [MDN stacking context](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_positioned_layout/Stacking_context) · [relative colour syntax, Firefox 128](https://web.dev/blog/web-platform-07-2024)
- Contrast: [apca-w3](https://github.com/Myndex/apca-w3) · [APCA introduction](https://github.com/Myndex/apca-introduction)
- LLM + verification: [Design2Code (arXiv 2403.03163)](https://arxiv.org/abs/2403.03163) · [VisRefiner (arXiv 2511.08195)](https://arxiv.org/abs/2511.08195) · [Amazon vision-guided refinement](https://cdn.amazon.science/e2/87/68ecc1e04ecc9e2e92bcd5fd3750/scipub-approval152129-45356067-visionguided-iterative-refinement-for-frontend-code-generation.pdf)
