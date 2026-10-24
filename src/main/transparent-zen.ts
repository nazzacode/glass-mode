import { insertStyles, removeStyles } from "./modules/Styles";
import { showHud } from "./modules/Hud";
import { type GlassTheme, glassOff, issueUrl } from "../shared/Glass";
import { panelMode, togglePanel } from "./modules/Panel";

type GlassReply = { theme: GlassTheme; opacity: number; text: string; enabled: boolean; siteOff: boolean };
import { glassKey } from "./modules/GlassKeys";
import { mark, unmark } from "./modules/RootMarks";
import type { Browser } from "webextension-polyfill-ts";
import type { ContentScripts, SupportedWebsite } from "../types/ContentScripts";
import type { ExtensionSettings, SiteSpecificSetting } from "../types/ExtensionSettings";
import type { Message } from "../types/Message";
import { AutoGlass, toRgba } from "./modules/autoglass/engine";
import { SupportedSite } from "./modules/SupportedSite";
import { WebInspector } from "./modules/WebInspector";
import "./transparent-zen.css";

declare const browser: Browser;

// sites on custom domains (a Substack publication at its own URL): no URL match → look for the platform's fingerprint
// (`detect` selector) once <head> is parsed, i.e. when <body> appears. Unlisted pages wait only that long (hidden anyway).
function detectSite(sites: Array<SupportedWebsite>): Promise<SupportedWebsite | undefined> {
	const detectable = sites.filter((s) => s.detect);
	const found = () => detectable.find((s) => document.querySelector(s.detect as string));
	if (!detectable.length || document.body) return Promise.resolve(found());
	return new Promise((resolve) => {
		const done = () => {
			observer.disconnect();
			document.removeEventListener("DOMContentLoaded", done);
			resolve(found());
		};
		const observer = new MutationObserver(() => (found() || document.body) && done());
		observer.observe(document.documentElement, { childList: true, subtree: true });
		document.addEventListener("DOMContentLoaded", done);
	});
}

class TransparentZen {
	private autoGlass = new AutoGlass();
	private autoOn = false;
	private siteStyle: SupportedWebsite | undefined; // registry entry when this page has a hand-made style
	private siteStyleOn = false;
	private opaque = false;
	private supportedSite: SupportedSite | undefined;
	private webInspector: WebInspector | undefined;
	private transparentZenSettings: ExtensionSettings["transparentZenSettings"] | undefined;
	private siteSpecificSettings: SiteSpecificSetting | null = null;
	private isSupportedWebsite = false;

	constructor() {
		this.applyGlass(); // synchronous first pass (auto → prefers-color-scheme) → no dark flash on a light desktop
		this.initLoadingScreen();
		this.initGlassKeys();
		// biome-ignore format: readability
		this.checkIfWebsiteAlreadySupported().then(contentScript => {
			browser.storage.local.get("transparentZenSettings").then(async (settings) => {
				this.transparentZenSettings = (settings as ExtensionSettings).transparentZenSettings;
				// forced site glass, unless this page is the site's own-theme app (`glassUnless`, matched on <html>: present at document_start)
				const own = contentScript && contentScript.glassUnless && document.documentElement.matches(contentScript.glassUnless);
				this.siteGlass = contentScript && !own ? contentScript.glass : undefined;
				// pre-auto builds persisted "dark" as the default → treat as auto until the user picks in the new popup
				const s = this.transparentZenSettings;
				this.applyGlass(s?.glassThemeV2 ? s.glassTheme : "auto", s?.glassOpacity);
				// every page listens, styled or not, on or off: the popup must reach a page to switch it back on
				this.initBrowserEvents();
				if (!contentScript) {
					console.info("Website is not supported by Glass Mode");
					this.webInspector = new WebInspector(this.transparentZenSettings);
					// lab/test hook (glasslab): same as switching auto glass on for this page
					document.addEventListener("tz-auto-glass", () => {
						this.setAuto(true);
						this.setOpaque(false);
					});
					this.removeLoadingScreen();
				} else {
					console.info("Website is supported by Glass Mode");
					this.siteStyle = contentScript;
					this.supportedSite = new SupportedSite(this.removeLoadingScreen, this.initExtensionSettingsStyles.bind(this));
					await this.supportedSite.initSupportedWebsite();
				}
				this.refresh();
				this.initSiteSpecificSettings();
			}).catch((error) => {
				console.error("Error checking supported websites:", error);
				this.removeLoadingScreen();
			});
		});
	}

