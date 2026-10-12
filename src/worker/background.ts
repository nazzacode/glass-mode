import type { Browser, Runtime } from "webextension-polyfill-ts";
import type { Message } from "../types/Message";
import { hudText, nextTheme, serial, stepOpacity } from "../shared/Glass";
import { sendMessageToAllTabs } from "../shared/MessageHelper";
import { BROWSER_STORAGE_KEY, loadSettings } from "../shared/StorageHelper";
import { DEFAULT_SETTINGS } from "../shared/Constants";

declare const browser: Browser;

// keyboard glass control (Alt+Shift+↑/↓/G, sent by the content script): works in every window incl. web apps, whose
// toolbar (and popup) is hidden. Settings are global → every tab follows; the sending page applies the reply + shows the HUD.
const glassCommand = serial(async (command: string) => { // serial: held keys → every step lands, in order
	const s = { ...DEFAULT_SETTINGS, ...(await loadSettings()) };
	if (command === "glass-mode") {
		s.glassTheme = nextTheme(s.glassThemeV2 ? (s.glassTheme ?? "auto") : "auto");
		s.glassThemeV2 = true;
		sendMessageToAllTabs({ action: "changeGlassTheme", value: s.glassTheme });
	} else {
		s.glassOpacity = stepOpacity(s.glassOpacity, command === "glass-more" ? 1 : -1);
		sendMessageToAllTabs({ action: "changeGlassOpacity", value: s.glassOpacity });
	}
	await browser.storage.local.set({ [BROWSER_STORAGE_KEY]: s });
	const text = hudText(command === "glass-mode" ? { theme: s.glassTheme } : { opacity: s.glassOpacity });
	return { theme: s.glassTheme, opacity: s.glassOpacity, text };
});

browser.runtime.onMessage.addListener((message: Message, sender: Runtime.MessageSender) => {
	// from a page → that tab only; from popup/settings (extension page) → every matching tab
	const fromPage = !sender.url?.startsWith("moz-extension://");
	const tabId = sender.tab?.id;
	switch (message.action) {
		case "glassCommand":
			return glassCommand(message.value as string);

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
