"""explored-state keys: unique (no slug collisions), and free of page text on private screens (they end up in the
committed baseline and in public tile names)"""
from tools.glasslab import explore


def t(label, sel="#a", role="button"):
    return {"label": label, "sel": sel, "role": role, "id": ""}


def test_public_keys_readable_and_unique():
    a, b = explore.state_key("app", t("Menu", "#a"), False), explore.state_key("app", t("Menu", "#b"), False)
    assert a.startswith("app~menu-") and a != b


def test_non_ascii_labels_dont_collide():
    assert explore.state_key("app", t("Löschen"), False) != explore.state_key("app", t("Отправить"), False)


def test_private_keys_carry_no_label():
    k = explore.state_key("gmail", t("Anna's birthday party", "#x"), True)
    assert k.startswith("gmail~") and "anna" not in k.lower() and "birthday" not in k.lower()
