// unit tests for the glass control logic (node --test, no deps): npm run test:unit
import assert from "node:assert/strict";
import { test } from "node:test";
import { OPACITY, REPO, hudText, issueUrl, nextTheme, stepOpacity } from "./Glass.ts";

test("opacity steps by 5 within the slider range", () => {
	assert.equal(stepOpacity(45, +1), 50);
	assert.equal(stepOpacity(45, -1), 40);
	assert.equal(stepOpacity(OPACITY.max, +1), OPACITY.max);
	assert.equal(stepOpacity(OPACITY.min, -1), OPACITY.min);
	assert.equal(stepOpacity(undefined, +1), OPACITY.default + OPACITY.step);
	assert.equal(stepOpacity(47, +1), 50); // snaps to the grid
});

test("theme cycles auto → dark → light → auto", () => {
	assert.equal(nextTheme("auto"), "dark");
	assert.equal(nextTheme("dark"), "light");
	assert.equal(nextTheme("light"), "auto");
});

test("hud text", () => {
	assert.equal(hudText({ opacity: 55 }), "Glass 55%");
	assert.equal(hudText({ theme: "auto" }), "Glass: Auto");
	assert.equal(hudText({ theme: "light" }), "Glass: Light");
});

test("issue links prefill the GitHub form for this site", () => {
	const u = new URL(issueUrl("site-bug", { host: "web.whatsapp.com", url: "https://web.whatsapp.com/", version: "1.0.0", theme: "dark", opacity: 45 }));
	assert.equal(u.origin + u.pathname, `https://github.com/${REPO}/issues/new`);
	assert.equal(u.searchParams.get("template"), "site-bug.yml");
	assert.equal(u.searchParams.get("site"), "web.whatsapp.com");
	assert.match(u.searchParams.get("title") ?? "", /web\.whatsapp\.com/);
	assert.match(u.searchParams.get("setup") ?? "", /dark.*45%.*1\.0\.0/);
	const r = new URL(issueUrl("site-request", { host: "example.com", url: "https://example.com/app" }));
	assert.equal(r.searchParams.get("template"), "site-request.yml");
	assert.equal(r.searchParams.get("url"), "https://example.com/app");
});
