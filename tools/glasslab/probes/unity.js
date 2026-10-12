// unity: topmost painted surface on a grid vs glass.css tier colours; returns shared fg colours too.
// args: scopes — optional selectors (explore layers): 8×6 grid inside each root's rect
((scopes) => {
  const P = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const probe = document.createElement('i'); probe.style.cssText = 'position:fixed;left:-9px;width:1px;height:1px'; document.body.append(probe);
  const tok = v => { probe.style.backgroundColor = `var(${v})`; return P(getComputedStyle(probe).backgroundColor); };
  const tiers = ['--g-frame', '--g-window', '--g-content', '--g-content-abs', '--g-popover', '--g-card', '--g-fill', '--g-fill-hover',
    '--g-fill-selected', '--g-paper', '--g-scrim'].map(t => [t, tok(t)]).filter(x => x[1]);
  const fgs = ['--g-fg', '--g-fg-2', '--g-fg-3'].map(t => { probe.style.color = `var(${t})`; return P(getComputedStyle(probe).color); });
  probe.remove();
  // tier colours are exact computed values → tight match (#fff must not pass as paper rgba(250,250,252,.97))
  const near = (a, b, tc = 3, ta = .015) => Math.abs(a[0]-b[0]) <= tc && Math.abs(a[1]-b[1]) <= tc && Math.abs(a[2]-b[2]) <= tc && Math.abs(a[3]-b[3]) <= ta;
  const tally = {}, foreign = new Map(); let ok = 0, bad = 0;
  const grids = scopes && scopes.length
    ? scopes.map(s => document.querySelector(s)).filter(Boolean).map(root => [root, root.getBoundingClientRect(), 8, 6])
    : [[null, { left: 0, top: 0, width: W, height: H }, 20, 14]];
  for (const [root, r, nx, ny] of grids) for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) {
    const x = Math.min(W - 1, Math.max(0, r.left + (i + .5) * r.width / nx)), y = Math.min(H - 1, Math.max(0, r.top + (j + .5) * r.height / ny));
    for (const e of document.elementsFromPoint(x, y)) {
      if (e === document.documentElement) break;      // scoped: a clear layer shows what's beneath → that surface counts
      const cs = getComputedStyle(e);
      if (/^(IMG|VIDEO|CANVAS|SVG|PICTURE|IFRAME)$/.test(e.tagName) || (cs.backgroundImage !== 'none' && !cs.backgroundImage.includes('gradient'))) break;
      const c = P(cs.backgroundColor); if (!c || c[3] * opacity(e) < .15) continue;  // thin overlays (state layers) aren't surfaces
      if ((e.getAttribute('style') || '').includes('background')) break;  // site data colour (event chip, label) — exempt
      const t = tiers.find(([, v]) => near(c, v));
      if (t) { ok++; tally[t[0]] = (tally[t[0]] || 0) + 1; }
      else { bad++; const k = cs.backgroundColor + ' ' + e.tagName.toLowerCase() + (e.getAttribute('role') ? `[role=${e.getAttribute('role')}]` : '')
        + [...e.classList].slice(0, 2).map(x => '.' + x).join(''); foreign.set(k, (foreign.get(k) || 0) + 1); }
      break;
    }
  }
  return JSON.stringify({ surface: ok / Math.max(1, ok + bad), tiers: tally,
    foreign: [...foreign].sort((a, b) => b[1] - a[1]).slice(0, 6), fgs: fgs.map(f => f && f.slice(0, 3)) });
})
