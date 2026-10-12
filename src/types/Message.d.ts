import type { ExtensionSettings } from "./ExtensionSettings";

export type Message = {
	action:
		| "updateSettings"
		| "toggleTransparency"
		| "toggleWhitelist"
		| "toggleLightweight"
		| "getDomain"
		| "changePrimaryColor"
		| "changeTextColor"
		| "changeBackgroundColor"
		| "changeBackgroundImage"
		| "changeBackgroundImageOpacity"
		| "changeBackgroundImageBlur"
		| "changeBackgroundImageBrightness"
		| "changeCustomStyles"
		| "toggleSiteSpecificSettings"
		| "toggleInspector"
		| "addCustomBackground"
		| "changeGlassTheme"
		| "changeGlassOpacity"
		| "glassCommand"
		| "glassSet"
		| "insertStyles"
		| "removeStyles";
	data?: unknown;
	enabled?: boolean;
	value?: string | number | boolean | Blob | object;
	filePath?: string;
	domains?: Array<string>;
	settings?: ExtensionSettings["transparentZenSettings"];
};
