<script setup lang="ts">
import { css } from "@codemirror/lang-css";
import { oneDark } from "@codemirror/theme-one-dark";
import { computed, onMounted, ref, toRaw } from "vue";
import { Codemirror } from "vue-codemirror";
import type { Browser } from "webextension-polyfill-ts";
import { DEFAULT_SETTINGS } from "../../shared/Constants";
import { REPO, glassOff, issueUrl, withSiteOff } from "../../shared/Glass";
import { getValidColorOrFallback } from "../../shared/Helper";
import { getActivePageDomain, sendMessageToActiveTabs, sendMessageToAllTabs, sendMessageToDomainTabs } from "../../shared/MessageHelper";
import { getContentScripts, loadSettings, saveSettings } from "../../shared/StorageHelper";
import type { SupportedWebsite } from "../../types/ContentScripts";
import type { ExtensionSettings, SiteSpecificSetting } from "../../types/ExtensionSettings";
import type { Manifest } from "../../types/Manifest";

declare const browser: Browser;
let inputDebounce: number;
let customStylesSavingDebounce: number;

const manifest: Manifest = browser.runtime.getManifest();

const extensionSettings = ref<ExtensionSettings["transparentZenSettings"] | null>(null);
const supportedWebsites = ref<Array<SupportedWebsite>>([]);
const showAllWebsites = ref(false);
const currentDomain = ref<string>();
const currentUrl = ref<string>();
// is the active page covered by a site style? → feedback button reports a bug, else requests the site
const currentSupported = computed(() => {
	const url = currentUrl.value;
	return !!url && supportedWebsites.value.some((w) => w.matches.some((m) => new RegExp(m).test(url)));
});
const host = computed(() => (currentUrl.value?.startsWith("http") ? new URL(currentUrl.value).hostname : undefined));
const siteStyle = computed(() => {
	const url = currentUrl.value;
	return url ? supportedWebsites.value.find((w) => w.matches.some((m) => new RegExp(m).test(url))) : undefined;
});
// the off switches: pages follow storage (content script refresh()), so these only save
const glassOn = computed(() => extensionSettings.value?.glassEnabled !== false);
const siteOn = computed(() => !host.value || !(extensionSettings.value?.offDomains ?? []).includes(host.value));
const setGlass = (on: boolean) => {
	if (!extensionSettings.value) return;
	extensionSettings.value.glassEnabled = on;
	saveSettings(toRaw(extensionSettings.value));
};
const setSite = (on: boolean) => {
	if (!extensionSettings.value || !host.value) return;
	extensionSettings.value.offDomains = withSiteOff(toRaw(extensionSettings.value.offDomains), host.value, !on);
	saveSettings(toRaw(extensionSettings.value));
};
// what this page shows right now — so a control that can't change anything here says why
const status = computed(() => {
	const s = extensionSettings.value;
	if (!s) return "";
	if (s.glassEnabled === false) return "Off everywhere: pages look as in any browser.";
	if (!host.value) return "Glass only works on web pages.";
	if (glassOff(s, host.value)) return "Off on this site: it looks as in any browser.";
	const style = siteStyle.value;
	if (style) return s.disabledWebsites.some((w) => w.name === style.name) ? `${style.name} style is switched off in the list below.` : `Glass: ${style.name} style.`;
	const listed = s.blacklistedDomains.includes(host.value);
	if (s.enableTransparency && (s.enableWhitelist ? listed : !listed)) return "Glass: auto (beta).";
	return "No glass style for this site, so it stays opaque. Try auto glass below, or request it.";
});
const domainDisabled = ref(false);
const siteSpecificSettings = ref<SiteSpecificSetting>({ domain: "", enabled: false, customStyles: "", backgroundSelectors: [] });

const primaryColor = computed(() => {
	const value = getValidColorOrFallback(extensionSettings.value?.primaryColor, DEFAULT_SETTINGS.primaryColor);
	return `--color-primary: ${value};`;
});
const sortedWebsites = computed(() => {
	return supportedWebsites.value?.sort((a, b) => a.name.localeCompare(b.name)) ?? [];
});

