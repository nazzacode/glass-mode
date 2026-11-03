// see-through layers: a fixed/sticky bar with content sliding beneath, or a popup (menu, listbox, dialog) over the page,
// must frost (content / popover tier + blur), or what's under reads sharp behind its labels. Sites leave headers clear and styles thin them, so this is caught at runtime, not
// per site: after a scroll (or a panel opening) sample the viewport, mark offenders [data-tz-frost]; glass.css styles them.
// Only where glass.css is loaded (a site style or auto glass). Content-script only; the rule itself is pure (needsFrost).
const COLUMNS = 7;
const ROWS = 5; // + rows hugging the top and bottom edges: bars are ~40–64 px, an even grid steps over them
const MIN_ALPHA = 0.75;
const MAX_SHARE = 0.6; // bigger than this is a page or a modal scrim, not a bar
const WAIT_MS = 250;

const POPUP = "[role=menu], [role=listbox], [role=dialog], [role=alertdialog], [role=tooltip], dialog[open], :popover-open";
const MIN_POPUP_SHARE = 0.01; // a hint chip isn't a panel
const MIN_POPUP_ALPHA = 0.9; // a menu over the page holds its own text: YouTube's .8 unblurred dropdown still showed titles through

export type Sample = { alpha: number; blurred: boolean; contentBelow: boolean; hasText: boolean; share: number; popup?: boolean };

export const needsFrost = (s: Sample): boolean =>
	s.contentBelow && s.hasText && !s.blurred && s.share < MAX_SHARE &&
	(s.popup ? s.alpha < MIN_POPUP_ALPHA && s.share >= MIN_POPUP_SHARE : s.alpha < MIN_ALPHA);

export const alphaOf = (color: string): number => {
	const m = color.match(/rgba?\(([^)]+)\)/);
	if (!m) return 0;
	const parts = m[1].split(/[\s,/]+/).filter(Boolean).map(Number.parseFloat);
	return parts.length > 3 ? parts[3] : 1;
};

const floating = (el: Element | null): HTMLElement | null => {
	for (let e = el; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
		const p = getComputedStyle(e).position;
		if (p === "fixed" || p === "sticky") return e as HTMLElement;
	}
	return null;
};

const popupOf = (el: Element | null): HTMLElement | null => (el?.closest(POPUP) as HTMLElement | null) ?? null;

const paints = (e: Element) => /^(IMG|VIDEO|CANVAS|svg)$/.test(e.tagName) || [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent?.trim());

const scrolled = (e: Element) => {
	if ((document.scrollingElement?.scrollTop ?? 0) > 0) return true;
	for (let a = e.parentElement; a; a = a.parentElement) if (a.scrollTop > 0) return true;
	return false;
};

// moves with the page: not floating itself, or floating only inside the same shell as the layer (apps that wrap the
// whole page in one fixed container: YouTube, Reddit)
const inFlow = (e: Element, layer: HTMLElement) => {
	const shell = floating(e);
	return !shell || shell.contains(layer);
};

const sample = (layer: HTMLElement, stack: Element[], popup: boolean): Sample => {
	const mine = stack.filter((e) => layer.contains(e));
	let clear = 1;
	let blurred = false;
	for (let e: Element | null = mine[0] ?? layer; e; e = e === layer ? null : e.parentElement) {
		const s = getComputedStyle(e);
		clear *= 1 - alphaOf(s.backgroundColor);
		if (s.backdropFilter && s.backdropFilter !== "none") blurred = true;
	}
	for (let a = layer.parentElement; a && !blurred; a = a.parentElement) if (getComputedStyle(a).backdropFilter !== "none") blurred = true;
	const r = layer.getBoundingClientRect();
	return {
		alpha: 1 - clear,
		blurred,
		contentBelow: stack.some((e) => !layer.contains(e) && !e.contains(layer) && paints(e) && (popup || (scrolled(e) && inFlow(e, layer)))),
		hasText: !!layer.innerText?.trim(),
		share: (r.width * r.height) / (innerWidth * innerHeight),
		popup,
	};
};

const scan = () => {
	if (!getComputedStyle(document.documentElement).getPropertyValue("--g-blur")) return; // no glass.css on this page
	const ys = [12, 36, ...Array.from({ length: ROWS }, (_, j) => (innerHeight * (j + 1)) / (ROWS + 1)), innerHeight - 36, innerHeight - 12];
	for (let i = 1; i <= COLUMNS; i++) {
		for (const y of ys) {
			const stack = document.elementsFromPoint((innerWidth * i) / (COLUMNS + 1), y);
			const popup = popupOf(stack[0] ?? null);
			const layer = popup ?? floating(stack[0] ?? null);
			if (!layer || layer.hasAttribute("data-tz-frost")) continue; // judged at every point: content may pass under only part of a bar
			if (needsFrost(sample(layer, stack, !!popup))) layer.setAttribute("data-tz-frost", popup ? "popup" : "");
		}
	}
};

export const startFrost = (): void => {
	let timer: ReturnType<typeof setTimeout> | undefined;
	const later = () => {
		clearTimeout(timer);
		timer = setTimeout(scan, WAIT_MS);
	};
	for (const ev of ["scroll", "transitionend", "animationend", "click", "keyup"]) addEventListener(ev, later, { capture: true, passive: true });
};
