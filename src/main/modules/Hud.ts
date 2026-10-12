// in-page HUD for keyboard glass changes (web-app windows have no toolbar → no popup). Shadow DOM: site CSS can't reach it.
const TAG = "tz-glass-hud";
let timer: number | undefined;

export const showHud = (text: string): void => {
	let host = document.querySelector(TAG) as HTMLElement | null;
	if (!host) {
		host = document.createElement(TAG);
		const root = host.attachShadow({ mode: "open" });
		const style = document.createElement("style");
		style.textContent = `:host { all: initial; position: fixed; z-index: 2147483647; top: 24px; left: 50%; transform: translateX(-50%);
			pointer-events: none; transition: opacity .25s; }
			div { font: 600 14px/1 system-ui, sans-serif; color: #f2f2f5; padding: 10px 18px; border-radius: 999px;
			background: rgba(30, 30, 34, .78); backdrop-filter: blur(24px) saturate(160%); box-shadow: 0 10px 30px rgba(0,0,0,.28),
			inset 0 1px 0 rgba(255,255,255,.08); }`;
		root.append(style, document.createElement("div"));
		document.documentElement.append(host);
	}
	host.dataset.text = text;
	(host.shadowRoot?.querySelector("div") as HTMLElement).textContent = text;
	host.style.opacity = "1";
	clearTimeout(timer);
	timer = window.setTimeout(() => {
		if (host) host.style.opacity = "0";
	}, 1200);
};
