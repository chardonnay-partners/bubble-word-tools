import json

import pytest

from wcg.core.models import SchemaError
from wcg.core.store import CategoryStore
from tests.conftest import make_category


def test_save_and_load_roundtrip(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    category = make_category()
    path = store.save(category)
    assert path.name == "birds.json"
    pool = store.load_all()
    assert list(pool) == ["birds"]
    assert pool["birds"].to_dict() == category.to_dict()


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category())
    assert [p.name for p in tmp_path.iterdir()] == ["birds.json"]


def test_load_rejects_filename_id_mismatch(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds"))
    (tmp_path / "birds.json").rename(tmp_path / "crows.json")
    with pytest.raises(SchemaError, match="does not match filename"):
        store.load_all()


def test_load_rejects_invalid_json_shape(tmp_path):
    store = CategoryStore(tmp_path)
    (tmp_path / "bad.json").write_text(json.dumps({"id": "bad"}), encoding="utf-8")
    with pytest.raises(SchemaError):
        store.load_all()


def test_by_status_filters(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    store.save(make_category(cid="crows", status="draft"))
    assert [c.id for c in store.by_status("approved")] == ["birds"]
