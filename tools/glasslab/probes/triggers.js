// triggers: on-screen controls that reveal hidden UI (menus, dropdowns, dialogs, suggestions) and are safe to activate.
// args: danger (RegExp source: labels never touched), max. Skips navigation links, submit buttons, disabled, covered.
((danger, max) => {
  const D = new RegExp(danger, 'i');
  const text = e => (e.getAttribute('aria-label') || e.innerText || e.getAttribute('placeholder') || e.getAttribute('title') || '')
    .trim().replace(/\s+/g, ' ').slice(0, 60);
  const typeable = e => e.matches('input:not([type]), input[type=search], input[type=text], textarea');
  const out = [], seen = new Set();
  for (const e of document.querySelectorAll('[aria-haspopup]:not([aria-haspopup=false]), [aria-expanded=false], [role=combobox], input[type=search], input[list], [popovertarget]')) {
    if (out.length >= max) break;
    if (e.closest('[aria-disabled=true], [disabled], [inert]') || e.matches('a[href]:not([href^="#"]):not([role=button]), [type=submit]')) continue;
    if (!onScreen(e)) continue;
    const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, hit = document.elementFromPoint(x, y);
    if (!hit || !(hit === e || e.contains(hit) || hit.contains(e))) continue;           // covered by something else
    const t = text(e);
    if (D.test(t) || D.test(e.id)) continue;
    const role = e.getAttribute('role') || e.tagName.toLowerCase(), k = `${role}|${t}`;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ id: e.id, sel: path(e), label: t, role, kind: typeable(e) ? 'type' : 'click', x: Math.round(x), y: Math.round(y) });
  }
  return JSON.stringify(out);
})
