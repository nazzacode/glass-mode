"""privacy scrambler (probes/scramble.js) on a Trusted-Types fixture: text/attrs replaced, lengths kept, deterministic,
icons + out-of-scope untouched, images covered, late DOM updates scrambled too."""
import asyncio, json, re

import pytest

from tools.glasslab import lab

SNAP = """JSON.stringify({
  text: Object.fromEntries([...document.querySelectorAll('#mail .row > *, #public > *, #late')].map((e, i) => [e.id || i + ':' + e.className, e.textContent])),
  rows: [...document.querySelectorAll('#mail .row')].map(e => e.textContent),
  from: [...document.querySelectorAll('.from')].map(e => e.textContent),
  icons: [...document.querySelectorAll('.icon')].map(e => e.textContent),
  pub: document.querySelector('#public h1').textContent,
  q: [document.getElementById('q').placeholder, document.getElementById('q').value],
  attrs: ['alt', 'title'].map(a => document.getElementById('avatar').getAttribute(a))
    .concat([document.getElementById('bgav').getAttribute('aria-label'), document.getElementById('btn').getAttribute('aria-label')]),
  img: getComputedStyle(document.getElementById('avatar')).objectPosition,
  imgBg: getComputedStyle(document.getElementById('avatar')).backgroundColor,
  bg: getComputedStyle(document.getElementById('bgav')).backgroundImage,
  late: document.getElementById('late')?.textContent,
  frame: getComputedStyle(document.getElementById('frame')).filter,
  lateFrame: getComputedStyle(document.getElementById('lframe') || document.body).filter,
})"""
LATE = ("{const d=document.createElement('div');d.id='late';d.textContent='Margaret Thornbury';document.getElementById('mail').append(d);"
        "const f=document.createElement('iframe');f.id='lframe';document.getElementById('mail').append(f)}")
SECRETS = ["Margaret", "Thornbury", "Kestrel", "Invoice", "Nathan", "Quarterly", "kestrel.io", "4821", "nazzacode", "Sellner", "Regime", "Leaked"]


def test_no_html_sinks():
    """Trusted Types pages (Google) throw on HTML sinks: text nodes, attributes, CSSOM only"""
    src = (lab.PROBES / "scramble.js").read_text()
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment", src)


@pytest.fixture(scope="module")
def runs(fixture_url, tmp_path_factory):
    out = tmp_path_factory.mktemp("scramble")

    async def go():
        async with lab.session(None, out / "browser.log") as pg:
            res = []
            for seed in (7, 7, 8):
                await pg.goto(fixture_url("private.html"), settle=1)
                before = json.loads(await pg.eval(SNAP))
                stats = await pg.probe("scramble", ["#mail"], seed)
                await pg.eval(LATE)
                await asyncio.sleep(0.3)
                res.append({"before": before, "after": json.loads(await pg.eval(SNAP)), "stats": stats})
            return res
    return asyncio.run(go())



@pytest.mark.e2e
def test_secrets_gone(runs):
    after = runs[0]["after"]
    blob = json.dumps({k: after[k] for k in ("rows", "q", "attrs", "late")})
    for s in SECRETS:
        assert s.lower() not in blob.lower(), s
    assert runs[0]["stats"]["texts"] > 0


@pytest.mark.e2e
def test_lengths_and_shape_preserved(runs):
    b, a = runs[0]["before"]["rows"], runs[0]["after"]["rows"]
    for x, y in zip(b, a):
        assert abs(len(x) - len(y)) <= max(2, 0.05 * len(x))
        assert re.sub(r"\w", "", x) == re.sub(r"\w", "", y)   # punctuation/spaces kept
    assert runs[0]["after"]["from"][2].isupper()                 # GITHUB → all caps word
    assert re.search(r"#\d{3} ", runs[0]["after"]["rows"][2])    # digits stay digits


@pytest.mark.e2e
def test_deterministic_and_consistent(runs):
    assert runs[0]["after"] == runs[1]["after"]                  # same seed → same output across page loads
    assert runs[0]["after"]["rows"] != runs[2]["after"]["rows"]  # seed matters
    f = runs[0]["after"]["from"]
    assert f[0] == f[1]                                          # repeated name → same fake name
    assert runs[0]["after"]["late"] == f[0]                      # text added after the scramble is scrambled too


@pytest.mark.e2e
def test_scope_and_icons_untouched(runs):
    b, a = runs[0]["before"], runs[0]["after"]
    assert a["pub"] == b["pub"] == "Public Header Stays"
    assert a["icons"][:2] == b["icons"][:2] == ["inbox", "star"]   # icon-font ligatures stay icons
    assert a["icons"][2] != b["icons"][2]                        # …but sentences in an icon font are still scrambled


@pytest.mark.e2e
def test_images_covered(runs):
    a = runs[0]["after"]
    assert a["bg"] == "none"
    assert a["img"] != runs[0]["before"]["img"] and a["imgBg"] not in ("rgba(0, 0, 0, 0)", "transparent")


@pytest.mark.e2e
def test_iframes_covered_even_late(runs):
    """the scrambler can't reach into iframes (cross-origin: Google's app launcher shows the account photo) → grey box"""
    b, a = runs[0]["before"], runs[0]["after"]
    assert b["frame"] == "none" and "contrast(0)" in a["frame"]
    assert "contrast(0)" in a["lateFrame"] and runs[0]["stats"]["frames"] >= 1


@pytest.mark.e2e
def test_keeps_function_words_and_small_numbers(runs):
    """plausibility: UI/function words and times/days/years stay (no names in the keep list); long numbers change"""
    r1, r3 = runs[0]["after"]["rows"][0], runs[0]["after"]["rows"][2]
    assert " for " in r1 and "12 Oct 2026" in r1 and "09:41" in r1
    assert "312" not in r3 and "Margaret" not in r1
    assert runs[0]["after"]["rows"][4].endswith("S M T W T F S")   # single letters (weekday heads, initials) stay