	private async checkIfWebsiteAlreadySupported(): Promise<SupportedWebsite | false> {
		const response = await fetch(browser.runtime.getURL("data/ContentScripts.json"));
		if (!response.ok) return false;
		const { supportedWebsites: sites }: ContentScripts = await response.json();
		const url = window.location.href;
		const site = sites.find((s) => s.matches.some((m) => new RegExp(m).test(url))) ?? (await detectSite(sites));
		this.isSupportedWebsite = !!site;
		return site ?? false;
	}

	private applyCustomBackgrounds(): void {
		if (!this.siteSpecificSettings) return;

		if (this.siteSpecificSettings.backgroundSelectors.length) {
			let customStyles = document.getElementById("tz-custom-backgrounds") as HTMLStyleElement | null;
			if (!customStyles) {
				customStyles = document.createElement("style");
				customStyles.id = "tz-custom-backgrounds";
				document.head.append(customStyles);
			}
			customStyles.textContent = `
				${this.siteSpecificSettings.backgroundSelectors.join(",")} {
					background-color: transparent !important;

					&[data-tz-processed] {
						&[data-tz-depth] {
							background-color: transparent !important;
						}
					}
				}`;
		}
	}

	private applyCustomStyles(): void {
		if (!this.siteSpecificSettings) return;

		let customStyles = document.getElementById("tz-custom-styles") as HTMLStyleElement | null;
		if (!customStyles) {
			customStyles = document.createElement("style");
			customStyles.id = "tz-custom-styles";
			document.head.append(customStyles);
		}
		customStyles.textContent = this.siteSpecificSettings.customStyles;
	}

	private removeCustomStyles(): void {
		const customStyles = document.getElementById("tz-custom-styles") as HTMLStyleElement | null;
		customStyles?.remove();
	}

	private initBrowserEvents(): void {
		// every switch (off everywhere / on this site, site-style list, auto glass + its lists) follows storage — one
		// source of truth for every tab in every window; popup and panel only write settings
		browser.storage.onChanged.addListener((changes) => {
			const next = changes.transparentZenSettings?.newValue as ExtensionSettings["transparentZenSettings"] | undefined;
			if (!next) return;
			this.transparentZenSettings = next;
			this.refresh();
		});
		browser.runtime.onMessage.addListener((request: Message) => {
			switch (request.action) {
				case "toggleInspector": {
					if (request.enabled) {
						this.webInspector?.enableInspector();
					} else {
						this.webInspector?.disableInspector();
					}
					break;
				}
				case "getDomain": {
					return Promise.resolve(window.location.hostname);
				}
				case "changePrimaryColor": {
					this.applyCustomProperty("--color-primary", request.value as string);
					break;
				}
				case "changeTextColor": {
					this.applyCustomProperty("--color-text", request.value as string);
					break;
				}
				case "changeBackgroundColor": {
					this.applyCustomProperty("--transparent-background", request.value as string);
					break;
				}
				case "changeBackgroundImage": {
					if (request.value) {
						const backgroundImage = request.value as Blob;
						this.blobToDataURL(backgroundImage).then((dataUrl) => {
							this.applyCustomProperty("--custom-background-image", `url(${dataUrl})`);
							document.documentElement?.classList.add("tz-custom-background");
						});
					} else {
						this.applyCustomProperty("--custom-background-image", "none");
						document.documentElement?.classList.remove("tz-custom-background");
					}
					break;
				}
				case "changeBackgroundImageOpacity": {
					this.applyCustomProperty("--custom-background-image-opacity", ((request.value as number) / 100).toString());
					break;
				}
				case "changeBackgroundImageBlur": {
					this.applyCustomProperty("--custom-background-image-blur", `blur(${request.value}px)`);
					break;
				}
				case "changeGlassTheme": {
					this.applyGlass(request.value as "auto" | "dark" | "light", undefined);
					break;
				}
				case "changeGlassOpacity": {
					this.applyGlass(undefined, request.value as number);
					break;
				}
				case "changeBackgroundImageBrightness": {
					this.applyCustomProperty("--custom-background-image-brightness", `brightness(${(request.value as number) / 100})`);
					break;
				}
				case "changeCustomStyles": {
					if (this.siteSpecificSettings) {
						this.siteSpecificSettings.customStyles = request.value as string;
						this.applyCustomStyles();
					} else {
						browser.storage.local.get("transparentZenSettings").then((settings) => {
							this.transparentZenSettings = settings.transparentZenSettings;
							if (this.transparentZenSettings?.siteSpecificSettings.length) {
								for (const setting of this.transparentZenSettings.siteSpecificSettings) {
									if (setting.domain === window.location.hostname) {
										this.siteSpecificSettings = setting;
										this.applyCustomStyles();
									}
								}
							}
						});
					}
					break;
				}
				case "toggleSiteSpecificSettings": {
					const enabled = request.value as boolean;
					if (enabled) {
						this.applyCustomStyles();
					} else {
						this.removeCustomStyles();
					}
				}
			}
		});
	}

