import type { Browser, Runtime } from "webextension-polyfill-ts";
import type { Message } from "../types/Message";
import { type GlassTheme, OPACITY, clampOpacity, glassOff, hudText, serial, stepOpacity, withSiteOff } from "../shared/Glass";
import { sendMessageToAllTabs } from "../shared/MessageHelper";
import { BROWSER_STORAGE_KEY, loadSettings } from "../shared/StorageHelper";
import { DEFAULT_SETTINGS } from "../shared/Constants";

declare const browser: Browser;

// glass control from pages: keys (Alt+Shift+↑/↓) and the in-page panel (Alt+Shift+G) — they work in every window incl.
// web apps, whose toolbar (and popup) is hidden. Settings are global → every tab follows; the sender applies the reply.
// change: { step: ±1 } | { opacity } | { theme } | { enabled } | { siteOff } (for the sender's host) | {} (just read
// the state). Serial: held keys → every step lands. The switches only write storage: every tab follows it (refresh()).
type GlassChange = { step?: number; opacity?: number; theme?: GlassTheme; enabled?: boolean; siteOff?: boolean };
const glassChange = serial(async ({ c, host }: { c: GlassChange; host: string }) => {
	const s = { ...DEFAULT_SETTINGS, ...(await loadSettings()) };
	const switched = c.enabled !== undefined || c.siteOff !== undefined;
	if (c.enabled !== undefined) s.glassEnabled = c.enabled;
	if (c.siteOff !== undefined) s.offDomains = withSiteOff(s.offDomains, host, c.siteOff);
	const theme = s.glassThemeV2 ? (s.glassTheme ?? "auto") : "auto";
	if (c.theme && c.theme !== theme) {
		s.glassTheme = c.theme;
		s.glassThemeV2 = true;
		sendMessageToAllTabs({ action: "changeGlassTheme", value: c.theme });
	}
	const opacity = c.step ? stepOpacity(s.glassOpacity, c.step) : c.opacity !== undefined ? clampOpacity(c.opacity) : undefined;
	if (opacity !== undefined && opacity !== s.glassOpacity) {
		s.glassOpacity = opacity;
		sendMessageToAllTabs({ action: "changeGlassOpacity", value: opacity });
	}
	if (c.theme || opacity !== undefined || switched) await browser.storage.local.set({ [BROWSER_STORAGE_KEY]: s });
	const now = {
		theme: (s.glassThemeV2 ? s.glassTheme : "auto") ?? "auto",
		opacity: s.glassOpacity ?? OPACITY.default,
		enabled: s.glassEnabled !== false,
		siteOff: glassOff({ offDomains: s.offDomains }, host),
	};
	return { ...now, text: hudText(c.theme ? { theme: now.theme } : { opacity: now.opacity }) };
});

browser.runtime.onMessage.addListener((message: Message, sender: Runtime.MessageSender) => {
	// from a page → that tab only; from popup/settings (extension page) → every matching tab
	const fromPage = !sender.url?.startsWith("moz-extension://");
	const tabId = sender.tab?.id;
	const host = sender.url ? new URL(sender.url).hostname : "";
	switch (message.action) {
		case "glassCommand": // keys
			return glassChange({ c: { step: message.value === "glass-more" ? 1 : -1 }, host });
		case "glassSet": // panel
			return glassChange({ c: (message.value ?? {}) as GlassChange, host });

		case "insertStyles": {
			if (fromPage && tabId === undefined) return Promise.resolve({ noTab: true });
			if (fromPage && tabId !== undefined) return browser.tabs.insertCSS(tabId, { file: message.filePath, frameId: sender.frameId }).then(() => ({ ok: true }));
			applyStyles(message.filePath, message.domains);
			break;
		}

		case "removeStyles": {
			if (fromPage && tabId !== undefined) browser.tabs.removeCSS(tabId, { file: message.filePath, frameId: sender.frameId });
			else if (!fromPage) removeStyles(message.filePath);
			break;
		}
	}
});

async function applyStyles(filePath?: string, domains?: Array<string>): Promise<void> {
	const tabs = await browser.tabs.query({ currentWindow: true });

	for (const tab of tabs) {
		if (!tab.id || !tab.url) continue;
		if (tab.discarded) continue;
		if (tabs.length > 40 && !tab.active) continue;
		if (domains) {
			for (const domain of domains) {
				const regex = new RegExp(domain);
				if (tab.url && regex.test(tab.url)) {
					browser.tabs.insertCSS(tab.id, { file: filePath });
				}
			}
		} else if (!tab.url.startsWith("moz-extension://")) {
			browser.tabs.insertCSS(tab.id, { file: filePath });
		}
	}
}

async function removeStyles(filePath?: string): Promise<void> {
	const tabs = await browser.tabs.query({ currentWindow: true });

	for (const tab of tabs) {
		browser.tabs.removeCSS(tab.id, { file: filePath });
	}
}
