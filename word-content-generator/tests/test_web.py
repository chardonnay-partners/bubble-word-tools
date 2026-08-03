import json

from fastapi.testclient import TestClient

from wcg.core.llm import LlmError
from wcg.core.store import CategoryStore
from wcg.web.app import create_app, slugify
from tests.conftest import FakeLlm, make_category

SETTINGS = {"model": "m", "item_min": 4, "item_max": 5,
            "locales": ["en", "tr"], "propose_variants": 3,
            "max_llm_retries": 3}
THEMES = {"themes": [{"id": "animals", "hint": "animal kingdom"}]}


def build_client(tmp_path, llm, sheet_config=None):
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
    (config / "themes.json").write_text(json.dumps(THEMES), encoding="utf-8")
    if sheet_config:
        (config / "sheet.json").write_text(json.dumps(sheet_config), encoding="utf-8")
    data = tmp_path / "categories"
    data.mkdir(exist_ok=True)
    app = create_app(data_dir=data, config_dir=config, llm_factory=lambda: llm)
    return TestClient(app), CategoryStore(data)


def variant(name="Planets", words=("Mars", "Venus", "Jupiter", "Saturn")):
    return {"name": name, "descriptor": name, "theme": "animals",
            "difficulty": 1, "words": list(words)}


def test_health(tmp_path):
    client, _ = build_client(tmp_path, None)
    assert client.get("/api/health").json() == {"status": "ok"}


def test_slugify():
    assert slugify("Gas Giants!") == "gas-giants"
    assert slugify("  ") == "category"


def test_propose_returns_valid_variants_only(tmp_path):
    llm = FakeLlm([[variant(),
                    variant("Gas Giants", ("Jupiter", "Saturn", "Uranus", "Neptune")),
                    "garbage"]])
    client, _ = build_client(tmp_path, llm)
    response = client.post("/api/propose", json={"topic": "planets"})
    assert response.status_code == 200
    assert [v["name"] for v in response.json()["variants"]] == ["Planets", "Gas Giants"]


def test_propose_without_api_key_returns_503(tmp_path):
    client, _ = build_client(tmp_path, None)
    assert client.post("/api/propose", json={"topic": "planets"}).status_code == 503


def test_propose_empty_topic_returns_400(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([]))
    assert client.post("/api/propose", json={"topic": "   "}).status_code == 400


def test_propose_llm_error_returns_502(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([LlmError("down")]))
    response = client.post("/api/propose", json={"topic": "planets"})
    assert response.status_code == 502
    assert "down" in response.json()["error"]


def test_select_saves_approved_and_localizes_in_background(tmp_path):
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, store = build_client(tmp_path, llm)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.status_code == 200
    assert response.json()["warnings"] == ["sheet: push to Google Sheet not configured"]
    assert response.json()["category"]["names"] == {"en": "Planets"}
    saved = store.load_all()["planets"]
    assert saved.status == "approved"
    assert saved.names == {"en": "Planets", "tr": "Gezegenler"}
    assert saved.words_for("tr") == ["Mars", "Venüs", "Jüpiter", "Satürn"]


def test_select_localization_failure_still_saves_en_only(tmp_path):
    llm = FakeLlm([LlmError("boom")])
    client, store = build_client(tmp_path, llm)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.status_code == 200
    assert response.json()["warnings"] == ["sheet: push to Google Sheet not configured"]
    saved = store.load_all()["planets"]
    assert saved.status == "approved"
    assert "tr" not in saved.names


def test_select_without_api_key_saves_en_only(tmp_path):
    client, store = build_client(tmp_path, None)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.status_code == 200
    assert "ANTHROPIC_API_KEY is not set" in response.json()["warnings"][0]
    saved = store.load_all()["planets"]
    assert saved.status == "approved"
    assert "tr" not in saved.names


