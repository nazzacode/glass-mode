// auto glass classifier: pure decisions from measured features (node --test)
import assert from "node:assert/strict";
import { test } from "node:test";
import { type Box, classify, inkFor, inkRanks, neutral, parseColor, statusInk } from "./classify.ts";

const VW = 1400, VH = 1000;
const box = (o: Partial<Box>): Box => ({ bg: [255, 255, 255, 1], w: 300, h: 200, floating: false, page: false, parentTier: "page", parentBg: [240, 242, 245, 1], ...o });

test("parseColor", () => {
	assert.deepEqual(parseColor("rgb(1, 2, 3)"), [1, 2, 3, 1]);
	assert.deepEqual(parseColor("rgba(1, 2, 3, 0.5)"), [1, 2, 3, 0.5]);
	assert.equal(parseColor("transparent"), null);
	assert.equal(parseColor("rgba(0, 0, 0, 0)"), null);
});

test("neutral = low chroma", () => {
	assert.ok(neutral([240, 242, 245, 1]));
	assert.ok(!neutral([24, 119, 242, 1]));
});

test("page backgrounds and full-bleed wrappers go clear (body carries the frame tint)", () => {
	assert.equal(classify(box({ page: true }), VW, VH), "clear");
	assert.equal(classify(box({ w: VW, h: VH }), VW, VH), "clear");
});

test("narrow tall chrome (sidebar) and bars go clear = frame", () => {
	assert.equal(classify(box({ w: 240, h: 944 }), VW, VH), "clear");
	assert.equal(classify(box({ w: VW, h: 56 }), VW, VH), "clear");
});

test("panes and cards on the page = content layer; a card inside content = fill; same colour as parent = clear", () => {
	assert.equal(classify(box({ w: 760, h: 600 }), VW, VH), "content");
	assert.equal(classify(box({ w: 760, h: 250 }), VW, VH), "content");
	assert.equal(classify(box({ w: 700, h: 180, parentTier: "content", parentBg: [240, 242, 245, 1] }), VW, VH), "fill");
	assert.equal(classify(box({ w: 700, h: 180, parentTier: "content", parentBg: [255, 255, 255, 1] }), VW, VH), "clear");
});

test("floating surfaces are popovers (but fixed bars/sidebars are chrome); their insides don't stack glass", () => {
	assert.equal(classify(box({ floating: true, w: 220, h: 140 }), VW, VH), "popover");
	assert.equal(classify(box({ floating: true, w: VW, h: 56 }), VW, VH), "clear");
	assert.equal(classify(box({ w: 200, h: 30, parentTier: "popover", parentBg: [255, 255, 255, 1] }), VW, VH), "clear");
});

test("scrims (translucent full-screen overlays) stay scrims", () => {
	assert.equal(classify(box({ floating: true, w: VW, h: VH, bg: [255, 255, 255, 0.8] }), VW, VH), "scrim");
});

test("brand / data colours are kept; small neutral controls become fills", () => {
	assert.equal(classify(box({ bg: [24, 119, 242, 1], w: 120, h: 36 }), VW, VH), "keep");
	assert.equal(classify(box({ bg: [228, 230, 235, 1], w: 100, h: 36 }), VW, VH), "fill");
});

test("ink ranks: contrast distance from the page's own background, any polarity", () => {
	const light = inkRanks([[28, 30, 33], [101, 103, 107], [138, 141, 145]], [240, 242, 245]);
	assert.deepEqual(light, [1, 2, 3]);
	const dark = inkRanks([[230, 230, 230], [150, 150, 150]], [20, 20, 20]);
	assert.deepEqual(dark, [1, 2]);
});

test("chromatic text → nearest status ink by hue", () => {
	assert.equal(statusInk([0, 100, 209]), "blue");
	assert.equal(statusInk([200, 30, 30]), "red");
	assert.equal(statusInk([30, 140, 60]), "green");
	assert.equal(statusInk([107, 78, 0]), "orange");
});

test("bar/sidebar shapes are chrome only at page level (a wide short code block in a card is a fill)", () => {
	assert.equal(classify(box({ w: 700, h: 44, bg: [246, 248, 250, 1], parentTier: "content", parentBg: [255, 255, 255, 1] }), VW, VH), "fill");
});

test("ink on thin glass: frame text moves up one rank; small text never gets the tertiary ink", () => {
	assert.equal(inkFor(2, "page", 15), 1);
	assert.equal(inkFor(3, "clear", 20), 2);
	assert.equal(inkFor(3, "content", 13), 2);
	assert.equal(inkFor(3, "content", 18), 3);
	assert.equal(inkFor(2, "popover", 13), 2);
});
