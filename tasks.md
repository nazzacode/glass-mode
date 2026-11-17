# Glass Mode tasks

Claims board for agent sessions. Goal + bar: [docs/NORTH-STAR.md](docs/NORTH-STAR.md). Lab + style rules:
[docs/GLASS.md](docs/GLASS.md). Linear GEN-213 (under GEN-207 "proof of work") = Nathan's high-level view; GEN-162 = stage 2. Detail lives here.
Claim: `[/]` + `@<session> <date>`. Done → `[x]`, drop tag. Claims > 2 days with no branch/session = stale, take over.
Private notes (browsing-history site list, launch kit): `launch/` (gitignored, local).

## Now
- [/] Fix every fail from the strict full-suite run (2026-11-16) — see "Lab backlog" below @glass-backlog 2026-11-17
- [ ] Crawl every covered site (`./glasslab crawl NAME URL`), fix leftover-surface tables; add crawl entry URLs to screens.json
- [ ] Crawl: open non-link item views (issue peek, row expanders, settings tabs) — biggest remaining blind spot
- [ ] Feed crawl results into `glasslab add --agent` (agent only sees listed screens today)
- [ ] `glasslab add`: register at END of ContentScripts.json, CRLF (today: top, LF; fixed by hand each time)

## Sites to add (Zen history, 6 weeks, by visits; flat-hunt sites ignored)
- [ ] GOV.UK design system (universal credit 34 + all gov.uk services: one style, hundreds of sites)
- [ ] accounts.google.com sign-in/consent (209, short pages)
- [ ] luma.com (79)
- [ ] zen-browser.app + docs (53)
- [ ] accounts.firefox.com (35)
- [ ] linkedin.com (26)
- [ ] openrouter.ai (25)
- [ ] pocketcasts.com (21)
- [ ] acrobat.adobe.com (18), amazon (18), easyjet (16), londonstartupmap (27)

## Stage 2: any site live (NORTH-STAR › Stage 2)
- [ ] Run crawl with auto glass forced on covered sites → per-site auto-vs-handwritten gap table
- [ ] Autoglass: inline-style mutation pass (JS-painted panels), new top-layer roots classified within a frame
- [ ] A/B auto vs opaque on uncovered sites → default on if it wins

## Taste + launch (quality plan order)
- [ ] A/B votes (GEN-159): rig built, 0 votes — needs Nathan; ask once, don't block on it
- [ ] Popup redesign in glass tokens (GEN-163 follow-up), in-browser "add this site" button
- [ ] Week-long bar (GEN-164) → launch (GEN-76)

## Lab backlog (strict suite 2026-11-16: 62/497 default rows fail; run `./glasslab test FILTER`)
Look at each render first: the slab rule is new, a hit may be an image/brand area that should be exempt.
- [ ] chatgpt: style not applying at all (surface 0 %, 96 % slab) — site changed or logged-out shell
- [ ] claude.ai: Cloudflare wall in lab (GEN-112) → replay/corpus
- [ ] gcal week/month/event: one hidden layer at surface 46 %, text 50 %
- [ ] spotify home: 19 % slab (dark); artist: OneTrust cookie banner 33 % slab
- [ ] ddg home search suggestions: 20 % slab, contrast 0 % (light)
- [ ] gdrive my-drive/recent: 6–8 % slab (+ contrast 81 % light)
- [ ] notion careers/what's new: 5–9 % slab
- [ ] substack home: text 77 %, contrast 76 % light (feed-dependent)
- [ ] linear issue page: contrast 16 % light
- [ ] gemini: hidden layer contrast 78 %
- [ ] x profile 5 % slab · discord login 2 % slab · youtube music menu see-through .68 (unblurred)
- [ ] autoglass: bbc 6 % slab + contrast 82 % light; mdn `<details>` 4 % slab, code-example layers 83 %; onthemarket contrast 88 %
- [ ] slider extremes (α .10/.90) fail widely (gcal, gmail, reader, claude, substack): user's trade below default, review after taste votes

## Done (recent)
- [x] 2026-11-16 crawl, logged-in lab (site storage), slab rule, blurred-or-solid, veil, animation settle
- [x] 2026-11-16 Linear lanes (1.0.11), composers (1.0.12); 2026-11-11 cards (1.0.9), new-issue modal (1.0.10)
