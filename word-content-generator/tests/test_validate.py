from wcg.core.validation import Issue, validate_pool, write_report
from tests.conftest import make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def as_pool(*categories):
    return {c.id: c for c in categories}


def errors(issues):
    return [i for i in issues if i.severity == "error"]


def test_clean_pool_has_no_errors():
    pool = as_pool(make_category())
    assert errors(validate_pool(pool, SETTINGS)) == []


def test_item_count_out_of_range():
    pool = as_pool(make_category(words=("A", "B", "C")))
    assert any("expected 4-5" in i.message for i in errors(validate_pool(pool, SETTINGS)))


def test_missing_ref_target():
    pool = as_pool(make_category(words=("A", "B", "C"), refs=("ghost",)))
    assert any("'ghost' does not exist" in i.message
               for i in errors(validate_pool(pool, SETTINGS)))


def test_cycle_detected():
    a = make_category(cid="animals", words=("A", "B", "C"), refs=("birds",))
    b = make_category(cid="birds", words=("D", "E", "F"), refs=("animals",))
    issues = errors(validate_pool(as_pool(a, b), SETTINGS))
    assert any("cycle" in i.message for i in issues)


def test_intra_category_duplicate_word_is_error():
    pool = as_pool(make_category(words=("Pigeon", "pigeon", "Crow", "Owl")))
    assert any("duplicate word" in i.message for i in errors(validate_pool(pool, SETTINGS)))


def test_cross_category_reuse_is_warning_only():
    a = make_category(cid="birds", words=("Pigeon", "Crow", "Eagle", "Owl"))
    b = make_category(cid="pets", words=("Pigeon", "Dog", "Cat", "Hamster"))
    issues = validate_pool(as_pool(a, b), SETTINGS)
    assert errors(issues) == []
    assert any(i.severity == "warning" and "pigeon" in i.message.lower() for i in issues)


def test_write_report(tmp_path):
    report = tmp_path / "validation.md"
    write_report([Issue("error", "birds", "boom"), Issue("warning", "pets", "meh")], report)
    text = report.read_text(encoding="utf-8")
    assert "## Errors (1)" in text
    assert "- [birds] boom" in text
    assert "## Warnings (1)" in text
