// privacy scrambler, run in-page before a showcase capture. args: (scopes = selectors, default ['body'], seed)
// text → plausible English-ish words: same length, case, punctuation; numbers ≥ 3 digits → other digits (function/UI
// words, short numbers and years stay: plausible, never private). Deterministic per seed +
// original word (a repeated name stays one fake name). Private attributes too; photos/avatars covered by neutral
// shapes (cover, never blur: blur looks broken). Iframes (the scrambler can't reach in: cross-origin, e.g. Google's app
// launcher with the account photo) → flat grey box (filter: contrast(0)). Text nodes / attributes / CSSOM only (Trusted Types pages: no HTML
// sinks). A MutationObserver keeps late DOM updates scrambled until the page unloads. → {texts, chars, attrs, images}
(scopes, seed) => {
  scopes = scopes && scopes.length ? scopes : ['body'];
  seed = seed | 0;
  const WORDS = ('a i o of to in it is on at by we us an as or up so do go be me no my he ' +
    'the and for are but not you all any can had her was one our out day get has him his how man new now old see two way who boy did its let put say she too use ' +
    'that with have this will your from they know want been good much some time very when come here just like long make many more only over such take than them well ' +
    'about after again below could every first found great house large learn never other place plant point right small sound spell still study their there these thing think three water where which world would write ' +
    'across always animal answer before better change differ family follow letter little mother number people around should simple summer travel winter garden market silver orange yellow window ' +
    'balance between capital century certain company country example morning nothing picture problem product program project several station surface teacher weather without journey kitchen harvest morning lantern meadow ' +
    'absolute building children complete continue language mountain movement remember sentence separate standard question together whatever painting thousand evening northern platform shoulder ' +
    'adventure attention community direction important knowledge practical determine furniture beautiful character september wonderful landscape afternoon chocolate ' +
    'atmosphere collection conference everything generation incredible understand particular population reflection signature photograph instrument ' +
    'temperature information environment development celebration countryside imagination observation ' +
    'presentation neighborhood construction relationship organization ').trim().split(/\s+/);
  // kept as-is: function words + common app UI words / days / months. Never names (no will, may, mark, june, rose …)
  const KEEP = new Set(('a an the of to in on at by for from with and or but not no is are was were be been it its this that ' +
    'these those i you we they he she me my your our their his her us them as if so do does did has have had can could ' +
    'would should all any each more less new re fwd fw via am pm ' +
    'inbox starred snoozed sent drafts draft spam trash bin compose labels label primary promotions social updates forums ' +
    'important everything else search mail settings help today yesterday tomorrow week month year day days reply forward ' +
    'archive delete unread read chat chats meet calendar tasks contacts notes home library later feed create upload share ' +
    'save saved edit view open close cancel done next previous back refresh select options account apps recents projects ' +
    'subscriptions shorts history playlists liked videos downloads show explore trending ' +
    'mon tue wed thu fri sat sun monday tuesday wednesday thursday friday saturday sunday ' +
    'feb mar apr jun jul aug sep sept oct nov dec january february march july september october november december').split(' '));
  const BY = {};
  for (const w of WORDS) (BY[w.length] ||= []).push(w);
  const MAX = Math.max(...Object.keys(BY).map(Number));
  const ATTRS = ['placeholder', 'value', 'title', 'aria-label', 'alt', 'data-tooltip', 'aria-description'];
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'svg', 'SVG']);
  const ICON_FONT = /material|icons?\b|symbols? (outlined|rounded|sharp)|glyph|awesome/i;   // first family only:
  const LIGATURE = /^\s*[a-z0-9_]+\s*$/;   // stacks end in 'Segoe UI Symbol'; icon text = one ligature name, else scramble
  const ICON_SRC = /logo|icon|sprite|cleardot|emoji|branding|\.svg|^data:image\/svg/i;
  const COVER = 'rgb(142, 142, 150)';

  // FNV-1a over seed + string
  const hash = s => { let h = (2166136261 ^ Math.imul(seed, 2654435761)) >>> 0;
    for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619) >>> 0; return h; };
  const fakeWord = (n, h) => n <= MAX && BY[n] ? BY[n][h % BY[n].length]
    : n <= MAX ? fakeWord(n - 1, h) + 'e'
    : fakeWord(Math.ceil(n / 2), h) + fakeWord(Math.floor(n / 2), Math.imul(h, 31) >>> 0);
  const memo = new Map();
  const word = w => { const k = w.toLowerCase(); if (KEEP.has(k) || [...k].length === 1) return w;   // + initials
    if (!memo.has(k)) memo.set(k, fakeWord([...k].length, hash(k)));
    const f = [...memo.get(k)], o = [...w];
    return f.map((c, i) => (o[i] && o[i] !== o[i].toLowerCase()) ? c.toUpperCase() : c).join(''); };
  const digits = d => { if (d.length <= 2 || /^(19|20)\d\d$/.test(d)) return d;   // times, dates, years, counts stay
    const h = hash('#' + d);
    return [...d].map((c, i) => String((+c + 1 + ((h >>> ((i % 8) * 4)) % 9)) % 10)).join(''); };
  const scr = s => s.replace(/\p{L}+|\p{N}+/gu, t => /^\p{N}+$/u.test(t) ? (/^\d+$/.test(t) ? digits(t) : t) : word(t));

  const st = window.__tzScramble ||= { text: new WeakMap(), attr: new WeakMap(), stats: { texts: 0, chars: 0, attrs: 0, images: 0, frames: 0 } };
  const stats = st.stats;
  const fontOk = new WeakMap();
  const iconFont = el => { if (!fontOk.has(el)) fontOk.set(el, ICON_FONT.test(getComputedStyle(el).fontFamily.split(',')[0]));
    return fontOk.get(el); };
  st.roots = st.roots || new WeakSet();   // open shadow roots found inside a scope (closest() can't cross into them)
  const inScope = n => { const el = n.nodeType === 1 ? n : n.parentElement; if (!el) return false;
    const r = el.getRootNode(); return r instanceof ShadowRoot ? st.roots.has(r) : scopes.some(s => el.closest(s)); };

  const text = n => {
    const p = n.parentElement;
    if (!p || SKIP.has(p.tagName) || p.closest('svg') || st.text.get(n) === n.nodeValue || !/[\p{L}\d]/u.test(n.nodeValue) || (LIGATURE.test(n.nodeValue) && iconFont(p))) return;
    const v = scr(n.nodeValue);
    st.text.set(n, v);
    n.nodeValue = v;
    stats.texts++; stats.chars += v.length;
  };
  const attrs = el => {
    const done = st.attr.get(el) || {};
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (v && done[a] !== v && /[\p{L}\d]/u.test(v)) { done[a] = scr(v); el.setAttribute(a, done[a]); stats.attrs++; }
    }
    if ((el.tagName === 'INPUT' && /^(text|search|email|url|tel|)$/.test(el.type)) || el.tagName === 'TEXTAREA') {
      if (el.value && el.value !== done.value && el.value !== done.$value) { done.$value = scr(el.value); el.value = done.$value; stats.attrs++; }
    }
    st.attr.set(el, done);
  };
  const cover = (el, round) => {
    const s = el.style;
    s.setProperty('background', COVER, 'important');
    s.setProperty('border-radius', round ? '50%' : '6px', 'important');
    stats.images++;
  };
  const image = el => {
    if (el.dataset.tzCovered) return;
    const r = el.getBoundingClientRect();
    const round = Math.abs(r.width - r.height) < 4 && r.width <= 96;
    if (el.tagName === 'IMG') {
      if (ICON_SRC.test(el.currentSrc || el.src) || r.width < 12 || r.height < 12) return;
      el.style.setProperty('object-position', '-99999px -99999px', 'important');   // image pixels gone, box stays
      el.dataset.tzCovered = 1;
      return cover(el, round);
    }
    const bg = getComputedStyle(el).backgroundImage;
    if (!/url\(/.test(bg) || ICON_SRC.test(bg) || r.width < 24 || r.height < 24) return;
    el.style.setProperty('background-image', 'none', 'important');
    el.dataset.tzCovered = 1;
    cover(el, round);
  };
  const frame = el => {
    if (el.dataset.tzCovered) return;
    el.style.setProperty('filter', 'contrast(0)', 'important');
    el.style.setProperty('border-radius', '6px', 'important');
    el.dataset.tzCovered = 1;
    stats.frames++;
  };
  const LIVE = ['src', 'srcset', 'poster', 'style'];   // lazy images swap these after load
  const OBSERVE = { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: [...ATTRS, ...LIVE] };
  const scan = root => {
    if (root.nodeType === 3) return text(root);
    if (root.nodeType !== 1 && root.nodeType !== 11) return;
    if (root.nodeType === 1 && SKIP.has(root.tagName)) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) text(n);
    for (const el of root.nodeType === 11 ? root.querySelectorAll('*') : [root, ...root.querySelectorAll('*')]) {
      if (ATTRS.some(a => el.hasAttribute(a)) || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') attrs(el);
      if (/^(IFRAME|CANVAS|VIDEO|EMBED|OBJECT)$/.test(el.tagName)) frame(el);   // pixels we can't rewrite → grey box
      else image(el);                                                         // <img> or url() background on ANY element
      if (el.shadowRoot && !st.roots.has(el.shadowRoot)) {                    // open shadow roots (Reddit, web components)
        st.roots.add(el.shadowRoot);
        scan(el.shadowRoot);
        st.obs?.observe(el.shadowRoot, OBSERVE);
      }
    }
  };

  // observer first: shadow roots found during the scan get observed too
  if (!st.obs) {
    st.obs = new MutationObserver(ms => { for (const m of ms) {
      if (!inScope(m.target)) continue;
      if (m.type === 'characterData') text(m.target);
      else if (m.type === 'attributes') LIVE.includes(m.attributeName) ? image(m.target) : attrs(m.target);
      else m.addedNodes.forEach(scan);
    } });
    st.obs.observe(document.documentElement, OBSERVE);
  }
  for (const s of scopes) document.querySelectorAll(s).forEach(scan);
  return JSON.stringify(stats);
}
