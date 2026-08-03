import pytest

from wcg.core.models import Category, Item, SchemaError


def valid_category_dict():
    return {
        "id": "birds",
        "theme": "animals",
        "difficulty": 1,
        "image": None,
        "status": "draft",
        "items": [
            {"word": {"en": "Pigeon", "tr": "Güvercin"}},
            {"word": {"en": "Crow"}},
            {"word": {"en": "Eagle"}},
            {"ref": "owls"},
        ],
        "names": {"en": "Birds", "tr": "Kuşlar"},
    }


def test_category_roundtrip():
    data = valid_category_dict()
    category = Category.from_dict(data)
    assert category.id == "birds"
    assert category.to_dict() == data


def test_words_for_and_refs():
    category = Category.from_dict(valid_category_dict())
    assert category.words_for("en") == ["Pigeon", "Crow", "Eagle"]
    assert category.words_for("tr") == ["Güvercin"]
    assert category.refs() == ["owls"]


def test_item_requires_exactly_one_of_word_or_ref():
    with pytest.raises(SchemaError):
        Item.from_dict({"word": {"en": "Pigeon"}, "ref": "owls"})
    with pytest.raises(SchemaError):
        Item.from_dict({})


def test_empty_word_text_rejected():
    with pytest.raises(SchemaError):
        Item.from_dict({"word": {"en": "  "}})


def test_word_item_requires_en_locale():
    with pytest.raises(SchemaError):
        Item.from_dict({"word": {"tr": "Güvercin"}})


@pytest.mark.parametrize("field,value", [
    ("id", "Birds"),
    ("id", "birds_x"),
    ("difficulty", 0),
    ("difficulty", 4),
    ("difficulty", "1"),
    ("status", "pending"),
    ("names", {"tr": "Kuşlar"}),
    ("names", {"en": ""}),
    ("items", []),
])
def test_invalid_category_fields_rejected(field, value):
    data = valid_category_dict()
    data[field] = value
    with pytest.raises(SchemaError):
        Category.from_dict(data)


DESCRIPTOR_BASE = {"id": "australian-animals", "theme": "animals",
                   "difficulty": 1, "image": None, "status": "draft",
                   "items": [{"word": {"en": "Kangaroo"}}],
                   "names": {"en": "Animals"}}


def test_descriptor_round_trip():
    category = Category.from_dict(dict(DESCRIPTOR_BASE,
                                       descriptor="Australian Animals"))
    assert category.descriptor == "Australian Animals"
    assert category.descriptor_or_name() == "Australian Animals"
    assert category.to_dict()["descriptor"] == "Australian Animals"


def test_descriptor_absent_falls_back_to_en_name():
    category = Category.from_dict(dict(DESCRIPTOR_BASE))
    assert category.descriptor is None
    assert category.descriptor_or_name() == "Animals"
    assert "descriptor" not in category.to_dict()


def test_descriptor_empty_rejected():
    with pytest.raises(SchemaError):
        Category.from_dict(dict(DESCRIPTOR_BASE, descriptor="   "))


def test_created_round_trips_when_set():
    data = valid_category_dict()
    data["created"] = "2026-07-21T10:00:00+00:00"
    category = Category.from_dict(data)
    assert category.created == "2026-07-21T10:00:00+00:00"
    assert category.to_dict()["created"] == "2026-07-21T10:00:00+00:00"


def test_created_absent_stays_none_and_off_dict():
    category = Category.from_dict(valid_category_dict())
    assert category.created is None
    assert "created" not in category.to_dict()


def test_created_empty_string_rejected():
    data = valid_category_dict()
    data["created"] = "  "
    with pytest.raises(SchemaError):
        Category.from_dict(data)
