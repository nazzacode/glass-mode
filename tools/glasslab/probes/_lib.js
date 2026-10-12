// prelude for every probe (lab.Page.probe prepends it): small DOM helpers. Probes may shadow these names.
const W = innerWidth, H = innerHeight;
// css colour → [r, g, b, a] (null for none/unparseable)
const rgba = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
  const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
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
