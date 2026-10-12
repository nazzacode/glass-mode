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
