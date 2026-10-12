"""suite bookkeeping (no browser): explored states become result rows; summary, baseline, regressions."""
from tools.glasslab import suite


def m(**kw):
    base = {"contrast": [1.0, 1.0], "surface": 1.0, "text": 1.0, "exempt_img_share": 0, "failing": [], "texts": 3, "opacity": 0.9, "ok": True}
    return {**base, **kw}


STATES = [{"key": "app~file-menu", "trigger": {"label": "File menu"}, "layers": [{"sel": "#m"}],
           "modes": {"dark": m(ok=False, surface=0.2), "light": m()}, "ok": False}]


def test_state_rows_flatten_modes():
    rows = suite.state_rows(STATES, "app", 0.45)
    assert [r["key"] for r in rows] == ["app~file-menu.dark.45", "app~file-menu.light.45"]
    assert rows[0]["screen"] == "app" and rows[0]["state"] == "File menu" and rows[0]["ok"] is False


def test_summary_lists_states_and_screens():
    rows = [m(key="app.dark.45", screen="app", mode="dark", alpha=0.45, glass=0.8)] + suite.state_rows(STATES, "app", 0.45)
    md = suite.summary_md(rows)
    assert "app~file-menu" in md and "File menu" in md
    assert md.count("✗") == 1


def test_failures_include_states_at_default_alpha():
    rows = suite.state_rows(STATES, "app", 0.45)
    assert suite.failures(rows) == ["app~file-menu.dark.45"]


def test_baseline_and_compare_cover_states():
    rows = suite.state_rows(STATES, "app", 0.45)
    bl = suite.baseline_numbers(rows)
    assert "app~file-menu.light.45" in bl and "page" not in str(bl)
    worse = [dict(r, surface=0.5) for r in rows]
    assert any("app~file-menu.light.45 surface" in x for x in suite.compare(worse, bl))


def test_compare_flags_rows_that_vanished():
    """a broken explorer/probe that silently yields fewer rows must not read as 'no regressions'"""
    rows = suite.state_rows(STATES, "app", 0.45)
    bl = suite.baseline_numbers(rows)
    assert any("app~file-menu.light.45 missing" in x for x in suite.compare(rows[:1], bl))
    assert suite.compare(rows, {**bl, "other.dark.45": bl["app~file-menu.dark.45"]}) == []   # screens not run: ignored


def test_merge_runs_into_baseline():
    """parallel runs (one per lab port) merge into one baseline: numbers only, newest wins, other keys kept"""
    rows = suite.state_rows(STATES, "app", 0.45)
    merged = suite.merge_baseline({"old.dark.45": {"contrast": 1, "surface": 1, "text": 1, "ok": True}}, [rows[:1], rows[1:]])
    assert set(merged) == {"old.dark.45", "app~file-menu.dark.45", "app~file-menu.light.45"}
    assert list(merged) == sorted(merged)


def test_compare_without_exploring_ignores_state_rows():
    rows = suite.state_rows(STATES, "app", 0.45)
    screen_row = [dict(rows[0], key="app.dark.45")]
    bl = suite.baseline_numbers(rows + screen_row)
    assert suite.compare(screen_row, bl, explored=False) == []