// glass changed elsewhere (Alt+Shift keys in another window) → show it, so this popup never saves a stale value back
browser.storage.onChanged.addListener((changes) => {
	const next = changes.transparentZenSettings?.newValue as ExtensionSettings["transparentZenSettings"] | undefined;
	if (!next || !extensionSettings.value) return;
	extensionSettings.value.glassOpacity = next.glassOpacity;
	extensionSettings.value.glassTheme = next.glassTheme;
	extensionSettings.value.glassThemeV2 = next.glassThemeV2;
});

onMounted(() => {
	browser.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
		currentUrl.value = tab?.url;
	});
	loadSettings().then(async (settings) => {
		extensionSettings.value = { ...DEFAULT_SETTINGS, ...settings };
		console.info("Extension settings loaded", settings);
		getContentScripts().then((contentScripts) => {
			supportedWebsites.value = contentScripts?.supportedWebsites || [];
		});
		currentDomain.value = await getActivePageDomain();
		if (currentDomain.value !== undefined && currentDomain.value !== null) {
			if (extensionSettings.value.blacklistedDomains) {
				domainDisabled.value = extensionSettings.value.blacklistedDomains.indexOf(currentDomain.value) >= 0;
			}
			if (extensionSettings.value.siteSpecificSettings) {
				const settings = extensionSettings.value.siteSpecificSettings.find((setting) => setting.domain === currentDomain.value);
				if (settings) {
					siteSpecificSettings.value = settings;
				}
			}
		}
	});
});

const changeSetting = (event: Event) => {
	if (inputDebounce) {
		clearTimeout(inputDebounce);
	}

	inputDebounce = setTimeout(async () => {
		const input = event.target as HTMLInputElement;
		switch (input.name) {
			case "enable-transparency":
				sendMessageToAllTabs({ action: "toggleTransparency", enabled: input.checked });
				break;
			case "enable-whitelist":
				sendMessageToAllTabs({ action: "toggleWhitelist", enabled: input.checked });
				break;
			case "blacklist-domain":
				await toggleDomainBlacklist(input.checked);
				sendMessageToActiveTabs({ action: "toggleTransparency", enabled: extensionSettings.value?.enableWhitelist ? input.checked : !input.checked });
				break;
			case "site-specific-settings":
				await toggleSiteSpecificSettings(input.checked);
				sendMessageToActiveTabs({ action: "toggleSiteSpecificSettings", value: input.checked });
				break;
			case "glass-theme":
				if (extensionSettings.value) {
					extensionSettings.value.glassTheme = input.value as "auto" | "dark" | "light";
					extensionSettings.value.glassThemeV2 = true;
				}
				sendMessageToAllTabs({ action: "changeGlassTheme", value: input.value });
				break;
			case "glass-opacity":
				sendMessageToAllTabs({ action: "changeGlassOpacity", value: Number(input.value) });
				break;
		}

		saveSettings(toRaw(extensionSettings.value));
	}, 500);
};

const toggleDomainBlacklist = async (enabled: boolean) => {
	const domain = await getActivePageDomain();
	if (!domain) return false;

	const indexOfDomain = extensionSettings.value?.blacklistedDomains.indexOf(domain);
	if (indexOfDomain === undefined) return false;

	if (enabled) {
		indexOfDomain === -1 && extensionSettings.value?.blacklistedDomains.push(domain);
	} else {
		extensionSettings.value?.blacklistedDomains.splice(indexOfDomain, 1);
	}
};

