// layers: hidden UI a trigger revealed. 'mark' remembers what is on screen now; 'diff' → roots of newly visible subtrees that
// float (positioned absolute/fixed themselves or via an ancestor, top layer, or a popup role), ≥ 1200 px², largest first.
((mode) => {
  const all = [...document.body.querySelectorAll('*')];
  if (mode === 'mark') { window.__glxSeen = new WeakSet(all.filter(onScreen)); return 'true'; }
  const seen = window.__glxSeen || new WeakSet();
  const fresh = new Set(all.filter(e => !seen.has(e) && onScreen(e)));
  const floats = e => { if (e.matches('dialog[open], :popover-open, [role=dialog], [role=alertdialog], [role=menu], [role=listbox], [role=tooltip]')) return true;
    for (let x = e; x && x !== document.body; x = x.parentElement) if (/^(absolute|fixed)$/.test(getComputedStyle(x).position)) return true;
    return false; };
  // the painted panel of a layer: the root if it paints, else its largest painting descendant (wrappers are often clear)
  const paints = e => (rgba(getComputedStyle(e).backgroundColor) || [0, 0, 0, 0])[3] > 0.02;
  const area = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
  const panel = e => paints(e) ? e : [...e.querySelectorAll('*')].filter(paints).sort((a, b) => area(b) - area(a))[0] || e;
  const roots = [...fresh].filter(e => !fresh.has(e.parentElement) && floats(e))
    .map(e => ({ sel: path(e), label: label(e), rect: rectOf(e), panel: rectOf(panel(e)) })).filter(l => l.rect[2] * l.rect[3] >= 1200)
    .sort((a, b) => b.rect[2] * b.rect[3] - a.rect[2] * a.rect[3]);
  return JSON.stringify(roots.slice(0, 6));
})
