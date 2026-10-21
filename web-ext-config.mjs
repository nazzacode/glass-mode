import "dotenv/config";

export default {
	artifactsDir: "builds",
	ignoreFiles: [
		"node_modules/",
		"scripts/",
		"builds/",
		"src/",
		".github/",
		".git/",
		"assets/images/github",
		".gitignore",
		".env",
		"package.json",
		"package-lock.json",
		"README.md",
		"tsconfig.json",
		"vite.config.ts",
		"web-ext-config.mjs",
		"biome.json",
		// not the extension: website, test lab, docs, web-app installer, dev files, source maps
		"site/",
		"tools/",
		"docs/",
		"webapp/",
		"glasslab",
		"shell.nix",
		"pytest.ini",
		"metadata.json",
		"vite.content.config.ts",
		"dist/**/*.map",
		"launch/", // launch drafts (posts, messages): never in the package
	],
	build: {
		overwriteDest: true,
	},
	sign: {
		apiKey: process.env.FIREFOX_API_KEY ?? "",
		apiSecret: process.env.FIREFOX_API_SECRET ?? "",
		channel: process.env.AMO_CHANNEL ?? "unlisted", // v1: signed xpi on GitHub Releases; "listed" = public AMO page (review)
		amoMetadata: "metadata.json",
	},
	run: {
		...(process.env.FIREFOX_EXE_PATH && { firefox: process.env.FIREFOX_EXE_PATH }),
		...(process.env.FIREFOX_PROFILE_PATH && { firefoxProfile: process.env.FIREFOX_PROFILE_PATH }),
		devtools: true,
	},
};
