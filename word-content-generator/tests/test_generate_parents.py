from wcg.commands.generate import run_generate_parents
from wcg.core.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def seeded_store(tmp_path):
    store = CategoryStore(tmp_path)
    for cid in ("birds", "cats", "dogs", "fish"):
        store.save(make_category(cid=cid, theme="animals",
                                 words=(f"{cid}-a", f"{cid}-b", f"{cid}-c", f"{cid}-d")))
    return store


def parent(cid="animals", children=("birds", "cats", "dogs", "fish")):
    return {"id": cid, "name": "Animals", "difficulty": 2, "children": list(children)}


def test_parent_saved_with_ref_items(tmp_path):
    store = seeded_store(tmp_path)
    llm = FakeLlm([[parent()]])
    result = run_generate_parents(1, store, llm, SETTINGS)
    assert result["accepted"] == ["animals"]
    saved = store.load_all()["animals"]
    assert saved.refs() == ["birds", "cats", "dogs", "fish"]
    assert saved.status == "draft"
    assert saved.theme == "animals"


def test_unknown_child_rejected(tmp_path):
    store = seeded_store(tmp_path)
    llm = FakeLlm([[parent(children=("birds", "cats", "dogs", "ghost"))]])
    result = run_generate_parents(1, store, llm, SETTINGS)
    assert result["accepted"] == []
    assert "unknown child" in result["rejected"][0][1]


def test_duplicate_children_rejected(tmp_path):
    store = seeded_store(tmp_path)
    llm = FakeLlm([[parent(children=("birds", "birds", "cats", "dogs"))]])
    result = run_generate_parents(1, store, llm, SETTINGS)
    assert result["accepted"] == []
    assert "duplicate children" in result["rejected"][0][1]


def test_existing_ids_listed_in_prompt(tmp_path):
    store = seeded_store(tmp_path)
    llm = FakeLlm([[]])
    run_generate_parents(1, store, llm, SETTINGS)
    _, user_prompt = llm.calls[0]
    for cid in ("birds", "cats", "dogs", "fish"):
        assert cid in user_prompt
