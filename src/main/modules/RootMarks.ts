// classes the extension puts on <html> (tz-initialized, tz-auto) — SPAs that assign html.className (Discord) wipe them,
// and every glass rule hangs off them. One observer re-adds whatever we own. Content-script only.
const owned = new Set<string>();
let observer: MutationObserver | undefined;

const heal = () => {
	const cl = document.documentElement.classList;
	for (const c of owned) if (!cl.contains(c)) cl.add(c);
};

export const mark = (...classes: string[]): void => {
	for (const c of classes) owned.add(c);
	heal();
	if (!observer) {
		observer = new MutationObserver(heal);
		observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
	}
};

export const unmark = (...classes: string[]): void => {
	for (const c of classes) owned.delete(c);
	document.documentElement.classList.remove(...classes);
};
