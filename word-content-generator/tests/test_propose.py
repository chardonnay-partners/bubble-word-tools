import pytest

from wcg.core.propose import (build_propose_prompt, propose_system,
                              run_propose, validate_variant)
from wcg.core.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5, "propose_variants": 3}
THEMES = [{"id": "animals", "hint": "animal kingdom"}]


def entry(name="Planets", descriptor="Solar System Planets",
          words=("Mars", "Venus", "Jupiter", "Saturn"),
          theme="animals", difficulty=1):
    return {"name": name, "descriptor": descriptor, "theme": theme,
            "difficulty": difficulty, "words": list(words)}


def test_valid_variant_passes():
    variant, reason = validate_variant(entry(), ["animals"], SETTINGS)
    assert reason is None
    assert variant == {"name": "Planets", "descriptor": "Solar System Planets",
                       "theme": "animals", "difficulty": 1,
                       "words": ["Mars", "Venus", "Jupiter", "Saturn"]}


def test_unknown_theme_maps_to_other():
    variant, _ = validate_variant(entry(theme="space"), ["animals"], SETTINGS)
    assert variant["theme"] == "other"


def test_two_word_name_allowed():
    variant, reason = validate_variant(entry(name="Gas Giants"),
                                       ["animals"], SETTINGS)
    assert reason is None
    assert variant["name"] == "Gas Giants"


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(name=""),
    lambda e: e.update(name="Rocky Inner Planets"),
    lambda e: e.update(descriptor=""),
    lambda e: e.pop("descriptor"),
    lambda e: e.update(words=["a", "b"]),
    lambda e: e.update(words=["Mars", "mars", "Venus", "Pluto"]),
    lambda e: e.update(difficulty=9),
    lambda e: e.pop("words"),
])
def test_invalid_variants_rejected(mutate):
    data = entry()
    mutate(data)
    variant, reason = validate_variant(data, ["animals"], SETTINGS)
    assert variant is None
    assert reason


def test_system_prompt_explains_both_names():
    system = propose_system(4, 5, 3, ["animals"])
    assert "descriptor" in system
    assert "at most 2 words" in system


def test_run_propose_drops_invalid_and_includes_dedup_context(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", theme="animals"))
    llm = FakeLlm([[entry(), entry(words=("a", "b")), "garbage"]])
    variants = run_propose("planets", store, llm, SETTINGS, THEMES)
    assert len(variants) == 1
    system, user = llm.calls[0]
    assert "Topic: planets" in user
    assert "Birds" in user
    assert "pigeon" in user
    assert "animals" in system


def test_prompt_without_pool_context():
    prompt = build_propose_prompt("planets", [], [])
    assert prompt == "Topic: planets"
