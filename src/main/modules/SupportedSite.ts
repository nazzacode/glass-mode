export class SupportedSite {
	private removeLoadingScreen: () => void;
	private initExtensionSettingsStyles: () => void;

	constructor(removeLoadingScreen: () => void, initExtensionSettingsStyles: () => void) {
		this.removeLoadingScreen = removeLoadingScreen;
		this.initExtensionSettingsStyles = initExtensionSettingsStyles;
	}

	// the site style itself is inserted/removed by TransparentZen.refresh() (off switches, per-site list)
	public async initSupportedWebsite(): Promise<void> {
		if (document.readyState === "complete") {
			this.initExtensionSettingsStyles();
			this.removeLoadingScreen();
		} else if (document.readyState === "interactive") {
			document.addEventListener("readystatechange", () => {
				if (document.readyState === "complete") {
					this.initExtensionSettingsStyles();
					this.removeLoadingScreen();
				}
			});
		} else {
			document.addEventListener("DOMContentLoaded", () => {
				this.initExtensionSettingsStyles();
				this.removeLoadingScreen();
			});
		}
	}
}
