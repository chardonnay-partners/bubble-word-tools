import json

from wcg.core.localize import run_localize, localize_category, localize_system
from wcg.core.llm import LlmError
from wcg.core.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def test_localizes_missing_locale(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    llm = FakeLlm([{"name": "Kuşlar",
                    "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]}])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result["localized"] == ["birds"]
    saved = store.load_all()["birds"]
    assert saved.names["tr"] == "Kuşlar"
    assert saved.words_for("tr") == ["Güvercin", "Karga", "Kartal", "Baykuş"]
    payload = json.loads(llm.calls[0][1])
    assert payload["words"] == ["Pigeon", "Crow", "Eagle", "Owl"]
    assert payload["category"] == "Birds"
    assert payload["name"] == "Birds"


def test_localize_payload_carries_full_descriptor(tmp_path):
    category = make_category(cid="indian-snacks", status="approved",
                             names={"en": "Indian Snacks"})
    category.descriptor = "Indian Snacks and Street Food"
    llm = FakeLlm([{"name": "Hint Atıştırmalıkları",
                    "words": ["Samosa", "Pakora", "Chaat", "Biryani"]}])
    localize_category(category, "tr", llm)
    payload = json.loads(llm.calls[0][1])
    assert payload["category"] == "Indian Snacks and Street Food"
    assert payload["name"] == "Indian Snacks"


def test_skips_drafts_and_complete_categories(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="draft-cat", status="draft"))
    complete = make_category(cid="done", status="approved",
                             names={"en": "Done", "tr": "Bitti"})
    for item in complete.items:
        item.word["tr"] = item.word["en"] + "-tr"
    store.save(complete)
    llm = FakeLlm([])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result == {"localized": [], "failed": []}
    assert llm.calls == []


def test_wrong_word_count_fails_category_untouched(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    llm = FakeLlm([{"name": "Kuşlar", "words": ["Güvercin"]}])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result["localized"] == []
    assert result["failed"][0][0] == "birds"
    assert "tr" not in store.load_all()["birds"].names


def test_duplicate_localized_words_fails_category_untouched(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    llm = FakeLlm([{"name": "Kuşlar", "words": ["At", "at", "Kartal", "Baykuş"]}])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result["localized"] == []
    assert result["failed"] == [("birds", "duplicate localized words")]
    assert "tr" not in store.load_all()["birds"].names


def test_llm_error_recorded_and_continues(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    store.save(make_category(cid="cats", status="approved",
                             words=("Siamese", "Persian", "Tabby", "Sphynx")))
    llm = FakeLlm([LlmError("boom"),
                   {"name": "Kediler",
                    "words": ["Siyam", "İran", "Tekir", "Sfenks"]}])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result["localized"] == ["cats"]
    assert result["failed"] == [("birds", "boom")]


def test_ref_items_ignored(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    store.save(make_category(cid="animals", status="approved",
                             words=("Horse", "Snake", "Frog"), refs=("birds",)))
    llm = FakeLlm([
        {"name": "Hayvanlar", "words": ["At", "Yılan", "Kurbağa"]},
        {"name": "Kuşlar", "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]},
    ])
    result = run_localize("tr", store, llm, SETTINGS)
    assert sorted(result["localized"]) == ["animals", "birds"]
    assert store.load_all()["animals"].words_for("tr") == ["At", "Yılan", "Kurbağa"]


def test_localize_category_skips_complete(tmp_path):
    category = make_category(cid="done", status="approved",
                             names={"en": "Done", "tr": "Bitti"})
    for item in category.items:
        item.word["tr"] = item.word["en"] + "-tr"
    llm = FakeLlm([])
    assert localize_category(category, "tr", llm) == ("skipped", None)
    assert llm.calls == []


def test_localize_category_mutates_but_does_not_save(tmp_path):
    store = CategoryStore(tmp_path)
    category = make_category(cid="birds", status="approved")
    store.save(category)
    llm = FakeLlm([{"name": "Kuşlar",
                    "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]}])
    outcome, reason = localize_category(category, "tr", llm)
    assert (outcome, reason) == ("localized", None)
    assert category.names["tr"] == "Kuşlar"
    assert "tr" not in store.load_all()["birds"].names


def test_localize_category_failure_reason():
    category = make_category(cid="birds", status="approved")
    llm = FakeLlm([{"name": "Kuşlar", "words": ["At", "at", "Kartal", "Baykuş"]}])
    assert localize_category(category, "tr", llm) == ("failed", "duplicate localized words")


def test_localize_system_proper_noun_rules():
    system = localize_system("tr")
    assert "NEVER translated" in system
    assert "Drinkwater" in system
    assert "Nueva York" in system
    assert "Londra" in system


def test_localize_system_keeps_name_short():
    assert "never more than 2 words" in localize_system("tr")


def test_localize_system_forbids_item_substitution():
    system = localize_system("ja")
    assert "NEVER swap" in system
    assert "Samosa" in system
    assert "Takoyaki" in system
