"""crawl: URL shapes (one page per shape) — pure, no browser"""
from tools.glasslab import crawl


def test_ids_and_title_slugs_collapse():
    assert crawl.shape("https://linear.app/w/issue/GEN-12/fix-it") == crawl.shape("https://linear.app/w/issue/GEN-9/other-thing")
    assert crawl.shape("https://linear.app/w/view/all-issues-f3aeb9154661") == "linear.app/w/view/:id"
    assert crawl.shape("https://x.com/a/123?cursor=9") == "x.com/a/:id"


def test_tabs_after_ids_stay_distinct():
    assert crawl.shape("https://linear.app/w/project/p-2b1f0a9c7e3d/overview") != crawl.shape("https://linear.app/w/project/p-2b1f0a9c7e3d/issues")


def test_page_ids_are_filename_safe():
    assert crawl.page_id("linear", "https://linear.app/w/issue/GEN-12/fix-it") == "linear@w-issue-id"
    assert crawl.page_id("site", "https://example.com/") == "site@home"
