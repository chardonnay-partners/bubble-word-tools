import csv
import json
from urllib.error import URLError

import pytest

from wcg.core.sheet import (LOCALE_LABELS, SheetPushError, append_rows,
                            build_rows, push_rows, update_csv_rows, word_key)
from tests.conftest import make_category

LOCALES = ["en", "tr", "es"]


def sheet_category():
    category = make_category(cid="world-cities", status="approved",
                             words=("London", "New York", "Rio, de Janeiro", "Tokyo"),
                             names={"en": "World Cities", "tr": "Dünya Şehirleri"})
    translations = {"London": "Londra", "New York": "New York",
                    "Rio, de Janeiro": "Rio", "Tokyo": "Tokyo"}
    for item in category.items:
        item.word["tr"] = translations[item.word["en"]]
    return category


def test_word_key():
    assert word_key("Sci-Fi") == "sci-fi"
    assert word_key("New York") == "new-york"
    assert word_key("Édouard!") == "douard"
    assert word_key("  ") == "item"


def test_new_file_gets_header_then_category_and_item_rows(tmp_path):
    path = tmp_path / "localization.csv"
    count = append_rows(sheet_category(), path, LOCALES)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert count == 5
    assert rows[0] == ["Key", "English(en)", "Turkish(tr)", "Spanish(es)"]
    assert rows[1] == ["world-cities", "World Cities", "Dünya Şehirleri", ""]
    assert rows[2] == ["world-cities.london", "London", "Londra", ""]
    assert rows[3] == ["world-cities.new-york", "New York", "New York", ""]
    assert rows[4] == ["world-cities.rio-de-janeiro", "Rio, de Janeiro", "Rio", ""]
    assert rows[5] == ["world-cities.tokyo", "Tokyo", "Tokyo", ""]


def test_append_does_not_repeat_header(tmp_path):
    path = tmp_path / "localization.csv"
    append_rows(sheet_category(), path, LOCALES)
    append_rows(make_category(cid="birds"), path, LOCALES)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert len(rows) == 11
    assert rows[6] == ["birds", "Birds", "", ""]
    assert rows[7] == ["birds.pigeon", "Pigeon", "", ""]


def test_ref_items_are_skipped(tmp_path):
    path = tmp_path / "localization.csv"
    category = make_category(cid="mixed", refs=("owls",))
    count = append_rows(category, path, LOCALES)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert count == 5
    assert all("owls" not in row[0] for row in rows)


def test_all_configured_labels_exist():
    for locale in ["en", "tr", "fr", "de", "ja", "ko", "pt", "es", "ru"]:
        assert locale in LOCALE_LABELS


def test_append_raises_on_header_mismatch(tmp_path):
    path = tmp_path / "localization.csv"
    append_rows(sheet_category(), path, LOCALES)
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        append_rows(make_category(cid="birds"), path, ["en", "tr"])
    after = path.read_text(encoding="utf-8")
    assert after == before


def test_build_rows_matches_csv_layout():
    rows = build_rows(sheet_category(), LOCALES)
    assert rows == [
        ["world-cities", "World Cities", "Dünya Şehirleri", ""],
        ["world-cities.london", "London", "Londra", ""],
        ["world-cities.new-york", "New York", "New York", ""],
        ["world-cities.rio-de-janeiro", "Rio, de Janeiro", "Rio", ""],
        ["world-cities.tokyo", "Tokyo", "Tokyo", ""],
    ]


def test_build_rows_skips_ref_items():
    rows = build_rows(make_category(cid="mixed", refs=("owls",)), LOCALES)
    assert len(rows) == 5
    assert all("owls" not in row[0] for row in rows)


def test_update_csv_rows_replaces_in_place_and_appends_unknown(tmp_path):
    path = tmp_path / "localization.csv"
    append_rows(make_category(cid="birds"), path, LOCALES)
    append_rows(make_category(cid="cats",
                              words=("Siamese", "Persian", "Tabby", "Sphynx")),
                path, LOCALES)
    update_csv_rows(path, [["birds", "Birds", "Kuşlar", "Aves"],
                           ["birds.pigeon", "Pigeon", "Güvercin", ""],
                           ["dogs", "Dogs", "", ""]], LOCALES)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[1] == ["birds", "Birds", "Kuşlar", "Aves"]
    assert rows[2] == ["birds.pigeon", "Pigeon", "Güvercin", ""]
    assert rows[3] == ["birds.crow", "Crow", "", ""]
    assert rows[6] == ["cats", "Cats", "", ""]
    assert rows[-1] == ["dogs", "Dogs", "", ""]


def test_update_csv_rows_creates_missing_file(tmp_path):
    path = tmp_path / "localization.csv"
    update_csv_rows(path, [["birds", "Birds", "Kuşlar", ""]], LOCALES)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == ["Key", "English(en)", "Turkish(tr)", "Spanish(es)"]
    assert rows[1] == ["birds", "Birds", "Kuşlar", ""]


def test_update_csv_rows_raises_on_header_mismatch(tmp_path):
    path = tmp_path / "localization.csv"
    append_rows(sheet_category(), path, LOCALES)
    with pytest.raises(ValueError):
        update_csv_rows(path, [["birds", "Birds", ""]], ["en", "tr"])


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_push_rows_posts_json_and_returns_reply(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse('{"inserted": 2, "skipped": 0}')

    monkeypatch.setattr("wcg.core.sheet.urlopen", fake_urlopen)
    result = push_rows([["a", "x"], ["b", "y"]], "https://example.test/exec", "tok")
    assert result == {"inserted": 2, "skipped": 0}
    assert seen["url"] == "https://example.test/exec"
    assert seen["timeout"] == 20
    assert seen["body"] == {"token": "tok", "rows": [["a", "x"], ["b", "y"]]}


def test_push_rows_includes_action_when_given(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse('{"updated": 1, "missing": 0}')

    monkeypatch.setattr("wcg.core.sheet.urlopen", fake_urlopen)
    result = push_rows([["a", "x"]], "https://example.test/exec", "tok",
                       action="updateRows")
    assert result == {"updated": 1, "missing": 0}
    assert seen["body"] == {"token": "tok", "rows": [["a", "x"]],
                            "action": "updateRows"}


def test_push_rows_raises_on_network_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise URLError("no route to host")

    monkeypatch.setattr("wcg.core.sheet.urlopen", fake_urlopen)
    with pytest.raises(SheetPushError):
        push_rows([["a", "x"]], "https://example.test/exec", "tok")


def test_push_rows_raises_on_error_reply(monkeypatch):
    monkeypatch.setattr("wcg.core.sheet.urlopen",
                        lambda req, timeout=None: FakeResponse('{"error": "invalid token"}'))
    with pytest.raises(SheetPushError, match="invalid token"):
        push_rows([["a", "x"]], "https://example.test/exec", "tok")


def test_push_rows_raises_on_non_json_reply(monkeypatch):
    monkeypatch.setattr("wcg.core.sheet.urlopen",
                        lambda req, timeout=None: FakeResponse("<html>login</html>"))
    with pytest.raises(SheetPushError):
        push_rows([["a", "x"]], "https://example.test/exec", "tok")
