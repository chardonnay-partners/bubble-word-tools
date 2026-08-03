from pathlib import Path

from wcg.core.backfill import missing_locales, run_backfill
from wcg.core.llm import LlmError
from wcg.core.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"locales": ["en", "tr"], "item_min": 4, "item_max": 5}


def test_missing_locales_ignores_en_and_complete():
    category = make_category(cid="birds", status="approved")
    assert missing_locales(category, ["en", "tr"]) == ["tr"]
    category.names["tr"] = "Kuşlar"
    for item in category.items:
        item.word["tr"] = item.word["en"]
    assert missing_locales(category, ["en", "tr"]) == []


def test_gives_up_after_max_attempts(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    store.save(make_category(cid="birds", status="approved"))
    llm = FakeLlm([LlmError("boom"), LlmError("boom"), LlmError("boom")])
    attempts = {}
    csv_path = tmp_path / "localization.csv"
    for _ in range(3):
        run_backfill(store, llm, SETTINGS, csv_path, None, attempts=attempts)
    assert len(llm.calls) == 2  # third run skips: gave up on ('birds', 'tr')
    assert attempts == {("birds", "tr"): 2}


def test_no_attempts_dict_means_unlimited_retries(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    store.save(make_category(cid="birds", status="approved"))
    llm = FakeLlm([LlmError("boom")] * 3)
    csv_path = tmp_path / "localization.csv"
    for _ in range(3):
        run_backfill(store, llm, SETTINGS, csv_path, None)
    assert len(llm.calls) == 3


def test_success_after_transient_failure(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    store.save(make_category(cid="birds", status="approved"))
    llm = FakeLlm([LlmError("boom"),
                   {"name": "Kuşlar",
                    "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]}])
    attempts = {}
    csv_path = tmp_path / "localization.csv"
    first = run_backfill(store, llm, SETTINGS, csv_path, None, attempts=attempts)
    assert first["failed"] == [["birds", "tr", "boom"]]
    second = run_backfill(store, llm, SETTINGS, csv_path, None, attempts=attempts)
    assert second["localized"] == ["birds"]
    assert store.load_all()["birds"].names["tr"] == "Kuşlar"
    assert "Kuşlar" in Path(csv_path).read_text(encoding="utf-8")