const toggleSiteSpecificSettings = async (enabled: boolean) => {
	if (!extensionSettings.value) return false;

	const domain = await getActivePageDomain();
	if (!domain) return false;

	const indexOfDomain = extensionSettings.value.siteSpecificSettings.findIndex((setting) => setting.domain === domain);
	if (indexOfDomain === -1) {
		const newEntry: SiteSpecificSetting = {
			domain,
			enabled,
			customStyles: "",
			backgroundSelectors: [],
		};
		siteSpecificSettings.value = newEntry;
		extensionSettings.value.siteSpecificSettings.push(newEntry);
	} else if (indexOfDomain >= 0) {
		if (siteSpecificSettings.value) siteSpecificSettings.value.enabled = enabled;
		extensionSettings.value.siteSpecificSettings[indexOfDomain].enabled = enabled;
	}

	saveSettings(toRaw(extensionSettings.value));
	sendMessageToDomainTabs(domain, { action: "toggleSiteSpecificSettings", value: enabled });
};

const saveCustomStyles = (value: string) => {
	if (customStylesSavingDebounce) clearTimeout(customStylesSavingDebounce);

	customStylesSavingDebounce = setTimeout(() => {
		const stylesheet = new CSSStyleSheet();
		stylesheet.replace(value).then(() => {
			if (!extensionSettings.value) return;
			const domainIndex = extensionSettings.value.siteSpecificSettings.findIndex((setting) => setting.domain === currentDomain.value);
			if (domainIndex >= 0) {
				extensionSettings.value.siteSpecificSettings[domainIndex].customStyles = value;
				saveSettings(toRaw(extensionSettings.value));
				sendMessageToDomainTabs(currentDomain.value ?? "", { action: "changeCustomStyles", value });
			}
		});
	}, 1000);
};

const toggleSupportedWebsite = (website: SupportedWebsite) => {
	if (!extensionSettings.value) return;

	const toggledWebsiteIndex = extensionSettings.value.disabledWebsites.findIndex((site) => site.name === website.name);
	const isCurrentlyActive = toggledWebsiteIndex === -1;
	const rawWebsite = toRaw(website);
	if (isCurrentlyActive) {
		extensionSettings.value.disabledWebsites.push(rawWebsite);
	} else {
		extensionSettings.value.disabledWebsites.splice(toggledWebsiteIndex, 1);
	}

	saveSettings(toRaw(extensionSettings.value));
};

const enableWebInspector = () => {
	sendMessageToActiveTabs({ action: "toggleInspector", enabled: true });
	window.close();
};

// prefilled GitHub issue form (origin only: paths can carry private ids); the user reviews it before submitting
const openIssue = () => {
	if (!currentUrl.value) return;
	const u = new URL(currentUrl.value);
	const s = extensionSettings.value;
	browser.tabs.create({
		url: issueUrl(currentSupported.value ? "site-bug" : "site-request", { host: u.hostname, url: u.origin, version: manifest.version, theme: s?.glassThemeV2 ? s.glassTheme : "auto", opacity: s?.glassOpacity }),
	});
	window.close();
};

const openSettingsPage = () => {
	browser.runtime.openOptionsPage();
};
</script>

