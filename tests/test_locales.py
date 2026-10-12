import json
from pathlib import Path


def test_locale_files_have_the_same_keys():
    root = Path(__file__).resolve().parents[1] / "app" / "ui" / "locales"
    english = json.loads((root / "en.json").read_text(encoding="utf-8"))
    indonesian = json.loads((root / "id.json").read_text(encoding="utf-8"))
    assert set(english) == set(indonesian)
    assert english
    assert all(str(value).strip() for value in english.values())
    assert all(str(value).strip() for value in indonesian.values())
