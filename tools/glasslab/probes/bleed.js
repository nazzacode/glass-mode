// see-through check: scroll, then find floating bars and panels with page content sliding under them. Sharp content behind text is what makes them
// unreadable, and an unscrolled page has nothing under its top bar, so the other probes never saw it. → [{sel, rect, alpha, blur, under, text}]
(minArea) => {
  const alphaOf = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return 0;
    const p = m[1].split(/[ ,/]+/).map(parseFloat);
    return p.length > 3 ? p[3] : 1;
  };
  const describe = (el) => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "");
  const vw = innerWidth, vh = innerHeight;
  const all = [...document.querySelectorAll("body *")];
  // scroll every big scroller so content sits under whatever floats over it
  for (const el of [document.scrollingElement, ...all]) {
    if (!el || el.scrollHeight <= el.clientHeight + 200 || el.clientWidth * el.clientHeight < vw * vh * 0.2) continue;
    const o = getComputedStyle(el).overflowY;
    if (el === document.scrollingElement || o === "auto" || o === "scroll") el.scrollTop = Math.min(400, el.scrollHeight - el.clientHeight);
  }
  const floats = all.filter((el) => {
    const s = getComputedStyle(el);
    if (s.position !== "fixed" && s.position !== "sticky" && !(s.position === "absolute" && s.zIndex !== "auto")) return false;
    if (s.visibility === "hidden" || s.display === "none" || +s.opacity < 0.05 || s.pointerEvents === "none") return false;
    const r = el.getBoundingClientRect();
    const w = Math.min(r.right, vw) - Math.max(r.left, 0), h = Math.min(r.bottom, vh) - Math.max(r.top, 0);
    return w > 0 && h > 0 && w * h >= minArea && w * h < vw * vh * 0.9;
  });
  const painted = (el) => el.tagName === "IMG" || el.tagName === "VIDEO" || el.tagName === "svg" || [...el.childNodes].some((n) => n.nodeType === 3 && n.data.trim());
  const out = [];
  for (const el of floats) {
    if (floats.some((f) => f !== el && f.contains(el))) continue; // the outermost layer speaks for its subtree
    const r = el.getBoundingClientRect();
    const hits = [];
    const hasText = !!el.innerText?.trim();
    for (let i = 1; i <= 5; i++) for (let j = 1; j <= 3; j++) {
      const x = Math.max(r.left, 0) + (Math.min(r.right, vw) - Math.max(r.left, 0)) * i / 6, y = Math.max(r.top, 0) + (Math.min(r.bottom, vh) - Math.max(r.top, 0)) * j / 4;
      const stack = document.elementsFromPoint(x, y);
      if (!stack.some((e) => e === el || el.contains(e))) continue;
      const mine = stack.filter((e) => e === el || el.contains(e));
      const under = stack.filter((e) => !el.contains(e) && !e.contains(el) && painted(e));
      if (!under.length) continue;
      let clear = 1, blur = false;
      for (let e = mine[0]; e; e = e === el ? null : e.parentElement) { // the layer's own paint at this point, ancestors inside it included
        const s = getComputedStyle(e);
        clear *= 1 - alphaOf(s.backgroundColor);
        if (s.backdropFilter && s.backdropFilter !== "none") blur = true;
      }
      for (let a = el.parentElement; a; a = a.parentElement) if (getComputedStyle(a).backdropFilter !== "none") blur = true;
      hits.push({ alpha: 1 - clear, blur, under: describe(under[0]) });
    }
    if (!hits.length) continue;
    const worst = hits.reduce((a, b) => (a.alpha <= b.alpha ? a : b));
    out.push({ sel: describe(el), position: getComputedStyle(el).position, rect: [r.left, r.top, r.width, r.height].map(Math.round), alpha: +worst.alpha.toFixed(2), blur: hits.every((h) => h.blur), under: worst.under, text: hasText, overlaps: hits.length });
  }
  return JSON.stringify(out);
}
