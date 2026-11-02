"""A vs B maths: pairing order, blind sides, ranking. Pure, no browser."""
import random

from tools.glasslab import vote


def pair(cap, q="t", a="x", b="y"):
    return {"q": q, "capture": cap, "mode": "dark", "wall": "mid", "left": a, "right": b}


def test_every_page_is_asked_before_any_is_asked_twice():
    pairs, votes = [pair("a"), pair("b")], []
    for _ in range(2):
        p = vote.next_pair(pairs, votes, random.Random(1))
        votes.append({**p, "pick": "same"})
    assert {v["capture"] for v in votes} == {"a", "b"}


def test_a_swapped_pair_counts_as_the_same_pair():
    assert vote.pair_key(pair("a", a="x", b="y")) == vote.pair_key(pair("a", a="y", b="x"))


def test_questions_run_in_order():
    pairs = [pair("a", q="first"), pair("b", q="second")]
    assert vote.next_pair(pairs, [], random.Random(3))["q"] == "first"


def test_sides_get_shuffled_so_votes_stay_blind():
    sides = {vote.next_pair([pair("a")], [], random.Random(i))["left"] for i in range(20)}
    assert sides == {"x", "y"}


def test_no_pairs_gives_none():
    assert vote.next_pair([], []) is None


def test_lower_bound_prefers_evidence():
    assert vote.wilson(40, 50) > vote.wilson(3, 3) > vote.wilson(0, 3) == 0


def test_standings_rank_and_count_each_outcome():
    votes = [{**pair("a"), "pick": "x"}, {**pair("b"), "pick": "x"}, {**pair("c"), "pick": "same"}, {**pair("d"), "pick": "bad"}]
    rows = vote.standings(votes)["t"]["all"]
    assert rows[0]["variant"] == "x" and (rows[0]["wins"], rows[0]["losses"], rows[0]["same"], rows[0]["bad"]) == (2, 0, 1, 1)
    assert (rows[1]["wins"], rows[1]["losses"]) == (0, 2)


def test_eligible_splits_pages_from_panels_and_drops_broken_freezes():
    base = {"host": "x.org", "source": "seed"}
    metas = [{**base, "id": "page"}, {**base, "id": "menu", "state": "Menu"}, {**base, "id": "broken", "drift": 0.5},
             {"host": "y.org", "source": "recorder", "id": "mine"}]
    assert {m["id"] for m in vote.eligible(metas, "pages")} == {"page", "mine"}
    assert {m["id"] for m in vote.eligible(metas, "panels")} == {"menu", "mine"}


def test_eligible_puts_real_use_first_and_caps_each_host():
    metas = [{"host": "x.org", "source": "seed", "id": f"s{i}"} for i in range(9)] + [{"host": "x.org", "source": "recorder", "id": "mine"}]
    got = vote.eligible(metas, "pages", max_per_host=2)
    assert got[0]["id"] == "mine" and len(got) == 2
