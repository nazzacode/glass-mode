// glass control logic shared by popup, keyboard commands (background) and the in-page HUD. Pure → src/shared/Glass.test.ts
export type GlassTheme = "auto" | "dark" | "light";

export const REPO = "nazzacode/glass-mode"; // issues, releases, docs — the one place to change on a rename
export const OPACITY = { min: 10, max: 90, step: 5, default: 45 } as const;

const clamp = (v: number) => Math.min(OPACITY.max, Math.max(OPACITY.min, v));
export const clampOpacity = (v: number): number => clamp(Math.round(v / OPACITY.step) * OPACITY.step);

/** one keyboard step (±1) on the popup slider's grid */
export const stepOpacity = (current: number | undefined, direction: number): number =>
	clamp(Math.round((current ?? OPACITY.default) / OPACITY.step) * OPACITY.step + Math.sign(direction) * OPACITY.step);

/** the off switches: glass off everywhere, or off for this host → no site style, no auto glass, page opaque as in any browser */
export type Switches = { glassEnabled?: boolean; offDomains?: Array<string> };
export const glassOff = (s: Switches | null | undefined, host: string): boolean =>
	s?.glassEnabled === false || (s?.offDomains ?? []).includes(host);

/** offDomains with host switched on (removed) or off (added) — new array, no duplicates */
export const withSiteOff = (list: Array<string> | undefined, host: string, off: boolean): Array<string> =>
	off ? [...new Set([...(list ?? []), host])] : (list ?? []).filter((h) => h !== host);

export const nextTheme = (theme: GlassTheme): GlassTheme => ({ auto: "dark", dark: "light", light: "auto" } as const)[theme];

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
export const hudText = ({ opacity, theme }: { opacity?: number; theme?: GlassTheme }): string =>
	theme ? `Glass: ${cap(theme)}` : `Glass ${opacity}%`;

type IssueInfo = { host: string; url: string; version?: string; theme?: string; opacity?: number };

/** GitHub issue form, prefilled (form field ids = query params): .github/ISSUE_TEMPLATE/<kind>.yml */
export const issueUrl = (kind: "site-bug" | "site-request", i: IssueInfo): string => {
	const q = new URLSearchParams({ template: `${kind}.yml`, site: i.host, url: i.url });
	q.set("title", kind === "site-bug" ? `[${i.host}] ` : `Add ${i.host}`);
	if (kind === "site-bug") q.set("setup", `glass ${i.theme ?? "auto"}, opacity ${i.opacity ?? OPACITY.default}%, extension ${i.version ?? "?"}`);
	return `https://github.com/${REPO}/issues/new?${q}`;
};

/** queue async calls: each runs after the previous settles (read-modify-write of settings from repeated keys) */
export const serial = <A, R>(f: (a: A) => Promise<R>) => {
	let last: Promise<unknown> = Promise.resolve();
	return (a: A): Promise<R> => {
		const next = last.then(() => f(a));
		last = next.catch(() => undefined);
		return next;
	};
};