def test_select_id_collision_gets_suffix(tmp_path):
    llm = FakeLlm([
        {"name": "Gezegenler", "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]},
        {"name": "Gezegenler", "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]},
    ])
    client, _ = build_client(tmp_path, llm)
    client.post("/api/select", json={"variant": variant()})
    response = client.post("/api/select", json={"variant": variant()})
    assert response.json()["category"]["id"] == "planets-2"


def test_select_invalid_variant_returns_400(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([]))
    response = client.post("/api/select",
                           json={"variant": {"name": "X", "words": ["a"]}})
    assert response.status_code == 400


def test_categories_listing_and_filters(tmp_path):
    client, store = build_client(tmp_path, None)
    store.save(make_category(cid="birds", theme="animals", status="approved",
                             words=("Pigeon", "Crow", "Eagle"), refs=("owls",)))
    store.save(make_category(cid="pizza", theme="food", status="draft"))
    data = client.get("/api/categories", params={"status": "approved"}).json()
    assert len(data["categories"]) == 1
    entry = data["categories"][0]
    assert entry["id"] == "birds"
    assert entry["descriptor"] == "Birds"
    assert entry["items"] == ["Pigeon", "Crow", "Eagle", "-> owls"]


def test_stats_endpoint(tmp_path):
    client, store = build_client(tmp_path, None)
    store.save(make_category(cid="birds", status="approved"))
    stats = client.get("/api/stats").json()
    assert stats["total"] == 1
    assert stats["by_status"] == {"approved": 1}


def test_select_appends_localization_csv(tmp_path):
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, _ = build_client(tmp_path, llm)
    client.post("/api/select", json={"variant": variant()})
    lines = (tmp_path / "localization.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Key,English(en),Turkish(tr)"
    assert lines[1] == "planets,Planets,Gezegenler"
    assert lines[2] == "planets.mars,Mars,Mars"


def test_select_csv_has_empty_cells_on_failed_locale(tmp_path):
    llm = FakeLlm([LlmError("boom")])
    client, _ = build_client(tmp_path, llm)
    client.post("/api/select", json={"variant": variant()})
    lines = (tmp_path / "localization.csv").read_text(encoding="utf-8").splitlines()
    assert lines[1] == "planets,Planets,"


def test_localization_csv_download(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([]))
    assert client.get("/api/localization.csv").status_code == 404
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, _ = build_client(tmp_path, llm)
    client.post("/api/select", json={"variant": variant()})
    response = client.get("/api/localization.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "planets.mars" in response.text


def test_select_id_comes_from_descriptor(tmp_path):
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, store = build_client(tmp_path, llm)
    body = variant()
    body["descriptor"] = "Solar System Planets"
    response = client.post("/api/select", json={"variant": body})
    assert response.json()["category"]["id"] == "solar-system-planets"
    saved = store.load_all()["solar-system-planets"]
    assert saved.descriptor == "Solar System Planets"
    assert saved.names["en"] == "Planets"


def test_select_missing_descriptor_returns_400(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([]))
    body = variant()
    del body["descriptor"]
    assert client.post("/api/select", json={"variant": body}).status_code == 400


def test_static_responses_are_no_cache(tmp_path):
    client, _ = build_client(tmp_path, None)
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/api/health").headers.get("cache-control") != "no-cache"


SHEET_CONFIG = {"webhook_url": "https://example.test/exec", "token": "tok"}


def test_select_pushes_en_rows_then_backfill_updates(tmp_path, monkeypatch):
    calls = []

    def fake_push(rows, url, token, action=None):
        calls.append((rows, url, token, action))
        return {"inserted": len(rows), "skipped": 0}

    monkeypatch.setattr("wcg.web.app.push_rows", fake_push)
    monkeypatch.setattr("wcg.core.backfill.push_rows", fake_push)
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, _ = build_client(tmp_path, llm, sheet_config=SHEET_CONFIG)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.json()["warnings"] == []
    rows, url, token, action = calls[0]
    assert url == "https://example.test/exec"
    assert token == "tok"
    assert action is None
    assert rows[0] == ["planets", "Planets", ""]
    assert rows[1] == ["planets.mars", "Mars", ""]
    assert len(rows) == 5
    rows, _, _, action = calls[1]
    assert action == "updateRows"
    assert rows[0] == ["planets", "Planets", "Gezegenler"]
    assert rows[1] == ["planets.mars", "Mars", "Mars"]


def test_select_push_failure_is_warning_only(tmp_path, monkeypatch):
    from wcg.core.sheet import SheetPushError

    def fake_push(rows, url, token, action=None):
        raise SheetPushError("request failed: down")

    monkeypatch.setattr("wcg.web.app.push_rows", fake_push)
    monkeypatch.setattr("wcg.core.backfill.push_rows", fake_push)
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, store = build_client(tmp_path, llm, sheet_config=SHEET_CONFIG)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.status_code == 200
    assert response.json()["warnings"] == ["sheet: request failed: down"]
    assert "planets" in store.load_all()
    assert "planets.mars" in (tmp_path / "localization.csv").read_text(encoding="utf-8")


def test_sheet_config_falls_back_to_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SHEET_WEBHOOK_URL", "https://env.test/exec")
    monkeypatch.setenv("SHEET_TOKEN", "env-tok")
    calls = []

    def fake_push(rows, url, token, action=None):
        calls.append((url, token))
        return {"inserted": len(rows), "skipped": 0}

    monkeypatch.setattr("wcg.web.app.push_rows", fake_push)
    monkeypatch.setattr("wcg.core.backfill.push_rows", fake_push)
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, _ = build_client(tmp_path, llm)  # no sheet.json file
    response = client.post("/api/select", json={"variant": variant()})
    assert response.json()["warnings"] == []
    assert calls[0] == ("https://env.test/exec", "env-tok")


def test_select_stamps_created(tmp_path):
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, store = build_client(tmp_path, llm)
    response = client.post("/api/select", json={"variant": variant()})
    created = response.json()["category"]["created"]
    assert created and created.endswith("+00:00")
    assert store.load_all()["planets"].created == created


def test_localize_missing_without_api_key_returns_503(tmp_path):
    client, _ = build_client(tmp_path, None)
    assert client.post("/api/localize-missing").status_code == 503


def test_localize_missing_sweeps_approved_pool(tmp_path):
    llm = FakeLlm([{"name": "Kuşlar",
                    "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]}])
    client, store = build_client(tmp_path, llm)
    store.save(make_category(cid="birds", status="approved"))
    store.save(make_category(cid="pizza", status="draft"))
    response = client.post("/api/localize-missing")
    assert response.status_code == 200
    data = response.json()
    assert data["localized"] == ["birds"]
    assert data["failed"] == []
    assert data["warnings"] == ["sheet: push to Google Sheet not configured"]
    saved = store.load_all()["birds"]
    assert saved.names["tr"] == "Kuşlar"
    assert saved.words_for("tr") == ["Güvercin", "Karga", "Kartal", "Baykuş"]
    assert "tr" not in store.load_all()["pizza"].names
    lines = (tmp_path / "localization.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Key,English(en),Turkish(tr)"
    assert lines[1] == "birds,Birds,Kuşlar"


def test_localize_missing_skips_complete_and_collects_failures(tmp_path):
    llm = FakeLlm([LlmError("boom")])
    client, store = build_client(tmp_path, llm)
    done = make_category(cid="birds", status="approved",
                         names={"en": "Birds", "tr": "Kuşlar"})
    for item in done.items:
        item.word["tr"] = item.word["en"]
    store.save(done)
    store.save(make_category(cid="cats", status="approved",
                             words=("Siamese", "Persian", "Tabby", "Sphynx")))
    data = client.post("/api/localize-missing").json()
    assert data["localized"] == []
    assert data["failed"] == [["cats", "tr", "boom"]]
    assert data["warnings"] == []


def test_stats_reports_missing_translations(tmp_path):
    client, store = build_client(tmp_path, None)
    store.save(make_category(cid="birds", status="approved"))
    assert client.get("/api/stats").json()["missing_translations"] == 1


def test_startup_sweeps_missing_translations(tmp_path):
    import time

    llm = FakeLlm([{"name": "Kuşlar",
                    "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]}])
    client, store = build_client(tmp_path, llm)
    store.save(make_category(cid="birds", status="approved"))
    with client:  # entering the context runs the lifespan startup
        for _ in range(200):
            if "tr" in store.load_all()["birds"].names:
                break
            time.sleep(0.01)
    assert store.load_all()["birds"].names["tr"] == "Kuşlar"


def test_categories_newest_first_then_legacy_alphabetical(tmp_path):
    client, store = build_client(tmp_path, None)
    store.save(make_category(cid="birds", status="approved"))
    first = make_category(cid="pizza", status="approved")
    first.created = "2026-07-20T09:00:00+00:00"
    store.save(first)
    second = make_category(cid="cheese", status="approved")
    second.created = "2026-07-21T09:00:00+00:00"
    store.save(second)
    ids = [c["id"] for c in client.get("/api/categories").json()["categories"]]
    assert ids == ["cheese", "pizza", "birds"]
