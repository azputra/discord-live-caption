import pytest

from app.translate.rules import desired_target
from app.utils.lang import normalize_lang


@pytest.mark.parametrize(
    ("mode", "detected", "fixed", "expected"),
    [
        ("swap", "id", "en", "en"),
        ("swap", "en", "en", "id"),
        ("swap", "indonesian", "id", "en"),
        ("swap", "english", "id", "id"),
        ("swap", "ja", "en", None),
        ("swap", "auto", "en", None),
        ("swap", "", "en", None),
        ("fixed", "id", "en", "en"),
        ("fixed", "en", "id", "id"),
        ("fixed", "id", "id", None),
        ("fixed", "en", "en", None),
        ("fixed", "en", "english", None),
        ("fixed", "id", "indonesian", None),
        ("fixed", "fr", "en", None),
        ("fixed", "en", "fr", None),
        ("other", "id", "en", None),
    ],
)
def test_desired_target(mode, detected, fixed, expected):
    assert desired_target(mode, detected, fixed) == expected


@pytest.mark.parametrize("detected", ["id", "en", "ja", "fr", "auto", "", None])
@pytest.mark.parametrize("mode", ["swap", "fixed"])
@pytest.mark.parametrize("fixed", ["id", "en", None])
def test_never_translates_into_the_same_language(mode, detected, fixed):
    target = desired_target(mode, detected, fixed)
    if target is None:
        return
    assert target != normalize_lang(detected)
    assert target in {"id", "en"}