<template>
  <div class="container" :style="primaryColor">
    <header id="extension-header">
      <!-- <img class="logo" src="../assets/images/logo_48.png" alt="Glass Mode Logo"> -->
      <h1 class="headline">{{manifest.name}}</h1>
      <span class="version">{{manifest.version}}</span>
		</header>
    <main id="extension-body" v-if="extensionSettings">
      <section>
				<div id="power">
					<div class="switch">
						<span>Glass</span>
						<button type="button" class="toggle" role="switch" :aria-checked="glassOn" :class="{active: glassOn}" @click="setGlass(!glassOn)"></button>
					</div>
					<div class="switch" v-if="host" :class="{disabled: !glassOn}">
						<span>On {{ host }}</span>
						<button type="button" class="toggle" role="switch" :aria-checked="siteOn" :class="{active: siteOn}" :disabled="!glassOn" @click="setSite(!siteOn)"></button>
					</div>
					<p class="status">{{ status }}</p>
				</div>
				<h2 class="headline">Settings</h2>
				<form id="extension-settings">
					<div class="setting">
						<span class="label">Glass</span>
						<div class="value">
							<select name="glass-theme" :value="extensionSettings.glassThemeV2 ? extensionSettings.glassTheme : 'auto'" @input="changeSetting">
								<option value="auto">Auto (follow desktop)</option>
								<option value="dark">Dark</option>
								<option value="light">Light</option>
							</select>
						</div>
					</div>
					<div class="setting">
						<span class="label">Glass opacity</span>
						<div class="value">
							<input type="range" min="10" max="90" name="glass-opacity" v-model.number="extensionSettings.glassOpacity" @input="changeSetting">
							<span class="range-value">{{ extensionSettings.glassOpacity ?? DEFAULT_SETTINGS.glassOpacity }}%</span>
						</div>
					</div>
					<p class="hint">Any window, incl. web apps: <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>↑</kbd>/<kbd>↓</kbd> opacity, <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> mode</p>
					<div class="button-wrapper" v-if="currentUrl?.startsWith('http')">
						<button type="button" class="feedback" @click="openIssue">{{ currentSupported ? "Report a glass problem on this site" : "Request glass for this site" }}</button>
					</div>
					<label class="setting">
						<input type="checkbox" name="enable-transparency" v-model="extensionSettings.enableTransparency" @input="changeSetting">
						<span class="custom-checkbox"></span>
						Auto glass on sites without a style (beta)
					</label>
					<div class="settings-group" data-depends-on="enable-transparency" v-show="extensionSettings.enableTransparency">
						<label class="setting">
							<input type="checkbox" name="enable-whitelist" v-model="extensionSettings.enableWhitelist" @input="changeSetting">
							<span class="custom-checkbox"></span>
							Only on sites I switch on
						</label>
						<label class="setting">
							<input type="checkbox" name="blacklist-domain" :checked="domainDisabled" @input="changeSetting">
							<span class="custom-checkbox"></span>
							<template v-if="extensionSettings.enableWhitelist">
								Enable for this domain
							</template>
							<template v-else>
								Disable for this domain
							</template>
						</label>
					</div>
					<label class="setting">
						<input type="checkbox" name="site-specific-settings" :checked="siteSpecificSettings.enabled" @input="changeSetting">
						<span class="custom-checkbox"></span>
						Add site specific settings
					</label>
					<div class="settings-group" v-show="siteSpecificSettings.enabled">
						<div class="setting">
							<button @click="enableWebInspector()">
								Hide additional background elements
								<img class="icon" src="../../../assets/icons/html.svg" alt="" role="presentation">
							</button>
						</div>
						<div class="setting">
							<label>Custom Styles</label>
							<Codemirror
								v-model="siteSpecificSettings.customStyles"
								:indentWithTab="true"
								:tabSize="2"
								:extensions="[css(), oneDark]"
								@change="saveCustomStyles"
							/>
						</div>
					</div>
				</form>
				<div class="button-wrapper">
					<button @click="openSettingsPage">
						Show all settings
						<img class="icon" src="../../../assets/icons/arrow-right.svg" alt="" role="presentation">
					</button>
				</div>
			</section>
      <section id="supported-websites">
        <h2 class="headline">Officially Supported Websites:</h2>
        <ul data-content="supported-sites" :class="{open: showAllWebsites}">
          <li v-for="website in sortedWebsites" :key="website.name">
            <span class="website-name">
							<img class="website-favicon" :src="website.favicon" alt="" role="presentation">
							{{ website.name }}
						</span>
            <button type="button" class="toggle" :class="{active: extensionSettings.disabledWebsites.findIndex((site) => site.name === website.name) === -1}" @click="toggleSupportedWebsite(website)"></button>
          </li>
        </ul>
        <div class="button-wrapper" v-if="!showAllWebsites">
          <button class="show-all" type="button" data-target="supported-sites" @click="showAllWebsites = true">Show all</button>
        </div>
      </section>
    </main>
		<footer id="extension-footer">
			<p>Open source. Add a site in one command (<code>./glasslab add</code>) — every style is tested on every screen and menu.</p>
			<a :href="`https://github.com/${REPO}`">GitHub Repository</a>
		</footer>
  </div>
</template>
