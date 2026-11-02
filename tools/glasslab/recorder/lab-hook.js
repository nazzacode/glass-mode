// lab builds only (corpus.lab_xpi): the lab can't press an extension hotkey, so it asks by DOM event. Never in the build installed for daily use.
document.addEventListener("gl-freeze", async () => {
	const frozen = await window.__glFreeze();
	window.wrappedJSObject.__glFrozen = JSON.stringify(frozen);
});
document.addEventListener("gl-record", () => browser.runtime.sendMessage("record"));
document.addEventListener("gl-commands", async () => {
	window.wrappedJSObject.__glCommands = JSON.stringify(await browser.runtime.sendMessage("commands"));
});
