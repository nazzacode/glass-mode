// triggers: on-screen controls that reveal hidden UI (menus, dropdowns, dialogs, suggestions) and are safe to activate.
// args: danger (RegExp source: never touched), max. Safety: DANGER tested against EVERY label source joined (aria-label,
// aria-labelledby text, title, tooltip, text, placeholder, id, href); unlabeled controls skipped (can't judge them);
// no navigation links, no submit buttons (incl. a <button> without type inside a form), nothing disabled or covered.
// kind 'type' only for search-like fields — anything else (composers, forms) is only ever clicked.
((danger, max) => {
  const D = new RegExp(danger, 'i');
  const clean = s => (s || '').trim().replace(/\s+/g, ' ');
  const sources = e => [e.getAttribute('aria-label'),
    (e.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent).join(' '),
    e.getAttribute('title'), e.getAttribute('data-tooltip'), e.getAttribute('data-tooltip-content'), e.innerText,
    e.getAttribute('placeholder')].map(clean).filter(Boolean);
  const searchy = e => e.matches('input[type=search], [role=combobox], [role=searchbox]')
    || /search|find|filter|query|look ?up|suche|recherche|buscar|cerca/i.test(sources(e).join(' ') + ' ' + (e.name || ''));
  const typeable = e => e.matches('input:not([type]), input[type=search], input[type=text], textarea') && searchy(e);
  const submits = e => e.matches('[type=submit], input[type=image]') || (e.tagName === 'BUTTON' && e.form && e.type === 'submit');
  const out = [], seen = new Set();
  for (const e of document.querySelectorAll('[aria-haspopup]:not([aria-haspopup=false]), [aria-expanded=false], [role=combobox], input[type=search], input[list], [popovertarget]')) {
    if (out.length >= max) break;
    if (e.closest('[aria-disabled=true], [disabled], [inert]') || e.matches('a[href]:not([href^="#"]):not([role=button])') || submits(e)) continue;
    if (!onScreen(e)) continue;
    const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, hit = document.elementFromPoint(x, y);
    if (!hit || !(hit === e || e.contains(hit) || hit.contains(e))) continue;           // covered by something else
    const all = sources(e);
    if (!all.length) continue;                                                            // unlabeled: can't judge → skip
    if (D.test([...all, e.id, e.getAttribute('href') || ''].join(' | '))) continue;
    if (e.matches('input, textarea') && !typeable(e) && !searchy(e)) continue;          // non-search text fields: leave alone
    const t = all[0].slice(0, 60);
    const role = e.getAttribute('role') || e.tagName.toLowerCase(), k = `${role}|${t}`;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ id: e.id, sel: path(e), label: t, role, kind: typeable(e) ? 'type' : 'click', x: Math.round(x), y: Math.round(y) });
  }
  return JSON.stringify(out);
})
