"""glasslab add: one command from URL to a verified site style.

Deterministic core: discover (causal tokens) → scaffold style + registry + test screen → build → test + explore → report.
Optional agent loop (--agent): an LLM edits ONLY the site's CSS from a fixed prompt (rules + current CSS + report); every
round is re-verified by the suite and kept only if the score improves — otherwise reverted. Monotone by construction, so
the agent can be anything (`GLASSLAB_AGENT`, default Claude Code; e.g. `codex exec`).
Sandbox: the agent works in a temp copy holding only the docs, the shared tokens and its CSS (no .git, no build files, no
credentials); only that CSS comes back, and only if it passes `lint_css` (no url()/imports/attr() — a site style may only
map onto var(--g-…)). Its prompt carries selectors and numbers, never page text (logged-in pages, prompt injection)."""
import json, os, re, shlex, shutil, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urlsplit

from . import cli, discover, suite

ROOT = Path(__file__).resolve().parents[2]
OUT = Path.home() / ".cache/glasslab/add"
DEFAULT = f".{int(suite.DEFAULT_ALPHA * 100)}"
SANDBOX = ("docs/GLASS.md", "styles/shared")     # what the agent may read besides its CSS
UNSAFE = re.compile(r"url\(|image-set\(|attr\(|expression\(|javascript:|-moz-binding|behavior\s*:", re.I)
SHARED_IMPORT = re.compile(r'^@import url\("\.\./shared/[\w.-]+\.css"\);\s*$')

RULES = """You are improving ONE liquid-glass site style for the Transparent Zen extension. Edit only {css}.
Rules (docs/GLASS.md):
- Map the site's own tokens/regions onto the shared glass tiers — never invent alphas or colours. Use only var(--g-…):
  surfaces var(--g-frame) / var(--g-content) / var(--g-content-abs) / var(--g-popover) (+ backdrop-filter: var(--g-blur)) /
  var(--g-fill) / var(--g-fill-hover) / var(--g-fill-selected) / var(--g-paper) / transparent;
  text var(--g-fg) / var(--g-fg-2) / var(--g-fg-3), status var(--g-red|orange|green|blue|purple), lines var(--g-line).
- Page/app background → transparent (glass.css tints body). Menus, dialogs, dropdowns, suggestion lists → var(--g-popover).
- Prefer the site's CSS custom properties (tokens) over selectors; selectors: ARIA role → id → data-testid → stable classes;
  never hashed classes. If you restyle a control's fill, also set its label colour.
- Failing rows below come from a headless test of every screen + every menu/dialog the explorer opened: `surface_foreign`
  = surfaces that are not glass tiers (map them), failing text = selector with its APCA contrast vs target (fix its colour
  or its background tier). Fix the largest failures first. Keep the file small and commented like the existing ones.
"""


def default_rows(rows):
    return [r for r in rows if r["key"].endswith(DEFAULT)]


def progress(rows):
    """comparable score at the default slider: rows passing first, then summed metrics (contrast at worst bound)"""
    rs = default_rows(rows)
    return (sum(r["ok"] for r in rs), round(sum(min(r["contrast"]) + r["surface"] + r["text"] for r in rs), 4))


def green(rows):
    return all(r["ok"] for r in default_rows(rows))


def report_md(rows, page_text=True):
    """what to fix, worst first: per failing row its foreign surfaces + failing text (page text only for humans)"""
    out = [f"{sum(r['ok'] for r in default_rows(rows))}/{len(default_rows(rows))} rows pass at the default slider.\n"]
    for r in sorted((r for r in default_rows(rows) if not r["ok"]), key=lambda r: min(r["contrast"]) + r["surface"]):
        where = f"{r['key']}" + (f" (opened: {r['state']})" if r.get("state") else "")
        out.append(f"## {where}\ncontrast {min(r['contrast']):.0%} · surface {r['surface']:.0%} · text {r['text']:.0%}"
                   + (f" · opacity {r['opacity']:.2f}{' over page content' if r.get('over_content') else ''}" if "opacity" in r else ""))
        out += [f"- foreign surface `{f}` ×{n}" for f, n in r.get("surface_foreign", [])]
        out += [f"- foreign text colour `{f}` ×{n}" for f, n in r.get("text_foreign", [])]
        out += [f"- text `{g['sel']}`" + (f" “{g['t']}”" if page_text else "") + f" Lc {min(g['lc'])} < {g['target']} (fg {g['fg']})"
                for g in r.get("failing", [])]
        out.append("")
    return "\n".join(out)


