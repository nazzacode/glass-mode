// glass keyboard shortcuts — content-script only. Lives here, not in shared/Glass.ts: anything the content script
// imports from a module the popup/background also import becomes a shared chunk, and content scripts can't import
// chunks (tools/glasslab/tests/test_build.py).
type KeyLike = { altKey: boolean; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; code: string; target: unknown };
const KEYS: Record<string, string> = { ArrowUp: "glass-more", ArrowDown: "glass-less", KeyG: "glass-mode" };

/** Alt+Shift+↑/↓ opacity, Alt+Shift+G mode → command; never in code editors (textarea = Monaco, contenteditable =
 *  CodeMirror: there Alt+Shift+↑/↓ moves/copies lines) */
export const glassKey = (e: KeyLike): string | undefined => {
	const t = e.target as { tagName?: string; isContentEditable?: boolean } | null;
	if (!e.altKey || !e.shiftKey || e.ctrlKey || e.metaKey || t?.isContentEditable || t?.tagName === "TEXTAREA") return undefined;
	return KEYS[e.code];
};
