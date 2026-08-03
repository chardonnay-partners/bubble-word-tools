import csv

import pytest

from wcg.commands.review import ReviewImportError, export_drafts, import_decisions
from wcg.core.store import CategoryStore
from tests.conftest import make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def read_rows(csv_path):
    with open(csv_path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(csv_path, rows):
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["id", "theme", "name", "difficulty", "words", "decision"])
        writer.writeheader()
        writer.writerows(rows)


def seeded(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    store.save(make_category(cid="birds", status="draft"))
    store.save(make_category(cid="cats", status="draft",
                             words=("Siamese", "Persian", "Tabby", "Sphynx")))
    store.save(make_category(cid="done", status="approved"))
    return store


def test_export_writes_only_drafts(tmp_path):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    assert export_drafts(store, csv_path) == 2
    rows = read_rows(csv_path)
    assert [r["id"] for r in rows] == ["birds", "cats"]
    assert rows[0]["words"] == "Pigeon|Crow|Eagle|Owl"
    assert rows[0]["decision"] == ""


def test_export_serializes_refs(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    store.save(make_category(cid="birds"))
    store.save(make_category(cid="animals", words=("Horse", "Snake", "Frog"),
                             refs=("birds",)))
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    rows = {r["id"]: r for r in read_rows(csv_path)}
    assert rows["animals"]["words"] == "Horse|Snake|Frog|ref:birds"


def test_import_applies_decisions_and_edits(tmp_path):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    rows = read_rows(csv_path)
    rows[0]["decision"] = "approve"
    rows[0]["words"] = "Pigeon|Crow|Eagle|Falcon"
    rows[0]["difficulty"] = "2"
    rows[1]["decision"] = "reject"
    write_rows(csv_path, rows)
    result = import_decisions(store, csv_path, SETTINGS)
    assert result == {"approved": 1, "rejected": 1, "skipped": 0}
    pool = store.load_all()
    assert pool["birds"].status == "approved"
    assert pool["birds"].difficulty == 2
    assert pool["birds"].words_for("en") == ["Pigeon", "Crow", "Eagle", "Falcon"]
    assert pool["cats"].status == "rejected"


def test_import_empty_decision_skips(tmp_path):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    result = import_decisions(store, csv_path, SETTINGS)
    assert result == {"approved": 0, "rejected": 0, "skipped": 2}
    assert store.load_all()["birds"].status == "draft"


def test_import_duplicate_id_rows_abort(tmp_path):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    rows = read_rows(csv_path)
    dup = dict(rows[0])
    dup["decision"] = "approve"
    rows[0]["decision"] = "reject"
    rows.append(dup)
    write_rows(csv_path, rows)
    with pytest.raises(ReviewImportError, match="duplicate row"):
        import_decisions(store, csv_path, SETTINGS)
    pool = store.load_all()
    assert pool["birds"].status == "draft"
    assert pool["cats"].status == "draft"


@pytest.mark.parametrize("mutate,match", [
    (lambda r: r.update(id="ghost"), "unknown id"),
    (lambda r: r.update(id="done"), "not a draft"),
    (lambda r: r.update(decision="maybe"), "invalid decision"),
    (lambda r: r.update(decision="approve", words="A|B"), "expected 4-5"),
    (lambda r: r.update(decision="approve", words="A|a|B|C"), "duplicate"),
    (lambda r: r.update(decision="approve", words="A|B|C|ref:ghost"), "unknown ref"),
    (lambda r: r.update(decision="approve", difficulty="9"), "difficulty"),
])
def test_import_invalid_row_aborts_everything(tmp_path, mutate, match):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    rows = read_rows(csv_path)
    rows[1]["decision"] = "approve"
    mutate(rows[0])
    write_rows(csv_path, rows)
    with pytest.raises(ReviewImportError, match=match):
        import_decisions(store, csv_path, SETTINGS)
    pool = store.load_all()
    assert pool["cats"].status == "draft"
