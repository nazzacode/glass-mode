// auto glass engine: measures painted boxes + text in the page, applies classify.ts decisions as data attributes that
// styles/shared/auto-glass.css maps onto glass.css tiers. One pass at start, then only mutated subtrees.
import { type Rgb, type Rgba, type Tier, classify, contentFirst, inkFor, inkRanks, neutral, parseColor, statusInk } from "./classify";

const SKIP = new Set(["SCRIPT", "STYLE", "LINK", "META", "NOSCRIPT", "TEMPLATE", "IMG", "VIDEO", "CANVAS", "IFRAME", "SVG", "PICTURE", "svg"]);
const POPUP = "dialog, [popover], [role=dialog], [role=alertdialog], [role=menu], [role=listbox], [role=tooltip]";
const WATCH = ["class", "style", "hidden", "open", "aria-expanded", "aria-hidden"];

const own = (el: HTMLElement, cs: CSSStyleDeclaration): Rgba | null => {
	// the site's colour, remembered across re-walks (after classification the computed colour is ours)
	if (el.dataset.tzBg !== undefined) return el.dataset.tzBg ? (JSON.parse(el.dataset.tzBg) as Rgba) : null;
	const c = parseColor(cs.backgroundColor);
	el.dataset.tzBg = c ? JSON.stringify(c) : "";
	return c;
};
const rgb = (c: string): Rgb | null => {
	const p = parseColor(c);
	return p ? [p[0], p[1], p[2]] : null;
};

export class AutoGlass {
	private base: Rgb = [255, 255, 255];
	private inks = new Map<string, string>(); // site text colour → ink
	private queue = new Set<Element>();
	private chars = { page: 0, pane: 0 }; // text characters without / with a pane under them (first pass)
	private observer?: MutationObserver;

	start(): number {
		const t0 = performance.now();
		const root = document.documentElement;
		root.classList.add("tz-initialized", "tz-auto");
		this.base = rgb(getComputedStyle(document.body).backgroundColor) ?? rgb(getComputedStyle(root).backgroundColor) ?? [255, 255, 255];
		this.chars = { page: 0, pane: 0 };
		this.process(document.body);
		if (contentFirst(this.chars)) root.style.setProperty("--g-body", "var(--g-content-abs)");
		// UI shown by stylesheet/animation changes produces no mutation (cookie banners, lazy panels) → two cheap re-scans
		for (const ms of [1500, 4000]) setTimeout(() => this.observer && this.process(document.body), ms);
		this.observer = new MutationObserver((ms) => {
			// observer callbacks are already batched per microtask; rAF would stall in background/headless tabs
			for (const m of ms) this.queue.add(m.target as Element);
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
		document.documentElement.classList.remove("tz-auto");
		document.documentElement.style.removeProperty("--g-body");
		for (const el of document.querySelectorAll<HTMLElement>("[data-tz-tier], [data-tz-ink], [data-tz-bg]")) {
			delete el.dataset.tzTier;
			delete el.dataset.tzInk;
			delete el.dataset.tzBg;
		}
	}

	private flush(): void {
		const roots = [...this.queue].filter((e) => e.isConnected);
		this.queue.clear();
		this.observer?.takeRecords();
		for (const r of roots.filter((r) => !roots.some((o) => o !== r && o.contains(r)))) this.process(r);
		this.observer?.takeRecords(); // our own attribute writes aren't site mutations
	}

	private process(root: Element): void {
		const ctx = this.context(root);
		this.walk(root, ctx.tier, ctx.bg, ctx.keep);
	}

	/** nearest classified ancestor of a re-walked subtree */
	private context(root: Element): { tier: Tier | "page"; bg: Rgba; keep: boolean } {
		let tier: Tier | "page" = "page", bg: Rgba = [...this.base, 1] as Rgba, keep = false;
		for (let e = root.parentElement; e; e = e.parentElement) {
			const t = (e as HTMLElement).dataset?.tzTier as Tier | undefined;
			if (t === "keep") keep = true;
			if (t && t !== "clear" && tier === "page") {
				tier = t;
				bg = JSON.parse((e as HTMLElement).dataset.tzBg || "null") ?? bg;
			}
		}
		return { tier, bg, keep };
	}

	private walk(el: Element, parentTier: Tier | "page", parentBg: Rgba, inKeep: boolean): void {
		if (SKIP.has(el.tagName) || !(el instanceof HTMLElement)) return;
		const cs = getComputedStyle(el);
		if (cs.display === "none") {
			delete el.dataset.tzTier; // re-classified with real geometry when shown (attribute mutation)
			return;
		}
		let tier = parentTier, bg = parentBg, keep = inKeep;
		const image = cs.backgroundImage !== "none";
		const own_ = own(el, cs);
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
		const key = el.dataset.tzFg ?? cs.color;
		el.dataset.tzFg = key;
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
