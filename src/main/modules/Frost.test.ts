// frost rule (node --test): which floating layers get frosted
import assert from "node:assert/strict";
import { test } from "node:test";
import { alphaOf, needsFrost } from "./Frost.ts";

const bar = { alpha: 0, blurred: false, contentBelow: true, hasText: true, share: 0.05 };

test("a clear bar with text over scrolled content frosts", () => assert.equal(needsFrost(bar), true));
test("thin glass still frosts; content-tier glass doesn't", () => {
	assert.equal(needsFrost({ ...bar, alpha: 0.55 }), true);
	assert.equal(needsFrost({ ...bar, alpha: 0.86 }), false);
});
test("already blurred is left alone", () => assert.equal(needsFrost({ ...bar, blurred: true }), false));
test("nothing passing under: a sidebar beside the page stays as styled", () => assert.equal(needsFrost({ ...bar, contentBelow: false }), false));
test("no text of its own: decoration, not a bar", () => assert.equal(needsFrost({ ...bar, hasText: false }), false));
test("page-sized layers are pages or scrims", () => assert.equal(needsFrost({ ...bar, share: 0.8 }), false));
test("alpha parses every computed colour form", () => {
	assert.equal(alphaOf("rgba(22, 22, 26, 0.5)"), 0.5);
	assert.equal(alphaOf("rgb(1, 2, 3)"), 1);
	assert.equal(alphaOf("rgb(1 2 3 / 0.25)"), 0.25);
	assert.equal(alphaOf("transparent"), 0);
});
test("popups frost over unscrolled pages too, but not hint-sized chips", () => {
	assert.equal(needsFrost({ ...bar, popup: true, share: 0.1 }), true);
	assert.equal(needsFrost({ ...bar, popup: true, share: 0.002 }), false);
});
test("popups need near-solid or blur; a bar is fine at content tier", () => {
	assert.equal(needsFrost({ ...bar, popup: true, share: 0.1, alpha: 0.8 }), true);
	assert.equal(needsFrost({ ...bar, popup: true, share: 0.1, alpha: 0.92 }), false);
	assert.equal(needsFrost({ ...bar, alpha: 0.8 }), false);
});