def prompt(css, css_text, report):
    return f"{RULES.format(css=css)}\n# Current {css}\n```css\n{css_text}\n```\n\n# Test report\n{report}\n"


def improve(lab, agent, read, write, rounds=4, css="site.css"):
    """verifier-gated loop → (final rows, log). lab() → rows; agent(prompt) edits via write(); read() → css text"""
    rows, log = lab(), []
    for i in range(rounds):
        if green(rows):
            break
        before = read()
        agent(prompt(css, before, report_md(rows, page_text=False)))
        new = lab()
        kept = progress(new) > progress(rows)
        log.append({"round": i + 1, "before": progress(rows), "after": progress(new), "kept": kept})
        print(f"agent round {i + 1}: {progress(rows)} → {progress(new)} {'kept' if kept else 'reverted'}", flush=True)
        if kept:
            rows = new
        else:
            write(before)
    return rows, log


def lint_css(text):
    """problems that make agent CSS unsafe to ship: anything that loads or leaks (url(), imports other than the shared
    tokens, attr() content, legacy script hooks)"""
    probs = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("@import") and not SHARED_IMPORT.match(line.strip()):
            probs.append(f"{i}: only @import url(\"../shared/….css\") allowed")
        elif not SHARED_IMPORT.match(line.strip()) and UNSAFE.search(line):
            probs.append(f"{i}: {UNSAFE.search(line).group(0)} not allowed")
    return probs


def sandboxed(agent, root, css):
    """agent(prompt, cwd) runs in a temp copy (docs + shared tokens + its CSS); only lint-clean CSS is copied back"""
    rel = css.relative_to(root)

    def run(text):
        with tempfile.TemporaryDirectory(prefix="glasslab-agent-") as tmp:
            tmp = Path(tmp)
            for item in SANDBOX:
                src = root / item
                if src.is_dir():
                    shutil.copytree(src, tmp / item)
                elif src.exists():
                    (tmp / item).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(src, tmp / item)
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(css, tmp / rel)
            agent(text, tmp)
            new = (tmp / rel).read_bytes().decode()
        if probs := lint_css(new):
            print("agent CSS rejected:", *probs, sep="\n  ")
        else:
            css.write_bytes(new.encode())
    return run


def cli_agent():
    """GLASSLAB_AGENT (default Claude Code: read + edit only, no shell) with the prompt as last argument, in cwd"""
    cmd = shlex.split(os.environ.get("GLASSLAB_AGENT", "claude -p --permission-mode acceptEdits --allowedTools Read,Edit "
                                                       "--disallowedTools Bash,WebFetch,WebSearch"))
    return lambda text, cwd: subprocess.run([*cmd, text], cwd=cwd, check=False, timeout=900)


def add(name, url, act=None, content_first=False, dark_only=False, agent=False, rounds=4, force=False):
    host = urlsplit(url).hostname.removeprefix("www.")
    css = ROOT / "styles/websites" / f"{host}.css"
    sid = discover.slug(name)
    out = OUT / sid
    out.mkdir(parents=True, exist_ok=True)
    if force or not css.exists():
        discover.new_site(cli.xpi(True), name, url, act, content_first, dark_only, force=True)

    def lab():
        rows = suite.run(cli.xpi(True), f"^{sid}-", out / time.strftime("%H%M%S"))
        (out / "report.md").write_text(report_md(rows))
        (out / "report-public.md").write_text(report_md(rows, page_text=False))   # PR bodies: no page text
        return rows

    read = lambda: css.read_bytes().decode()
    write = lambda t: css.write_bytes(t.encode())
    rows, log = improve(lab, sandboxed(cli_agent(), ROOT, css), read, write, rounds, css.name) if agent else (lab(), [])
    (out / "log.json").write_text(json.dumps(log, indent=1))
    print(f"\n{'GREEN' if green(rows) else 'NOT GREEN'}: {progress(rows)[0]}/{len(default_rows(rows))} rows pass"
          f"\nreport: {out / 'report.md'}\nstyle: {css.relative_to(ROOT)}"
          + ("\nnext: ./glasslab test --save-baseline " + sid + " → commit → open a pull request" if green(rows)
             else "\nnext: edit the style (or rerun with --agent), ./glasslab test " + sid))
    return 0 if green(rows) else 1
