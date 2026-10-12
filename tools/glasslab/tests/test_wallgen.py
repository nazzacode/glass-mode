"""procedural wallpapers we own (public shots can't use the user's copyrighted ones)"""
import numpy as np
import pytest

from tools.glasslab import wallgen

SIZE = (640, 400)


def arr(img):
    return np.asarray(img, dtype=float)


@pytest.mark.parametrize("name", list(wallgen.PRESETS))
def test_size_and_deterministic(name):
    a, b = wallgen.make(name, SIZE, seed=3), wallgen.make(name, SIZE, seed=3)
    assert a.size == SIZE and a.mode == "RGB"
    assert np.array_equal(arr(a), arr(b))


@pytest.mark.parametrize("name", list(wallgen.PRESETS))
def test_not_flat_and_has_crisp_structure(name):
    a = arr(wallgen.make(name, SIZE))
    assert a.std() > 18                                          # colour field, not a flat fill
    grad = np.abs(np.diff(a.mean(2), axis=1))
    assert np.percentile(grad, 99.5) > 2.5                       # some crisp edges survive (blur behind window shows)


def test_seed_changes_output():
    assert not np.array_equal(arr(wallgen.make("aurora", SIZE, seed=1)), arr(wallgen.make("aurora", SIZE, seed=2)))


def test_presets_distinct():
    imgs = {n: arr(wallgen.make(n, SIZE)) for n in wallgen.PRESETS}
    names = list(imgs)
    assert 3 <= len(names) <= 5
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert np.abs(imgs[a] - imgs[b]).mean() > 15, (a, b)


def test_light_preset_brighter_than_dark():
    light, dark = wallgen.for_mode("light"), wallgen.for_mode("dark")
    assert light in wallgen.PRESETS and dark in wallgen.PRESETS
    assert arr(wallgen.make(light, SIZE)).mean() > arr(wallgen.make(dark, SIZE)).mean() + 40
