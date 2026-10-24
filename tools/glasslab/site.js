// one article at a time (docs layout); #site-x deep links work, unknown hash → overview. #sites?q=… carries gallery state
const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
const route = () => location.hash.slice(1).split('?');
const show = () => { const [id, qs] = route(); const a = document.getElementById(id) || document.getElementById('overview');
  $$('article').forEach(x => x.classList.toggle('on', x === a));
  const cur = a.id.startsWith('site-') ? 'sites' : a.id;
  $$('nav a[href^="#"]').forEach(l => l.toggleAttribute('aria-current', l.getAttribute('href') === '#' + cur));
  if (a.id === 'sites') gallery.load(new URLSearchParams(qs || ''));
  if (id) scrollTo(0, 0); };

// gallery: search, status chips, dark/light thumbs, sort, grid/table. Pure state → DOM; state → hash + remembered mode
const gallery = (() => {
  const art = document.getElementById('sites'); if (!art) return { load() {} };
  const cards = $$('.card', art), rows = $$('tbody tr', art), q = $('#q', art), sort = $('#sort', art);
  const order = new Map(cards.map((c, i) => [c, i])), rowOf = new Map(rows.map(r => [r.dataset.name, r]));
  const defaults = () => ({ q: '', st: $$('[data-key=status] button', art).filter(b => b.dataset.on !== '0').map(b => b.value),
    mode: store.get() || 'dark', sort: 'status', view: 'grid' });
  const store = { get: () => { try { return localStorage.getItem('glass-gallery-mode'); } catch { return null; } },
                  set: v => { try { localStorage.setItem('glass-gallery-mode', v); } catch {} } };
  $$('[data-key=status] button', art).forEach(b => { b.dataset.on = b.getAttribute('aria-pressed') === 'true' ? '1' : '0'; });
  let s = defaults(), seed = Math.random();

  const hit = (el, st) => st.st.includes(el.dataset.status) &&
    (!st.q || el.dataset.name.includes(st.q) || el.dataset.host.includes(st.q));
  const rank = (st) => st.sort === 'name' ? (a, b) => a.dataset.name.localeCompare(b.dataset.name)
    : st.sort === 'shuffle' ? (a, b) => hash(a.dataset.name + seed) - hash(b.dataset.name + seed)
    : (a, b) => order.get(a) - order.get(b);
  const hash = str => [...str].reduce((h, ch) => Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0, 2166136261);

  const paint = () => {
    const grid = $('.cards', art), body = $('tbody', art), sorted = [...cards].sort(rank(s));
    sorted.forEach(c => { c.hidden = !hit(c, s); grid.append(c);
      const r = rowOf.get(c.dataset.name); if (r) { r.hidden = c.hidden; body.append(r); }
      const im = $('img', c); if (im) { const src = im.dataset[s.mode]; if (im.getAttribute('src') !== src) im.src = src; } });
    const n = sorted.filter(c => !c.hidden).length;
    $('.count', art).textContent = `${n} of ${cards.length} sites`;
    $('.empty', art).hidden = n > 0;
    grid.hidden = s.view !== 'grid'; $('.tbl', art).hidden = s.view !== 'table';
    $$('.seg', art).forEach(g => $$('button', g).forEach(b => b.setAttribute('aria-pressed',
      String(g.dataset.key === 'status' ? s.st.includes(b.value) : s[g.dataset.key] === b.value))));
    if (q.value !== s.q) q.value = s.q;
    sort.value = s.sort;
  };
  const save = () => { const d = defaults(), p = new URLSearchParams();
    Object.entries(s).forEach(([k, v]) => { const x = [v].flat().join(','); if (x !== [d[k]].flat().join(',')) p.set(k, x); });
    history.replaceState(null, '', '#sites' + (p.size ? '?' + p : '')); };
  const set = patch => { s = { ...s, ...patch }; if (patch.mode) store.set(patch.mode); paint(); save(); };

  q.addEventListener('input', () => set({ q: q.value.trim().toLowerCase() }));
  sort.addEventListener('change', () => { if (sort.value === 'shuffle') seed = Math.random(); set({ sort: sort.value }); });
  art.addEventListener('click', e => { const b = e.target.closest('.seg button'); if (!b) return;
    const k = b.closest('.seg').dataset.key;
    set(k === 'status' ? { st: s.st.includes(b.value) ? s.st.filter(x => x !== b.value) : [...s.st, b.value] } : { [k]: b.value }); });
  return { load(p) { const d = defaults();
    s = { q: p.get('q') || '', st: p.has('st') ? p.get('st').split(',').filter(Boolean) : d.st,
          mode: ['dark', 'light'].includes(p.get('mode')) ? p.get('mode') : d.mode,
          sort: ['status', 'name', 'shuffle'].includes(p.get('sort')) ? p.get('sort') : 'status',
          view: p.get('view') === 'table' ? 'table' : 'grid' };
    paint(); } };
})();
addEventListener('hashchange', show); show();

// lightbox: click a shot → fullscreen; click image / › / → / swipe = next, ‹ / ← = previous; ×, Esc or backdrop closes.
// Flips through the visible pictures of the current article (the gallery: what the filters left)
const box = document.getElementById('lightbox'), big = $('img', box), cap = $('p', box);
let imgs = [], at = 0, x0 = null;
const view = i => { at = (i + imgs.length) % imgs.length; const im = imgs[at];
  big.src = im.currentSrc || im.src; big.alt = im.alt; cap.textContent = `${im.alt}  ·  ${at + 1} / ${imgs.length}`; };
$('main').addEventListener('click', e => { const im = e.target.closest('figure img'); if (!im) return;
  imgs = $$('figure img', im.closest('article')).filter(x => !x.closest('[hidden]')); view(imgs.indexOf(im)); box.showModal(); });
box.addEventListener('click', e => { const b = e.target.closest('button');
  if (b) b.value === 'close' ? box.close() : view(at + +b.value); else if (e.target === big) view(at + 1); else box.close(); });
box.addEventListener('touchstart', e => { x0 = e.touches[0].clientX; }, { passive: true });
box.addEventListener('touchend', e => { const dx = e.changedTouches[0].clientX - x0;
  if (Math.abs(dx) > 40) { view(at + (dx < 0 ? 1 : -1)); e.preventDefault(); } });
addEventListener('keydown', e => { if (!box.open) return;
  if (e.key === 'ArrowRight' || e.key === ' ') { view(at + 1); e.preventDefault(); } else if (e.key === 'ArrowLeft') view(at - 1); });