	// Alt+Shift+↑/↓ = glass more/less opaque, Alt+Shift+G = cycle auto/dark/light. A page listener (not manifest commands):
	// web-app windows have no browser chrome, and Zen's own shortcuts can't shadow it. Capture phase, before the site.
	private initGlassKeys(): void {
		window.addEventListener("keydown", (e) => {
			const command = glassKey(e);
			if (!command) return;
			e.preventDefault();
			e.stopPropagation();
			if (command === "glass-panel") return this.openPanel();
			browser.runtime.sendMessage({ action: "glassCommand", value: command }).then((r: GlassReply) => {
				this.applyGlass(undefined, r.opacity);
				showHud(r.text);
			});
		}, true);
	}

	// the glass panel: state from the background (global settings), every change goes through it so all windows follow
	private async openPanel(): Promise<void> {
		const set = async (change: object): Promise<GlassReply> => browser.runtime.sendMessage({ action: "glassSet", value: change });
		const view = (r: GlassReply) => {
			const u = new URL(location.href);
			const kind = this.isSupportedWebsite ? "site-bug" : "site-request";
			return { opacity: r.opacity, theme: r.theme, enabled: r.enabled, siteOff: r.siteOff, host: u.hostname, reportLabel: this.isSupportedWebsite ? "Report a problem" : "Request this site",
				report: issueUrl(kind, { host: u.hostname, url: u.origin, version: browser.runtime.getManifest().version, theme: r.theme, opacity: r.opacity }) };
		};
		const mode = () => (document.documentElement.dataset.tzGlass === "light" ? "light" : "dark");
		togglePanel(view(await set({})), mode(), async (change) => {
			const r = await set(change);
			this.applyGlass(r.theme, r.opacity);
			panelMode(mode());
			return view(r);
		});
	}

	// what this page should show, from the settings; idempotent. Off (everywhere / this site) = the page as in any browser.
	private refresh(): void {
		const s = this.transparentZenSettings;
		const off = glassOff(s, window.location.hostname);
		if (this.siteStyle) {
			const listedOff = (s?.disabledWebsites ?? []).some((w) => w.name === this.siteStyle?.name);
			this.setSiteStyle(!off && !listedOff);
		} else {
			this.setAuto(!off && this.autoAllowed());
		}
		this.setOpaque(!this.siteStyleOn && !this.autoOn);
	}

	private setSiteStyle(on: boolean): void {
		const file = this.siteStyle?.css?.[0];
		if (on === this.siteStyleOn || !file) return;
		this.siteStyleOn = on;
		if (on) insertStyles(file, this.siteStyle?.matches);
		else removeStyles(file);
	}

	// Zen draws pages over the desktop: a page that paints no background of its own (html and body transparent) shows
	// the wallpaper through dark text. Without glass it gets the opaque canvas of any other browser (CSS Canvas colour).
	// The paint is a background-IMAGE layer (transparent-zen.css), so the site's own background-color stays readable
	// here. Checked again once the site's CSS is in (DOMContentLoaded, load): its own background wins.
	private opaqueHooked = false;
	private setOpaque(on: boolean): void {
		this.opaque = on;
		const check = () => {
			const [html, body] = [document.documentElement, document.body].map((el) => el && getComputedStyle(el));
			const bare = !toRgba(html.backgroundColor) && (!body || (!toRgba(body.backgroundColor) && body.backgroundImage === "none"));
			if (this.opaque && bare) mark("tz-opaque");
			else unmark("tz-opaque");
		};
		check();
		setTimeout(check, 400); // after a live switch: the removed style's fade (root transition) has settled
		if (this.opaqueHooked || document.readyState === "complete") return;
		this.opaqueHooked = true;
		document.addEventListener("DOMContentLoaded", check, { once: true });
		window.addEventListener("load", check, { once: true });
	}

	// auto glass (sites without a style): global switch + per-domain black/whitelist, as upstream's dynamic mode
	private autoAllowed(): boolean {
		const s = this.transparentZenSettings;
		if (!s?.enableTransparency) return false;
		const listed = (s.blacklistedDomains ?? []).includes(window.location.hostname);
		return s.enableWhitelist ? listed : !listed;
	}

