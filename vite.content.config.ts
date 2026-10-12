import { dirname, resolve } from "node:path";
import { defineConfig } from "vite";

// The content script is a classic script (no ES imports allowed), so it is built on its own as one self-contained IIFE:
// it may import shared modules (src/shared) without them turning into a chunk it can't load (tests/test_build.py).
export default defineConfig({
	root: "src/",
	base: "",
	build: {
		sourcemap: true,
		outDir: resolve(dirname("./"), "dist"), // absolute: relative paths resolve against root (src/) → src/dist
		emptyOutDir: false, // the main build (popup, settings, background) ran first
		lib: {
			entry: resolve(dirname("./"), "src/main/transparent-zen.ts"),
			formats: ["iife"],
			name: "TransparentZen",
			fileName: () => "transparent-zen.js",
		},
		rollupOptions: { output: { assetFileNames: "transparent-zen.[ext]" } },
	},
});
