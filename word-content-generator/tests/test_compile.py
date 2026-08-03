from wcg.commands import compile_cmd
from wcg.games.bubble import compile_bubble
from wcg.games.ws import compile_ws
from wcg.core.store import CategoryStore
from tests.conftest import make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def localized(cid, words, names, status="approved", refs=()):
    category = make_category(cid=cid, status=status,
                             words=tuple(w[0] for w in words), refs=refs, names=names)
    word_items = [item for item in category.items if item.word]
    for item, (en, tr) in zip(word_items, words):
        item.word["tr"] = tr
    return category


BIRD_WORDS = [("Pigeon", "Güvercin"), ("Crow", "Karga"),
              ("Eagle", "Kartal"), ("Owl", "Baykuş")]


def test_compile_bubble_includes_complete_categories():
    birds = localized("birds", BIRD_WORDS, {"en": "Birds", "tr": "Kuşlar"})
    payload, warnings = compile_bubble({"birds": birds}, ["en", "tr"])
    assert warnings == []
    entry = payload["categories"][0]
    assert entry["id"] == "birds"
    assert entry["names"] == {"en": "Birds", "tr": "Kuşlar"}
    assert entry["items"][0] == {"word": {"en": "Pigeon", "tr": "Güvercin"}}


def test_compile_bubble_skips_missing_locale_and_cascades_to_parents():
    birds = make_category(cid="birds", status="approved")
    animals = make_category(cid="animals", status="approved",
                            words=("Horse", "Snake", "Frog"), refs=("birds",))
    grand = make_category(cid="alive", status="approved",
                          words=("Tree", "Moss", "Fern"), refs=("animals",))
    payload, warnings = compile_bubble(
        {"birds": birds, "animals": animals, "alive": grand}, ["en", "tr"])
    assert payload["categories"] == []
    assert len(warnings) == 3


def test_compile_bubble_excludes_drafts():
    draft = make_category(cid="birds", status="draft")
    payload, warnings = compile_bubble({"birds": draft}, ["en"])
    assert payload["categories"] == []
    assert warnings == []


def test_compile_ws_flattens_refs_to_child_names():
    birds = localized("birds", BIRD_WORDS, {"en": "Birds", "tr": "Kuşlar"})
    animals = localized("animals",
                        [("Horse", "At"), ("Snake", "Yılan"), ("Frog", "Kurbağa")],
                        {"en": "Animals", "tr": "Hayvanlar"}, refs=("birds",))
    output, warnings = compile_ws({"birds": birds, "animals": animals}, "tr")
    assert warnings == []
    by_name = {entry["categoryId"]: entry["wordsIds"] for entry in output}
    assert by_name["Hayvanlar"] == ["At", "Yılan", "Kurbağa", "Kuşlar"]


def test_compile_ws_skips_incomplete_locale_with_warning():
    birds = make_category(cid="birds", status="approved")
    output, warnings = compile_ws({"birds": birds}, "tr")
    assert output == []
    assert "birds" in warnings[0]


def test_compile_ws_warns_on_duplicate_category_id():
    birds = localized("birds", BIRD_WORDS, {"en": "Birds", "tr": "Kuşlar"})
    cats = localized("cats",
                     [("Siamese", "Siyam"), ("Persian", "Iran"),
                      ("Tabby", "Sarman"), ("Sphynx", "Sfenks")],
                     {"en": "Birds", "tr": "Kediler"})
    output, warnings = compile_ws({"birds": birds, "cats": cats}, "en")
    assert len(output) == 2
    assert any("duplicate categoryId" in w and "Birds" in w for w in warnings)


def test_compile_bubble_cascades_exclusion_through_localized_parents():
    birds = make_category(cid="birds", status="approved")
    animals = localized("animals",
                        [("Horse", "At"), ("Snake", "Yılan"), ("Frog", "Kurbağa")],
                        {"en": "Animals", "tr": "Hayvanlar"}, refs=("birds",))
    alive = localized("alive",
                      [("Tree", "Ağaç"), ("Moss", "Yosun"), ("Fern", "Eğrelti")],
                      {"en": "Alive", "tr": "Canlı"}, refs=("animals",))
    payload, warnings = compile_bubble(
        {"birds": birds, "animals": animals, "alive": alive}, ["en", "tr"])
    assert payload["categories"] == []
    assert any("birds" in w and "missing locales" in w for w in warnings)
    assert any("animals" in w and "refs excluded category" in w for w in warnings)
    assert any("alive" in w and "refs excluded category" in w for w in warnings)
    assert len(warnings) == 3


def test_run_aborts_on_cyclic_pool_and_writes_nothing(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    a = make_category(cid="a", words=("Foo", "Bar", "Baz"), refs=("b",),
                      status="approved")
    b = make_category(cid="b", words=("Qux", "Quux", "Corge"), refs=("a",),
                      status="approved")
    store.save(a)
    store.save(b)
    output_dir = tmp_path / "output"
    result = compile_cmd.run(store, SETTINGS, output_dir, "bubble", ["en"])
    assert result == 1
    assert not output_dir.exists()


def test_run_returns_error_when_all_categories_skipped(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    store.save(make_category(cid="birds", status="approved"))
    output_dir = tmp_path / "output"
    result = compile_cmd.run(store, SETTINGS, output_dir, "bubble", ["en", "tr"])
    assert result == 1
    assert (output_dir / "categories_bubble.json").exists()


def test_run_returns_ok_on_happy_path(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    birds = localized("birds", BIRD_WORDS, {"en": "Birds", "tr": "Kuşlar"})
    store.save(birds)
    output_dir = tmp_path / "output"
    result = compile_cmd.run(store, SETTINGS, output_dir, "bubble", ["en", "tr"])
    assert result == 0
    assert (output_dir / "categories_bubble.json").exists()
