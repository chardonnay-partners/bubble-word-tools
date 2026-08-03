import pytest

from wcg.commands.generate import build_user_prompt, run_generate
from wcg.core.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5}
THEMES = [{"id": "animals", "hint": "animal kingdom"}]


def candidate(cid="birds", name="Birds", words=("Pigeon", "Crow", "Eagle", "Owl"), difficulty=1):
    return {"id": cid, "name": name, "difficulty": difficulty, "words": list(words)}


def test_accepted_candidates_saved_as_draft(tmp_path):
    store = CategoryStore(tmp_path)
    llm = FakeLlm([[candidate("birds"), candidate("cats", "Cats", ("Siamese", "Persian", "Tabby", "Sphynx"))]])
    result = run_generate("animals", 2, store, llm, SETTINGS, THEMES)
    assert result["accepted"] == ["birds", "cats"]
    assert result["rejected"] == []
    pool = store.load_all()
    assert pool["birds"].status == "draft"
    assert pool["birds"].theme == "animals"
    assert pool["birds"].words_for("en") == ["Pigeon", "Crow", "Eagle", "Owl"]
    assert pool["birds"].names == {"en": "Birds"}


def test_invalid_candidates_rejected_not_saved(tmp_path):
    store = CategoryStore(tmp_path)
    llm = FakeLlm([[
        candidate("too-few", words=("A", "B")),
        candidate("dup-words", words=("Pigeon", "pigeon", "Crow", "Owl")),
        candidate("Bad_Id"),
        candidate("no-name", name=""),
        "not even an object",
    ]])
    result = run_generate("animals", 5, store, llm, SETTINGS, THEMES)
    assert result["accepted"] == []
    assert len(result["rejected"]) == 5
    assert store.load_all() == {}


def test_existing_id_rejected_and_dedup_context_in_prompt(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", theme="animals"))
    llm = FakeLlm([[candidate("birds")]])
    result = run_generate("animals", 1, store, llm, SETTINGS, THEMES)
    assert result["accepted"] == []
    assert "duplicate id" in result["rejected"][0][1]
    _, user_prompt = llm.calls[0]
    assert "Birds" in user_prompt
    assert "pigeon" in user_prompt


def test_pool_category_descriptor_used_in_dedup_context(tmp_path):
    store = CategoryStore(tmp_path)
    birds = make_category(cid="birds", theme="animals")
    birds.descriptor = "birds-animal-kingdom"
    store.save(birds)
    llm = FakeLlm([[]])
    run_generate("animals", 1, store, llm, SETTINGS, THEMES)
    _, user_prompt = llm.calls[0]
    assert "birds-animal-kingdom" in user_prompt


def test_unknown_theme_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown theme"):
        run_generate("ghosts", 1, CategoryStore(tmp_path), FakeLlm([]), SETTINGS, THEMES)


def test_prompt_mentions_count_and_hint():
    prompt = build_user_prompt(THEMES[0], 7, [], [], [])
    assert "exactly 7" in prompt
    assert "animal kingdom" in prompt
