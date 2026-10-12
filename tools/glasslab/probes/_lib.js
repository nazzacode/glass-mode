// prelude for every probe (lab.Page.probe prepends it): small DOM helpers. Probes may shadow these names.
const W = innerWidth, H = innerHeight;
// css colour → [r, g, b, a] (null for none/unparseable). Firefox keeps oklch()/lab()/color() in computed style
// (Tailwind v4) → anything not rgb() goes through a 1×1 canvas
const _cv = document.createElement('canvas').getContext('2d', { willReadFrequently: true }), _cc = new Map();
const rgba = c => { if (!c || c === 'transparent' || c === 'none') return null;
  const m = c.match(/^rgba?\(([^)]+)\)/); if (m) { const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
  if (!_cc.has(c)) { _cv.clearRect(0, 0, 1, 1); _cv.fillStyle = c; _cv.fillRect(0, 0, 1, 1); const d = _cv.getImageData(0, 0, 1, 1).data;
    _cc.set(c, [d[0], d[1], d[2], Math.round(d[3] / 255 * 1000) / 1000]); }
  return _cc.get(c); };
const css = c => `rgb(${c[0]}, ${c[1]}, ${c[2]})`;   // normalised colour for reports (Python parses rgb())
// short human selector (reports): tag#id.class.class[role]
const label = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + [...e.classList].slice(0, 2).map(c => '.' + c).join('')
  + (e.getAttribute('role') ? `[role=${e.getAttribute('role')}]` : '');
// unique selector (re-locate the element later): #id, else nth-of-type path up to the nearest unique id
const uniq = id => id && document.querySelectorAll('#' + CSS.escape(id)).length === 1;
const path = e => { const parts = [];
  for (let x = e; x && x !== document.body && x !== document.documentElement; x = x.parentElement) {
    if (uniq(x.id)) { parts.unshift('#' + CSS.escape(x.id)); return parts.join(' > '); }
    let i = 1; for (let s = x.previousElementSibling; s; s = s.previousElementSibling) if (s.tagName === x.tagName) i++;
    parts.unshift(`${x.tagName.toLowerCase()}:nth-of-type(${i})`); }
  return ['body', ...parts].join(' > '); };
// on screen and painted (not visibility:hidden / opacity 0 / zero-size)
const onScreen = e => { const r = e.getBoundingClientRect();
  if (r.width < 1 || r.height < 1 || r.bottom <= 0 || r.right <= 0 || r.top >= H || r.left >= W) return false;
  const s = getComputedStyle(e); return s.visibility === 'visible' && +s.opacity > 0.05; };
const rectOf = e => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; };
// opacity an element is painted with (its own × every ancestor's); cached per probe run
const _op = new Map();
const opacity = e => { if (!e || e.nodeType !== 1) return 1; if (_op.has(e)) return _op.get(e);
  const o = +getComputedStyle(e).opacity * opacity(e.parentElement); _op.set(e, o); return o; };
