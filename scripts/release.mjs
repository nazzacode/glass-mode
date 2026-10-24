// npm run release [patch|minor|major|hotfix] ["notes"] — bump → build → sign (AMO unlisted) → GitHub release → updates.json.
// Installed copies poll gecko.update_url (site/updates.json on gh-pages) daily and update themselves: no clicks, no restart.
import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFileSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const REPO = "nazzacode/glass-mode";
const [bump = "patch", notes = ""] = process.argv.slice(2);
const sh = (cmd, opts = {}) => execSync(cmd, { stdio: "inherit", ...opts });
const read = (f) => JSON.parse(readFileSync(f, "utf8"));

if (execSync("git status --porcelain --untracked-files=no").toString().trim()) {
	console.error("release: commit or stash first (tracked changes in the tree)");
	process.exit(1);
}

sh(`npm run build:${bump}`);
const manifest = read("manifest.json");
const { version } = manifest;
const id = manifest.browser_specific_settings.gecko.id;
sh("npm run sign");
const xpi = join(
	"builds",
	readdirSync("builds").find((f) => f.endsWith(`-${version}.xpi`)),
);

sh(`git commit -qm "${version}" -- manifest.json package.json && git push -q origin release`);
const asset = join(mkdtempSync(join(tmpdir(), "glass-release-")), "glass-mode.xpi");
copyFileSync(xpi, asset);
sh(`gh release create v${version} --latest --title v${version} --notes ${JSON.stringify(notes || `v${version}`)} ${asset}`);

// updates.json: newest first; Firefox takes the highest version it's compatible with
const entry = {
	version,
	update_link: `https://github.com/${REPO}/releases/download/v${version}/glass-mode.xpi`,
	update_hash: `sha256:${createHash("sha256").update(readFileSync(xpi)).digest("hex")}`,
};
const updatesFile = "site/updates.json";
const old = (() => {
	try {
		return read(updatesFile).addons[id].updates;
	} catch {
		return [];
	}
})();
const updates = { addons: { [id]: { updates: [entry, ...old.filter((u) => u.version !== version)] } } };
writeFileSync(updatesFile, `${JSON.stringify(updates, null, 2)}\n`);
sh(`git add ${updatesFile} && git commit -qm "updates.json: ${version}" && git push -q origin release`);

// publish just updates.json to gh-pages (the rest of the site deploys via ./glasslab site)
const wt = mkdtempSync(join(tmpdir(), "glass-pages-"));
sh(`git fetch -q origin gh-pages && git worktree add -q --detach ${wt} origin/gh-pages`);
try {
	copyFileSync(updatesFile, join(wt, "updates.json"));
	sh(`git add updates.json && git commit -qm "updates.json: ${version}" && git push -q origin HEAD:gh-pages`, { cwd: wt });
} finally {
	sh(`git worktree remove --force ${wt}`);
	rmSync(wt, { recursive: true, force: true });
}
console.log(`released v${version} → installed copies update within a day (about:addons → Check for Updates: now)`);
