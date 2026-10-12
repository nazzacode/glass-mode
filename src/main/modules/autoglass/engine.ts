// auto glass engine: measures painted boxes + text in the page, applies classify.ts decisions as data attributes that
// styles/shared/auto-glass.css maps onto glass.css tiers. One pass at start, then only mutated subtrees.
import { mark, unmark } from "../RootMarks";
import { type Rgb, type Rgba, type Tier, classify, contentFirst, inkFor, inkRanks, neutral, parseColor, statusInk } from "./classify";

const SKIP = new Set(["SCRIPT", "STYLE", "LINK", "META", "NOSCRIPT", "TEMPLATE", "IMG", "VIDEO", "CANVAS", "IFRAME", "SVG", "PICTURE", "svg"]);
const POPUP = "dialog, [popover], [role=dialog], [role=alertdialog], [role=menu], [role=listbox], [role=tooltip]";
const WATCH = ["class", "style", "hidden", "open", "aria-expanded", "aria-hidden"];

// computed colours may be oklch()/lab()/color() (Firefox keeps them; Tailwind v4 default) → sRGB via a 1×1 canvas, cached
let ctx: CanvasRenderingContext2D | null | undefined;
const converted = new Map<string, Rgba | null>();
export const toRgba = (c: string): Rgba | null => {
	if (c === "transparent" || /^rgba?\(/.test(c)) return parseColor(c);
	if (converted.has(c)) return converted.get(c) ?? null;
	if (ctx === undefined) {
		const cv = document.createElement("canvas");
		cv.width = cv.height = 1;
		ctx = cv.getContext("2d", { willReadFrequently: true });
	}
	let out: Rgba | null = null;
	if (ctx) {
		ctx.clearRect(0, 0, 1, 1);
		ctx.fillStyle = c;
		ctx.fillRect(0, 0, 1, 1);
		const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
		out = a > 5 ? [r, g, b, Math.round((a / 255) * 1000) / 1000] : null;
	}
	converted.set(c, out);
	return out;
};
const rgb = (c: string): Rgb | null => {
	const p = toRgba(c);
	return p ? [p[0], p[1], p[2]] : null;
};

// the site's own colours, cached per element until its class/style changes (state classes recolour: re-read then).
// Our marks change the computed colours → lift the mark while reading.
const sig = (el: HTMLElement) => `${el.getAttribute("class") ?? ""}|${el.getAttribute("style") ?? ""}`;
const siteValue = (el: HTMLElement, mark: "tzTier" | "tzInk", read: () => string): string => {
	const held = el.dataset[mark];
	if (held !== undefined) delete el.dataset[mark];
	const v = read();
	if (held !== undefined) el.dataset[mark] = held;
	return v;
};
const own = (el: HTMLElement): Rgba | null => {
	if (el.dataset.tzBg !== undefined && el.dataset.tzSig === sig(el)) return el.dataset.tzBg ? (JSON.parse(el.dataset.tzBg) as Rgba) : null;
	const c = toRgba(siteValue(el, "tzTier", () => getComputedStyle(el).backgroundColor));
	el.dataset.tzBg = c ? JSON.stringify(c) : "";
	el.dataset.tzSig = sig(el);
	return c;
};

export class AutoGlass {
	private base: Rgb = [255, 255, 255];
	private inks = new Map<string, string>(); // site text colour → ink
	private queue = new Set<Element>();
	private walked = 0; // elements walked by the last flush (lab: tzAutoWalked)
	private chars = { page: 0, pane: 0 }; // text characters without / with a pane under them (first pass)
	private observer?: MutationObserver;

	start(): number {
		const t0 = performance.now();
		const root = document.documentElement;
		mark("tz-initialized", "tz-auto");
		this.base = rgb(getComputedStyle(document.body).backgroundColor) ?? rgb(getComputedStyle(root).backgroundColor) ?? [255, 255, 255];
		this.chars = { page: 0, pane: 0 };
		this.process(document.body);
		if (contentFirst(this.chars)) root.style.setProperty("--g-body", "var(--g-content-abs)");
		// UI shown by stylesheet/animation changes produces no mutation (cookie banners, lazy panels) → two cheap re-scans
		for (const ms of [1500, 4000]) setTimeout(() => this.observer && this.process(document.body), ms);
		this.observer = new MutationObserver((ms) => {
			// observer callbacks are already batched per microtask; rAF would stall in background/headless tabs
			// only what changed: added elements (not their whole parent), attribute targets; text → its parent
			for (const m of ms) {
				if (m.type !== "childList") this.queue.add(m.target as Element);
				else for (const n of m.addedNodes) this.queue.add(n.nodeType === 1 ? (n as Element) : (n.parentElement as Element));
			}
			this.flush();
		});
		this.observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: WATCH });
		const ms = performance.now() - t0;
		root.dataset.tzAutoMs = ms.toFixed(1);
		return ms;
	}

	stop(): void {
		this.observer?.disconnect();
		this.observer = undefined;
		unmark("tz-auto");
		document.documentElement.style.removeProperty("--g-body");
		for (const el of document.querySelectorAll<HTMLElement>("[data-tz-tier], [data-tz-ink], [data-tz-bg], [data-tz-fg]")) {
			for (const k of ["tzTier", "tzInk", "tzBg", "tzFg", "tzSig", "tzFgSig"]) delete el.dataset[k];
		}
	}

	private flush(): void {
		// outermost roots only, O(n·depth): shallowest first, skip any whose ancestor is already taken
		const depth = (e: Element) => {
			let d = 0;
			for (let x: Element | null = e; x; x = x.parentElement) d++;
			return d;
		};
		const roots = new Set<Element>();
		for (const e of [...this.queue].filter((e) => e?.isConnected).sort((a, b) => depth(a) - depth(b))) {
			let inside = false;
			for (let x = e.parentElement; x && !inside; x = x.parentElement) inside = roots.has(x);
			if (!inside) roots.add(e);
		}
		this.queue.clear();
		this.walked = 0;
		for (const r of roots) this.process(r);
		document.documentElement.dataset.tzAutoWalked = String(this.walked);
		this.observer?.takeRecords(); // our own attribute writes aren't site mutations
	}

	private process(root: Element): void {
		const ctx = this.context(root);
		this.walk(root, ctx.tier, ctx.bg, ctx.keep);
	}

	/** what walk() would carry into a re-walked subtree: nearest surface ancestor (tier + its colour); keep only if a
	 *  kept surface (image, brand fill) sits between the subtree and that surface — same rules as the first pass */
	private context(root: Element): { tier: Tier | "page"; bg: Rgba; keep: boolean } {
		let keep = false;
		for (let e = root.parentElement; e; e = e.parentElement) {
			const t = (e as HTMLElement).dataset?.tzTier as Tier | undefined;
			if (t === "keep") keep = true;
			else if (t && t !== "clear") return { tier: t, bg: JSON.parse((e as HTMLElement).dataset.tzBg || "null") ?? [...this.base, 1], keep };
		}
		return { tier: "page", bg: [...this.base, 1] as Rgba, keep };
	}

	private walk(el: Element, parentTier: Tier | "page", parentBg: Rgba, inKeep: boolean): void {
		if (SKIP.has(el.tagName) || !(el instanceof HTMLElement)) return;
		this.walked++;
		const cs = getComputedStyle(el);
		if (cs.display === "none") {
			delete el.dataset.tzTier; // re-classified with real geometry when shown (attribute mutation)
			return;
		}
		let tier = parentTier, bg = parentBg, keep = inKeep;
		const image = cs.backgroundImage !== "none";
		const own_ = own(el);
		if (image) {
			el.dataset.tzTier = "keep"; // images and gradients are content: untouched, and so is text drawn on them
			keep = true;
		} else if (own_) {
			const r = el.getBoundingClientRect();
			const floating = el.matches(POPUP) || ((cs.position === "fixed" || cs.position === "absolute") && (cs.boxShadow !== "none" || Number(cs.zIndex) > 0));
			const page = el === document.body;
			const t = classify({ bg: own_, w: r.width, h: r.height, floating, page, parentTier, parentBg }, innerWidth, innerHeight);
			if (!page) el.dataset.tzTier = t; // body keeps glass.css's frame tint
			if (t === "keep") keep = true;
			else if (t !== "clear") {
				tier = t;
				bg = own_;
				keep = false; // a neutral surface on a coloured one resets: its text is ours again
			}
		}
		this.ink(el, cs, keep, tier);
		for (const c of el.children) this.walk(c, tier, bg, keep);
	}

	/** text colour → shared ink (neutral, ranked) or status ink (chromatic); text on kept surfaces stays the site's */
	private ink(el: HTMLElement, cs: CSSStyleDeclaration, keep: boolean, surface: Tier | "page"): void {
		const text = [...el.childNodes].reduce((n, c) => n + (c.nodeType === 3 ? (c.textContent?.trim().length ?? 0) : 0), 0);
		if (keep || !text) return;
		this.chars[surface === "page" || surface === "clear" ? "page" : "pane"] += text;
		const fresh = el.dataset.tzFg === undefined || el.dataset.tzFgSig !== sig(el);
		const key = fresh ? siteValue(el, "tzInk", () => getComputedStyle(el).color) : (el.dataset.tzFg as string);
		el.dataset.tzFg = key;
		el.dataset.tzFgSig = sig(el);
		const ink = this.inks.get(key) ?? this.rank(key);
		el.dataset.tzInk = /^[123]$/.test(ink) ? String(inkFor(Number(ink), surface, Number.parseFloat(cs.fontSize))) : ink;
	}

	private rank(key: string): string {
		const c = rgb(key);
		if (!c) return "1";
		if (!neutral(c)) {
			this.inks.set(key, statusInk(c));
			return this.inks.get(key) as string;
		}
		// re-rank all neutral colours seen so far (ranks are relative); earlier elements keep theirs
		const keys = [...this.inks.keys()].filter((k) => /^[123]$/.test(this.inks.get(k) as string)).concat(key);
		const ranks = inkRanks(keys.map((k) => rgb(k) as Rgb), this.base);
		keys.forEach((k, i) => this.inks.set(k, String(ranks[i])));
		return this.inks.get(key) as string;
	}
}
