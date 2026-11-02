// hotkey → freeze.js in the tab → one JSON in Downloads/glass-corpus (`./glasslab corpus import` picks it up). Nothing leaves the machine.
const DELAY_MS = 3000;

async function record(tab) {
	const started = new Date().toISOString();
	const shot = await browser.tabs.captureVisibleTab(tab.windowId, { format: "png" }).catch(() => null); // what the eye saw, before the walk can disturb anything
	await browser.tabs.executeScript(tab.id, { file: "freeze.js" });
	const [frozen] = await browser.tabs.executeScript(tab.id, { code: "window.__glFreeze()" });
	const stem = `${started.replace(/[:.]/g, "-")}-${new URL(tab.url).hostname}`;
	const blob = new Blob([JSON.stringify({ ...frozen, shot, recorded: started, title: tab.title })], { type: "application/json" });
	const url = URL.createObjectURL(blob);
	await browser.downloads.download({ url, filename: `glass-corpus/${stem}.json`, saveAs: false, conflictAction: "uniquify" });
	setTimeout(() => URL.revokeObjectURL(url), 60000);
}

const run = async (delayed) => {
	const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
	if (delayed) await new Promise((r) => setTimeout(r, DELAY_MS));
	try {
		await record(tab);
	} catch (e) {
		console.error("glass-recorder:", tab.url, e);
	}
};

browser.commands.onCommand.addListener((command) => run(command === "record-delayed"));
browser.browserAction.onClicked.addListener(() => run(true)); // the click may close the panel: 3 s to reopen it
// the only senders are this extension's content scripts, and the daily build has none: the lab hook, testing the save path
browser.runtime.onMessage.addListener((m) => (m === "commands" ? browser.commands.getAll() : run(false)));
