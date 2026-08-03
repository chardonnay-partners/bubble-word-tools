from wcg.commands.stats import compute_stats
from tests.conftest import make_category


def test_compute_stats():
    birds = make_category(cid="birds", theme="animals", status="approved")
    for item in birds.items:
        item.word["tr"] = item.word["en"] + "-tr"
    birds.names["tr"] = "Kuşlar"
    cats = make_category(cid="cats", theme="animals", status="approved",
                         words=("Siamese", "Persian", "Tabby", "Sphynx"))
    pizza = make_category(cid="pizza", theme="food-drink", status="draft")
    pool = {c.id: c for c in (birds, cats, pizza)}
    stats = compute_stats(pool, ["en", "tr"])
    assert stats["total"] == 3
    assert stats["by_status"] == {"approved": 2, "draft": 1}
    assert stats["by_theme"] == {"animals": 2, "food-drink": 1}
    assert stats["locale_coverage"] == {"en": 100.0, "tr": 50.0}
    assert stats["missing_translations"] == 1


def test_empty_pool():
    stats = compute_stats({}, ["en"])
    assert stats["total"] == 0
    assert stats["locale_coverage"] == {"en": 0.0}
    assert stats["missing_translations"] == 0
