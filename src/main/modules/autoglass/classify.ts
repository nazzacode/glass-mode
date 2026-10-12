// auto glass, pure decisions (no DOM): which glass tier a painted box becomes, which ink a text colour becomes.
// Features are measured by engine.ts. Design: docs/research/auto-glass-algorithm.md (surface pass + rank-mapped text).
export type Rgb = [number, number, number];
export type Rgba = [number, number, number, number];
export type Tier = "clear" | "content" | "popover" | "fill" | "scrim" | "keep";
export type Box = {
	bg: Rgba; // the site's own background colour (before glass)
	w: number;
	h: number;
	floating: boolean; // top layer, popup role, or positioned with shadow / z-index
	page: boolean; // <html> / <body>
	parentTier: Tier | "page"; // nearest classified ancestor (clear ones pass their parent's through)
	parentBg: Rgba; // that ancestor's own colour
};

export const parseColor = (c: string): Rgba | null => {
	const m = c.match(/rgba?\(([^)]+)\)/);
	if (!m) return null;
	const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
	const a = p.length > 3 ? p[3] : 1;
	return a > 0.02 ? [p[0], p[1], p[2], a] : null;
};

export const chroma = (c: Rgb | Rgba) => Math.max(c[0], c[1], c[2]) - Math.min(c[0], c[1], c[2]);
export const neutral = (c: Rgb | Rgba) => chroma(c) <= 24; // same line as the test suite's "neutral text"
const near = (a: Rgba, b: Rgba) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]) <= 9;

export const classify = (b: Box, vw: number, vh: number): Tier => {
	if (b.page) return "clear"; // glass.css tints body with the frame tier
	const view = vw * vh, area = b.w * b.h;
	const bar = b.h <= 80 && b.w >= 0.5 * vw, sidebar = b.w <= 0.3 * vw && b.h >= 0.5 * vh;
	if (b.floating && area >= 0.8 * view) return b.bg[3] < 0.95 ? "scrim" : "clear"; // dimming layer vs full-screen shell
	if (!neutral(b.bg)) return "keep"; // brand fills, chips, data colours: the site's own
	const onPage = b.parentTier === "page" || b.parentTier === "clear";
	if (area >= 0.8 * view || (onPage && (bar || sidebar))) return "clear"; // full-bleed wrappers and chrome = frame (body tint)
	if (b.floating) return "popover";
	if (onPage) return area >= 0.02 * view ? "content" : "fill";
	return near(b.bg, b.parentBg) ? "clear" : "fill"; // no glass on glass: same colour as its pane → part of it
};

// APCA-W3 lightness contrast |Lc| (same maths as tools/glasslab/probes/text.js)
const Y = (c: Rgb) => {
	const f = (v: number) => (v / 255) ** 2.4;
	const y = 0.2126729 * f(c[0]) + 0.7151522 * f(c[1]) + 0.072175 * f(c[2]);
	return y > 0.022 ? y : y + (0.022 - y) ** 1.414;
};
export const apca = (text: Rgb, bg: Rgb) => {
	const t = Y(text), b = Y(bg);
	const s = b > t ? (b ** 0.56 - t ** 0.57) * 1.14 : (b ** 0.65 - t ** 0.62) * 1.14;
	return Math.abs(s) < 0.1 ? 0 : (Math.abs(s) - 0.027) * 100;
};

/** text colours → ink 1|2|3 by contrast against the site's own page colour (polarity-free). A new rank starts at each
 *  drop of more than 15 % of the strongest contrast; capped at 3. */
export const inkRanks = (colors: Rgb[], base: Rgb): number[] => {
	const lc = colors.map((c) => apca(c, base));
	const order = [...lc.keys()].sort((i, j) => lc[j] - lc[i]);
	const ranks = new Array<number>(colors.length);
	const step = 0.15 * Math.max(...lc, 1);
	let rank = 1, lead = lc[order[0]];
	for (const i of order) {
		if (lead - lc[i] > step) {
			rank = Math.min(3, rank + 1);
			lead = lc[i];
		}
		ranks[i] = rank;
	}
	return ranks;
};

/** chromatic text (links, status) → the glass status ink of its hue family */
export const statusInk = ([r, g, b]: Rgb): "red" | "orange" | "green" | "blue" | "purple" => {
	const max = Math.max(r, g, b), d = max - Math.min(r, g, b) || 1;
	const h = (max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4) * 60;
	return h < 20 || h >= 330 ? "red" : h < 65 ? "orange" : h < 170 ? "green" : h < 260 ? "blue" : "purple";
};

/** ink for a rank where the text sits: on frame glass (no pane under it) one rank stronger; the tertiary ink only for
 *  large text — floors in glass.css are calibrated for fg-2 labels, fg-3 needs size (APCA Lc45 large-text tier) */
export const inkFor = (rank: number, surface: Tier | "page", px: number): number => {
	const r = surface === "page" || surface === "clear" ? Math.max(1, rank - 1) : rank;
	return r === 3 && px < 16 ? 2 : r;
};