	private setAuto(on: boolean): void {
		if (on === this.autoOn) return;
		this.autoOn = on;
		if (!on) {
			this.autoGlass.stop();
			removeStyles("styles/shared/auto-glass.css");
			return;
		}
		insertStyles("styles/shared/auto-glass.css");
		const go = () => this.autoOn && this.autoGlass.start();
		if (document.body) go();
		else document.addEventListener("DOMContentLoaded", go, { once: true });
	}

	private initLoadingScreen(): void {
		document.documentElement?.style.setProperty("--zen-logo-path", `url(${browser.runtime.getURL("assets/images/zen_logo.svg")})`);
		document.documentElement?.classList.add("tz-hidden");
	}

	private removeLoadingScreen(): void {
		setTimeout(() => {
			document.documentElement.classList.remove("tz-hidden");
			document.documentElement.style.removeProperty("--zen-logo-path");
		}, 500);
	}

	private async initSiteSpecificSettings(): Promise<void> {
		if (!this.transparentZenSettings) {
			const settings = (await browser.storage.local.get("transparentZenSettings")) as ExtensionSettings;
			this.transparentZenSettings = settings.transparentZenSettings;
		}

		if (this.transparentZenSettings?.siteSpecificSettings.length) {
			for (const setting of this.transparentZenSettings.siteSpecificSettings) {
				if (setting.domain === window.location.hostname) {
					this.siteSpecificSettings = setting;
					if (setting.enabled) {
						this.applyCustomBackgrounds();
						this.applyCustomStyles();
					}
				}
			}
		}
	}

	// glass mode for site styles (styles/shared/glass.css): :root[data-tz-glass=dark|light] + --tz-glass-alpha.
	// "auto" (default) follows prefers-color-scheme, i.e. the desktop light/dark theme, live; a site's registry
	// "glass" (dark-only apps) overrides both. First pass runs synchronously in the constructor.
	private glassTheme: "auto" | "dark" | "light" = "auto";
	private siteGlass?: "dark" | "light"; // per-site override from data/ContentScripts.json
	private static readonly lightScheme = window.matchMedia("(prefers-color-scheme: light)");

	private applyGlass(theme?: "auto" | "dark" | "light", opacity?: number): void {
		if (theme) this.glassTheme = theme;
		const resolve = () => {
			document.documentElement.dataset.tzGlass =
				this.siteGlass ?? (this.glassTheme === "auto" ? (TransparentZen.lightScheme.matches ? "light" : "dark") : this.glassTheme);
		};
		resolve();
		TransparentZen.lightScheme.onchange = resolve;
		if (opacity !== undefined) document.documentElement.style.setProperty("--tz-glass-alpha", String(opacity / 100));
	}

	private initExtensionSettingsStyles(): void {
		mark("tz-initialized");
		if (this.transparentZenSettings?.primaryColor) {
			this.applyCustomProperty("--color-primary", this.transparentZenSettings.primaryColor);
		}
		if (this.transparentZenSettings?.textColor) {
			this.applyCustomProperty("--color-text", this.transparentZenSettings.textColor);
		}
		if (this.transparentZenSettings?.backgroundColor) {
			this.applyCustomProperty("--transparent-background", this.transparentZenSettings.backgroundColor);
		}
		if (this.transparentZenSettings?.backgroundImage) {
			this.blobToDataURL(this.transparentZenSettings.backgroundImage).then((dataUrl) => {
				this.applyCustomProperty("--custom-background-image", `url(${dataUrl})`);
				document.documentElement?.classList.add("tz-custom-background");
			});
			if (this.transparentZenSettings.backgroundImageOpacity) {
				const opacity = this.transparentZenSettings.backgroundImageOpacity / 100;
				this.applyCustomProperty("--custom-background-image-opacity", opacity.toString());
			}
			if (this.transparentZenSettings.backgroundImageBlur) {
				this.applyCustomProperty("--custom-background-image-blur", `blur(${this.transparentZenSettings.backgroundImageBlur}px)`);
			}
			if (this.transparentZenSettings.backgroundImageBrightness) {
				const brightness = this.transparentZenSettings.backgroundImageBrightness / 100;
				this.applyCustomProperty("--custom-background-image-brightness", `brightness(${brightness})`);
			}
		}
	}

	private blobToDataURL(blob: Blob): Promise<string> {
		return new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onloadend = () => {
				resolve(reader.result as string);
			};
			reader.onerror = (error) => {
				reject(error);
			};
			reader.readAsDataURL(blob);
		});
	}

	private applyCustomProperty(property: string, color: string): void {
		document.body.style.setProperty(property, color);
	}
}

new TransparentZen();
