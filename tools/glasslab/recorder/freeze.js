// freeze this document: HTML + an asset table, no scripts, no network, live state kept (open panels, scroll, form values, shadow DOM, CSS-in-JS
// rules). Assets and shadow-root CSS live once in the table and are referenced as /__gl/<id>: reddit repeats them in every shadow root (171 MB inline). Glass Mode's own marks are dropped so any build or variant can be applied on replay. Also run by the lab.
(() => {
	const MAX_ASSET = 3e6, MAX_TOTAL = 150e6;
	const VOID = new Set("area base br col embed hr img input link meta source track wbr".split(" "));
	const DROP = new Set(["SCRIPT", "NOSCRIPT", "BASE", "OBJECT", "EMBED"]);
	const OWN_TAGS = new Set(["TZ-GLASS-PANEL"]);
	const OWN_IDS = new Set(["tz-custom-styles", "tz-custom-backgrounds"]);
	const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
	const escAttr = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
	const NEW_STATS = () => ({ assets: 0, assetBytes: 0, assetsFailed: 0, sheets: 0, sheetsFailed: 0, frames: 0, framesLost: 0, shadows: 0, closedShadows: 0, canvases: 0 });
	let stats = NEW_STATS(), assets = new Map(), table = {}, sheetsByText = new Map(), sheetTexts = new WeakMap();
	const REF = "/__gl/";
	const put = (dataUrl) => {
		const id = `a${Object.keys(table).length}`;
		table[id] = dataUrl;
		return REF + id;
	};

	const dataUrl = (blob) => new Promise((ok, no) => {
		const r = new FileReader();
		r.onload = () => ok(r.result);
		r.onerror = no;
		r.readAsDataURL(blob);
	});

	// asset URL → /__gl/<id> (cached); on failure the URL stays and replay simply can't load it
	const inline = (raw, base) => {
		if (!raw || /^(data|blob:null|about|javascript|#)/i.test(raw)) return Promise.resolve(raw);
		let url;
		try { url = new URL(raw, base).href; } catch { return Promise.resolve(raw); }
		if (!assets.has(url)) {
			assets.set(url, fetch(url, { credentials: "include" })
				.then((r) => (r.ok ? r.blob() : Promise.reject(r.status)))
				.then((b) => {
					if (b.size > MAX_ASSET || stats.assetBytes + b.size > MAX_TOTAL) throw new Error("too big");
					stats.assets += 1; stats.assetBytes += b.size;
					return dataUrl(b).then(put);
				})
				.catch(() => { stats.assetsFailed += 1; return url; }));
		}
		return assets.get(url);
	};

	const URL_RE = /url\(\s*(?:"([^"]*)"|'([^']*)'|([^)"'\s]*))\s*\)/g;
	const cssAssets = async (css, base) => {
		const found = [...css.matchAll(URL_RE)];
		const urls = await Promise.all(found.map((m) => inline(m[1] ?? m[2] ?? m[3], base)));
		let i = 0;
		// no scripts on replay → custom elements never upgrade; don't let :not(:defined) hide them
		return css.replace(URL_RE, () => `url("${urls[i++]}")`).replace(/:not\(:defined\)/g, ":not(*)");
	};

	const sheetText = (sheet, base) => {
		if (!sheetTexts.has(sheet)) sheetTexts.set(sheet, readSheet(sheet, base));
		return sheetTexts.get(sheet);
	};

	const readSheet = async (sheet, base) => {
		stats.sheets += 1;
		let rules;
		try {
			rules = [...sheet.cssRules];
		} catch { // cross-origin: the CSSOM is closed; the extension's fetch isn't
			if (!sheet.href) { stats.sheetsFailed += 1; return ""; }
			try {
				return cssAssets(await (await fetch(sheet.href, { credentials: "include" })).text(), sheet.href);
			} catch { stats.sheetsFailed += 1; return ""; }
		}
		const parts = await Promise.all(rules.map(async (r) => {
			if (r.type !== CSSRule.IMPORT_RULE) return r.cssText;
			const inner = r.styleSheet ? await sheetText(r.styleSheet, r.styleSheet.href || base) : "";
			return r.media?.mediaText ? `@media ${r.media.mediaText} {${inner}}` : inner;
		}));
		return cssAssets(parts.join("\n"), sheet.href || base);
	};

	const b64 = (text) => {
		const bytes = new TextEncoder().encode(text);
		let bin = "";
		for (let i = 0; i < bytes.length; i += 32768) bin += String.fromCharCode(...bytes.subarray(i, i + 32768));
		return btoa(bin);
	};

	// one copy per distinct text, however many shadow roots use it
	const sheetRef = (css) => {
		if (!sheetsByText.has(css)) sheetsByText.set(css, put(`data:text/css;base64,${b64(css)}`));
		return sheetsByText.get(css);
	};
	const styleTag = (css, attrText, inShadow) => (inShadow && css.length > 2000 ? `<link${attrText} rel="stylesheet" href="${sheetRef(css)}">` : `<style${attrText}>${css}</style>`);

	const adopted = async (root, base, inShadow) => (await Promise.all([...(root.adoptedStyleSheets ?? [])].map((s) => sheetText(s, base))))
		.map((css) => styleTag(css, " data-gl-adopted", inShadow)).join("");

	const attrs = (el, extra = {}, skip = new Set()) => {
		let out = "";
		for (const a of el.attributes) {
			const n = a.name;
			if (skip.has(n) || n.startsWith("on") || n.startsWith("data-tz-") || n === "data-gl-own" || n === "integrity" || n === "nonce" || n === "loading") continue;
			if (n in extra) continue;
			out += ` ${n}="${escAttr(a.value)}"`;
		}
		for (const [n, v] of Object.entries(extra)) if (v !== null && v !== undefined) out += v === true ? ` ${n}` : ` ${n}="${escAttr(String(v))}"`;
		return out;
	};

	const rootAttrs = (el) => {
		const classes = [...el.classList].filter((c) => !c.startsWith("tz-")).join(" ");
		const style = el.style.cssText.replace(/--tz-glass-alpha:[^;]*;?/, "").replace(/background[^;]*;?/g, "").trim();
		const extra = { class: classes || null, style: style || null };
		return attrs(el, extra, new Set(["class", "style"]));
	};

	const state = (el) => {
		const s = {};
		if (el.scrollTop || el.scrollLeft) s["data-gl-scroll"] = `${el.scrollLeft},${el.scrollTop}`;
		if (el.matches?.(":popover-open")) s["data-gl-popover"] = "";
		if (el.tagName === "DIALOG" && el.matches?.(":modal")) s["data-gl-modal"] = "";
		if (el === el.getRootNode().activeElement && el !== document.body) s["data-gl-focus"] = "";
		return s;
	};

	const children = async (node, base) => (await Promise.all([...node.childNodes].map((c) => walk(c, base)))).join("");

	const iframe = async (el, base, extra) => {
		let inner = null;
		try { inner = el.contentDocument; } catch {}
		if (inner?.documentElement) {
			stats.frames += 1;
			return `<iframe${attrs(el, { ...extra, srcdoc: await documentHtml(inner, inner.URL === "about:blank" ? base : inner.URL) }, new Set(["src", "srcdoc", "sandbox"]))}></iframe>`;
		}
		stats.framesLost += 1; // cross-origin: keep the box, not the content
		return `<iframe${attrs(el, { ...extra, "data-gl-lost": el.src || "" }, new Set(["src", "srcdoc", "sandbox"]))}></iframe>`;
	};

	// a <link> that loads nothing but still answers selectors (site styles detect by link[href^=…])
	const inert = (el) => `<link rel="gl-frozen" href="${escAttr(el.href)}">`;

	const element = async (el, base) => {
		const tag = el.tagName;
		if (DROP.has(tag) || OWN_TAGS.has(tag) || OWN_IDS.has(el.id)) return "";
		if (tag === "LINK" && el.dataset.tzFile !== undefined) return "";
		if (tag === "META" && /^(content-security-policy|refresh)$/i.test(el.httpEquiv)) return "";
		const name = el.localName, extra = state(el);
		if (tag === "LINK" && /stylesheet/i.test(el.rel)) {
			if (el.disabled || !el.sheet) return inert(el);
			return `${inert(el)}${styleTag(await sheetText(el.sheet, el.href), attrs(el, extra, new Set(["rel", "href", "crossorigin", "as", "type"])), el.getRootNode() !== el.ownerDocument)}`;
		}
		if (tag === "LINK") return inert(el);
		if (tag === "STYLE") return styleTag(el.sheet ? await sheetText(el.sheet, base) : el.textContent, attrs(el, extra), el.getRootNode() !== el.ownerDocument);
		if (tag === "IFRAME" || tag === "FRAME") return iframe(el, base, extra);
		if (tag === "CANVAS") {
			stats.canvases += 1;
			let src = null;
			try { src = el.toDataURL(); } catch {}
			const r = el.getBoundingClientRect();
			return `<img${attrs(el, { ...extra, src, width: el.getAttribute("width") ?? Math.round(r.width), height: el.getAttribute("height") ?? Math.round(r.height), "data-gl-canvas": "" }, new Set(["src"]))}>`;
		}
		if (tag === "AUDIO") return "";
		if (tag === "VIDEO") { // a still of the current frame at its real size: an unsized <video> collapses the layout around it
			const r = el.getBoundingClientRect();
			let poster = el.poster ? await inline(el.poster, base) : null;
			try {
				const c = el.ownerDocument.createElement("canvas");
				c.width = el.videoWidth; c.height = el.videoHeight;
				c.getContext("2d").drawImage(el, 0, 0);
				poster = put(c.toDataURL("image/jpeg", 0.8));
			} catch {}
			const size = `width:${Math.round(r.width)}px;height:${Math.round(r.height)}px;`;
			extra.style = `${el.getAttribute("style") ?? ""};${size}`;
			return `<video${attrs(el, { ...extra, poster, "data-gl-media": "" }, new Set(["src", "autoplay", "poster"]))}></video>`;
		}
		if (tag === "SOURCE") return "";
		if (tag === "IMG") {
			extra.src = await inline(el.currentSrc || el.src, base);
			return `<img${attrs(el, extra, new Set(["src", "srcset", "sizes"]))}>`;
		}
		if (tag === "INPUT") {
			if (el.type !== "password" && el.type !== "file" && el.value) extra.value = el.value;
			if (el.checked) extra.checked = true;
			return `<input${attrs(el, extra, new Set(["value", "checked"]))}>`;
		}
		if (tag === "TEXTAREA") return `<textarea${attrs(el, extra)}>${esc(el.value)}</textarea>`;
		if (tag === "OPTION") {
			if (el.selected) extra.selected = true;
			return `<option${attrs(el, extra, new Set(["selected"]))}>${esc(el.textContent)}</option>`;
		}
		if (el.namespaceURI === "http://www.w3.org/2000/svg" && (tag === "image" || tag === "use")) {
			const h = el.getAttribute("href") ?? el.getAttribute("xlink:href");
			if (tag === "image" && h) {
				extra.href = await inline(h, base);
				return `<${name}${attrs(el, extra, new Set(["href", "xlink:href"]))}></${name}>`;
			}
		}
		if (el.hasAttribute("style")) {
			extra.style = await cssAssets(el.getAttribute("style"), base);
		}
		const open = `<${name}${el === el.ownerDocument.documentElement ? rootAttrs(el) : attrs(el, extra)}`;
		if (VOID.has(name)) return `${open}>`;
		const root = el.openOrClosedShadowRoot ?? el.shadowRoot;
		let shadow = "";
		if (root) {
			stats.shadows += 1;
			if (!el.shadowRoot) stats.closedShadows += 1;
			shadow = `<template shadowrootmode="open">${await adopted(root, base, true)}${await children(root, base)}</template>`;
		}
		return `${open}>${shadow}${await children(el, base)}</${name}>`;
	};

	const walk = (node, base) => {
		if (node.nodeType === Node.TEXT_NODE) return /^(style|xmp|plaintext)$/i.test(node.parentNode?.nodeName ?? "") ? node.data : esc(node.data);
		if (node.nodeType === Node.ELEMENT_NODE) return element(node, base);
		return "";
	};

	// runs on load in the frozen page: restores what the DOM alone can't say (top layer, scroll, focus)
	const RESTORE = `<script data-gl-restore>addEventListener("load",()=>{for(const d of document.querySelectorAll("dialog[data-gl-modal]")){d.removeAttribute("open");try{d.showModal()}catch{}}
for(const p of document.querySelectorAll("[data-gl-popover]")){try{p.showPopover()}catch{}}
for(const s of document.querySelectorAll("[data-gl-scroll]")){const[x,y]=s.dataset.glScroll.split(",");s.scrollTo(+x,+y)}
const f=document.querySelector("[data-gl-focus]");f?.focus({preventScroll:true});
document.documentElement.dataset.glReady="1"});</script>`;

	const documentHtml = async (doc, base) => {
		const el = doc.documentElement;
		let inner = await children(el, base);
		const styles = await adopted(doc, base, false);
		const marker = "</head>";
		inner = inner.includes(marker) ? inner.replace(marker, `${styles}${RESTORE}${marker}`) : `${styles}${RESTORE}${inner}`;
		const xy = doc.defaultView.scrollX || doc.defaultView.scrollY ? ` data-gl-scroll="${doc.defaultView.scrollX},${doc.defaultView.scrollY}"` : "";
		return `<!doctype html><html${rootAttrs(el)}${xy}>${inner}</html>`;
	};

	window.__glFreeze = async () => {
		const started = performance.now();
		stats = NEW_STATS(); assets = new Map(); table = {}; sheetsByText = new Map(); sheetTexts = new WeakMap();
		const html = await documentHtml(document, document.baseURI);
		return {
			url: location.href, host: location.hostname, html, assets: table,
			viewport: [innerWidth, innerHeight], dpr: devicePixelRatio,
			scheme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
			glass: document.documentElement.dataset.tzGlass ?? null,
			alpha: document.documentElement.style.getPropertyValue("--tz-glass-alpha") || null,
			stats: { ...stats, ms: Math.round(performance.now() - started), bytes: html.length },
		};
	};
})();
