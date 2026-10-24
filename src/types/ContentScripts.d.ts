export type ContentScripts = {
	supportedWebsites: Array<SupportedWebsite>;
};

export type SupportedWebsite = {
	name: string;
	matches: Array<string>;
	js?: Array<string>;
	css?: Array<string>;
	run_at?: "document_start" | "document_end" | "document_idle";
	favicon?: string;
	glass?: "dark" | "light"; // force a glass mode for this site (e.g. dark-only apps), overrides the popup/auto setting
	detect?: string; // selector: pages on other domains carrying it get this style too (Substack custom domains)
	glassUnless?: string; // selector on <html>: pages of the site matching it keep popup/auto glass (Linear app vs dark-only marketing)
};
