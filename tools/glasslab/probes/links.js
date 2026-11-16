// links: same-origin navigation the app itself offers (sidebar, nav, header, tabs, then main), for crawl. Read-only by
// construction: plain GET links only, nothing whose label sources or href match danger (sign out, delete, billing…),
// no downloads, no new windows, no in-page anchors. args: danger (RegExp source), max → [{href, label, nav}]
((danger, max) => {
  const D = new RegExp(danger, 'i');
  const clean = s => (s || '').trim().replace(/\s+/g, ' ');
  const navish = e => !!e.closest('nav, aside, header, [role=navigation], [role=tablist], [data-sidebar-surface], [class*="sidebar" i], [class*="nav" i]');
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let u; try { u = new URL(a.href, location.href); } catch (_) { continue; }
    if (u.origin !== location.origin || a.hasAttribute('download') || (a.target && a.target !== '_self')) continue;
    u.hash = '';
    const href = u.href;
    if (href === location.href.split('#')[0] || seen.has(href)) continue;
    const r = a.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const label = clean([a.getAttribute('aria-label'), a.getAttribute('title'), a.innerText].filter(Boolean).join(' ')).slice(0, 60);
    if (D.test(label + ' ' + u.pathname + u.search)) continue;
    seen.add(href);
    out.push({ href, label, nav: navish(a) });
  }
  out.sort((x, y) => (y.nav - x.nav));
  return JSON.stringify(out.slice(0, max));
})
