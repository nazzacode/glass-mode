// layers: hidden UI a trigger revealed. 'mark' remembers what is on screen now; 'diff' → roots of newly visible subtrees that
// float (positioned absolute/fixed themselves or via an ancestor, top layer, or a popup role), ≥ 1200 px², largest first.
// trigger: selector of the activated control — anything new INSIDE it (Material ripple, focus ring) is not a layer.
((mode, trigger) => {
  const all = [...document.body.querySelectorAll('*')];
  if (mode === 'mark') { window.__glxSeen = new WeakSet(all.filter(onScreen)); return 'true'; }
  const seen = window.__glxSeen || new WeakSet();
  const fresh = new Set(all.filter(e => !seen.has(e) && onScreen(e)));
  const floats = e => { if (e.matches('dialog[open], :popover-open, [role=dialog], [role=alertdialog], [role=menu], [role=listbox], [role=tooltip]')) return true;
    for (let x = e; x && x !== document.body; x = x.parentElement) if (/^(absolute|fixed)$/.test(getComputedStyle(x).position)) return true;
    return false; };
  // the painted panel of a layer: the largest painting element in it smaller than the viewport — wrappers are often
  // clear, and modal roots are often a full-screen scrim whose dialog is the panel that holds the text
  const paints = e => (rgba(getComputedStyle(e).backgroundColor) || [0, 0, 0, 0])[3] > 0.02;
  const area = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
  const panel = e => [e, ...e.querySelectorAll('*')].filter(x => paints(x) && area(x) < 0.8 * W * H)
    .sort((a, b) => area(b) - area(a))[0] || e;
  // does the layer cover text that was already on screen? (menus over content need popover opacity; a drawer over clear glass doesn't)
  const textual = all.filter(e => seen.has(e) && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && onScreen(e));
  const hits = (a, b) => a.left < b.right - 2 && b.left < a.right - 2 && a.top < b.bottom - 2 && b.top < a.bottom - 2;
  const over = p => { const r = p.getBoundingClientRect(); return textual.some(t => !t.contains(p) && !p.contains(t) && hits(t.getBoundingClientRect(), r)); };
  // frosted: the panel or an ancestor up to the layer root blurs what's beneath (headless pixels never show blur → style)
  const blurred = (p, root) => { for (let x = p; x; x = x.parentElement) { if (getComputedStyle(x).backdropFilter !== 'none') return true; if (x === root) break; } return false; };
  // veil: a full-viewport element in the layer that frosts or tints the whole window (modal wrapper / focus trap
  // styled as a panel → everything goes solid). A light scrim (Apple .35) is fine
  const veil = e => [e, ...e.querySelectorAll('*')].some(x => area(x) >= 0.8 * W * H
    && (getComputedStyle(x).backdropFilter !== 'none' || (rgba(getComputedStyle(x).backgroundColor) || [0, 0, 0, 0])[3] * (+getComputedStyle(x).opacity) > 0.45));
  let inside = null; try { inside = trigger && document.querySelector(trigger); } catch (_) {}
  const roots = [...fresh].filter(e => !fresh.has(e.parentElement) && floats(e) && !(inside && inside.contains(e)))
    .map(e => ({ sel: path(e), label: label(e), rect: rectOf(e), panel: rectOf(panel(e)), over: over(panel(e)), blur: blurred(panel(e), e), veil: veil(e) }))
    .filter(l => l.rect[2] * l.rect[3] >= 1200)
    .sort((a, b) => b.rect[2] * b.rect[3] - a.rect[2] * a.rect[3]);
  return JSON.stringify(roots.slice(0, 6));
})
