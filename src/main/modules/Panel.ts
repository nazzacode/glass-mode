// The glass panel (Alt+Shift+G): opacity slider + Auto/Dark/Light + report link, inside the page. It exists because
// web-app windows have no toolbar, so the popup can't be reached there. Shadow DOM: the site's CSS can't touch it.
import { type GlassTheme, OPACITY } from "../../shared/Glass";

const TAG = "tz-glass-panel";
type State = { opacity: number; theme: GlassTheme; report: string; reportLabel: string };
type Change = { opacity?: number; theme?: GlassTheme };

const CSS = `
:host { all: initial; position: fixed; z-index: 2147483647; top: 16px; right: 16px; font: 13px/1.4 system-ui, sans-serif; }
.card { width: 260px; padding: 14px 16px 12px; border-radius: 10px; display: grid; gap: 10px; color: var(--fg);
  background: var(--bg); backdrop-filter: blur(24px) saturate(160%); border: 1px solid var(--rim);
  box-shadow: 0 12px 32px rgba(0,0,0,.28), inset 0 1px 0 var(--sheen); }
:host([data-mode=dark]) { --fg: #f2f2f5; --muted: #a8a8b0; --bg: rgba(30,30,34,.86); --rim: rgba(255,255,255,.1); --sheen: rgba(255,255,255,.08); --seg: rgba(255,255,255,.07); --on: rgba(10,132,255,.35); }
:host([data-mode=light]) { --fg: #1c1c1e; --muted: #55555c; --bg: rgba(250,250,252,.9); --rim: rgba(255,255,255,.8); --sheen: rgba(255,255,255,.7); --seg: rgba(0,0,0,.05); --on: rgba(0,122,255,.16); }
.head { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
button { all: unset; cursor: pointer; }
.x { color: var(--muted); padding: 0 4px; }
label { display: flex; justify-content: space-between; color: var(--muted); }
input { width: 100%; accent-color: #0a84ff; margin: 0; }
.seg { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; padding: 2px; border-radius: 7px; background: var(--seg); }
.seg button { text-align: center; padding: 4px 0; border-radius: 5px; }
.seg button[aria-pressed=true] { background: var(--on); font-weight: 600; }
.foot { display: flex; justify-content: space-between; color: var(--muted); font-size: 12px; }
a { color: inherit; }
`;

let host: HTMLElement | null = null;

const render = (root: ShadowRoot, s: State) => {
	(root.querySelector("input") as HTMLInputElement).value = String(s.opacity);
	(root.querySelector(".val") as HTMLElement).textContent = `${s.opacity}%`;
	for (const b of root.querySelectorAll<HTMLElement>("[data-theme]")) b.setAttribute("aria-pressed", String(b.dataset.theme === s.theme));
	const a = root.querySelector("a") as HTMLAnchorElement;
	a.href = s.report;
	a.textContent = s.reportLabel;
};

const build = (onChange: (c: Change) => Promise<State>) => {
	const el = document.createElement(TAG);
	const root = el.attachShadow({ mode: "open" });
	const style = document.createElement("style");
	style.textContent = CSS;
	const card = document.createElement("div");
	card.className = "card";
	const node = (tag: string, props: Record<string, string> = {}, text = "") => {
		const n = document.createElement(tag);
		for (const [k, v] of Object.entries(props)) n.setAttribute(k, v);
		n.textContent = text;
		return n;
	};
	const head = node("div", { class: "head" }, "Glass");
	const close = node("button", { class: "x", "aria-label": "Close" }, "×");
	head.append(close);
	const lab = node("label");
	lab.append(node("span", {}, "Opacity"), node("span", { class: "val" }));
	const slider = node("input", { type: "range", min: String(OPACITY.min), max: String(OPACITY.max), step: String(OPACITY.step), "aria-label": "Opacity" });
	const seg = node("div", { class: "seg", role: "group", "aria-label": "Mode" });
	for (const t of ["auto", "dark", "light"]) seg.append(node("button", { "data-theme": t }, t[0].toUpperCase() + t.slice(1)));
	const foot = node("div", { class: "foot" });
	foot.append(node("a", { target: "_blank", rel: "noopener" }), node("span", {}, "Alt+Shift+↑↓"));
	card.append(head, lab, slider, seg, foot);
	root.append(style, card);
	const apply = async (c: Change) => render(root, await onChange(c));
	slider.addEventListener("input", () => apply({ opacity: Number((slider as HTMLInputElement).value) }));
	seg.addEventListener("click", (e) => {
		const t = (e.target as HTMLElement).dataset?.theme as GlassTheme | undefined;
		if (t) apply({ theme: t });
	});
	close.addEventListener("click", () => hide());
	return el;
};

const onKey = (e: KeyboardEvent) => {
	if (e.key === "Escape") hide();
};

export const hide = (): void => {
	if (!host || host.hidden) return;
	host.hidden = true;
	removeEventListener("keydown", onKey, true);
};

/** open (or close) the panel; mode = the glass mode in effect (panel matches it), state = current settings */
export const togglePanel = (state: State, mode: "dark" | "light", onChange: (c: Change) => Promise<State>): void => {
	if (host && !host.hidden) return hide();
	host ??= build(onChange);
	if (!host.isConnected) document.documentElement.append(host);
	host.dataset.mode = mode;
	render(host.shadowRoot as ShadowRoot, state);
	host.hidden = false;
	addEventListener("keydown", onKey, true);
};

export const panelMode = (mode: "dark" | "light"): void => {
	if (host) host.dataset.mode = mode;
};
