import base64
import json
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..commands.stats import compute_stats
from ..core.backfill import run_backfill
from ..core.llm import LlmError
from ..core.models import Category
from ..core.propose import run_propose, validate_variant
from ..core.sheet import SheetPushError, append_rows, build_rows, push_rows
from ..core.store import CategoryStore


class ProposeBody(BaseModel):
    topic: str


class SelectBody(BaseModel):
    variant: dict


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "category"


def unique_id(slug, pool):
    if slug not in pool:
        return slug
    suffix = 2
    while f"{slug}-{suffix}" in pool:
        suffix += 1
    return f"{slug}-{suffix}"


def create_app(data_dir="data/categories", config_dir="config", llm_factory=None,
               levels_dir=None):
    @asynccontextmanager
    async def lifespan(app):
        llm = factory()
        if llm is not None:
            interval = float(os.environ.get("WCG_SWEEP_MINUTES", "15")) * 60

            def sweep_loop():
                while True:
                    try:
                        auto_backfill(llm)
                    except Exception as error:
                        print(f"backfill sweep crashed: {error!r}")
                    time.sleep(interval)

            threading.Thread(target=sweep_loop, daemon=True).start()
        yield

    app = FastAPI(lifespan=lifespan)
    store = CategoryStore(Path(data_dir))
    csv_path = Path(data_dir).parent / "localization.csv"
    config_path = Path(config_dir)
    settings = json.loads((config_path / "settings.json").read_text(encoding="utf-8"))
    themes = json.loads((config_path / "themes.json").read_text(encoding="utf-8"))["themes"]
    theme_ids = [t["id"] for t in themes]
    sheet_path = config_path / "sheet.json"
    if sheet_path.exists():
        sheet_config = json.loads(sheet_path.read_text(encoding="utf-8"))
    elif os.environ.get("SHEET_WEBHOOK_URL") and os.environ.get("SHEET_TOKEN"):
        sheet_config = {"webhook_url": os.environ["SHEET_WEBHOOK_URL"],
                        "token": os.environ["SHEET_TOKEN"]}
    else:
        sheet_config = None

    def default_factory():
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        from ..core.llm import LlmClient
        return LlmClient(settings["model"], settings.get("max_llm_retries", 3))

    factory = llm_factory or default_factory

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/propose")
    def propose(body: ProposeBody):
        llm = factory()
        if llm is None:
            return JSONResponse({"error": "ANTHROPIC_API_KEY is not set"},
                                status_code=503)
        topic = body.topic.strip()
        if not topic:
            return JSONResponse({"error": "topic is empty"}, status_code=400)
        try:
            variants = run_propose(topic, store, llm, settings, themes)
        except LlmError as error:
            return JSONResponse({"error": str(error)}, status_code=502)
        return {"variants": variants}

    locale_attempts = {}

    def auto_backfill(llm, cid=None):
        result = run_backfill(store, llm, settings, csv_path, sheet_config,
                              only_ids=None if cid is None else {cid},
                              attempts=locale_attempts)
        for failed_id, locale, reason in result["failed"]:
            print(f"backfill {failed_id} {locale}: {reason}")
        for warning in result["warnings"]:
            print(f"backfill: {warning}")

    @app.post("/api/select")
    def select(body: SelectBody, background_tasks: BackgroundTasks):
        llm = factory()
        variant, reason = validate_variant(body.variant, theme_ids, settings)
        if variant is None:
            return JSONResponse({"error": f"invalid variant: {reason}"},
                                status_code=400)
        pool = store.load_all()
        cid = unique_id(slugify(variant["descriptor"]), pool)
        category = Category.from_dict({
            "id": cid,
            "descriptor": variant["descriptor"],
            "theme": variant["theme"],
            "difficulty": variant["difficulty"],
            "image": None,
            "status": "approved",
            "items": [{"word": {"en": word}} for word in variant["words"]],
            "names": {"en": variant["name"]},
            "created": datetime.now(timezone.utc).isoformat(),
        })
        warnings = []
        if llm is None:
            warnings.append("localization skipped, ANTHROPIC_API_KEY is not set")
        store.save(category)
        try:
            append_rows(category, csv_path, settings["locales"])
        except (OSError, ValueError) as error:
            warnings.append(f"sheet: {error}")
        if sheet_config is None:
            warnings.append("sheet: push to Google Sheet not configured")
        else:
            try:
                push_rows(build_rows(category, settings["locales"]),
                          sheet_config["webhook_url"], sheet_config["token"])
            except SheetPushError as error:
                warnings.append(f"sheet: {error}")
        if llm is not None:
            background_tasks.add_task(auto_backfill, llm, cid)
        return {"category": category.to_dict(), "warnings": warnings}

    @app.post("/api/localize-missing")
    def localize_missing():
        # Manual repair: retries even locales the automatic sweep gave up on.
        llm = factory()
        if llm is None:
            return JSONResponse({"error": "ANTHROPIC_API_KEY is not set"},
                                status_code=503)
        return run_backfill(store, llm, settings, csv_path, sheet_config)

    @app.get("/api/categories")
    def categories(status: str = "", theme: str = ""):
        rows = []
        pool = sorted(store.load_all().values(), key=lambda c: c.id)
        pool.sort(key=lambda c: c.created or "", reverse=True)
        for category in pool:
            if status and category.status != status:
                continue
            if theme and category.theme != theme:
                continue
            items = [item.word["en"] if item.word else f"-> {item.ref}"
                     for item in category.items]
            rows.append({"id": category.id, "name": category.names["en"],
                         "descriptor": category.descriptor_or_name(),
                         "theme": category.theme, "status": category.status,
                         "difficulty": category.difficulty, "items": items})
        return {"categories": rows}

    @app.get("/api/stats")
    def stats():
        return compute_stats(store.load_all(), settings["locales"])

    @app.get("/api/localization.csv")
    def localization_csv():
        if not csv_path.exists():
            return JSONResponse({"error": "no localization rows yet"},
                                status_code=404)
        return FileResponse(csv_path, media_type="text/csv",
                            filename="localization.csv")

    @app.middleware("http")
    async def no_cache_static(request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Optional HTTP Basic Auth. Set APP_BASIC_AUTH="user:pass" (e.g. as a Coolify
    # env var) to gate the whole app; unset = open (local dev). The health check
    # stays open so the platform's container health probe still works.
    auth = os.environ.get("APP_BASIC_AUTH", "").strip()
    if ":" in auth:
        exp_user, exp_pass = auth.split(":", 1)

        @app.middleware("http")
        async def basic_auth(request, call_next):
            if request.url.path == "/api/health":
                return await call_next(request)
            ok = False
            header = request.headers.get("authorization", "")
            if header.startswith("Basic "):
                try:
                    user, _, pw = base64.b64decode(
                        header[6:]).decode("utf-8").partition(":")
                    ok = (secrets.compare_digest(user, exp_user)
                          and secrets.compare_digest(pw, exp_pass))
                except Exception:
                    ok = False
            if not ok:
                return Response("Authentication required", status_code=401,
                                headers={"WWW-Authenticate":
                                         'Basic realm="Bubble Word Tools"'})
            return await call_next(request)

    # One unified single-page tool: the Level Generator (with a native Word
    # Content tab) is served at /, and talks to the /api/* endpoints directly.
    levels = Path(levels_dir) if levels_dir else \
        Path(os.environ.get("WCG_LEVELS_DIR",
                            Path(__file__).resolve().parents[3] / "level-generator"))
    if levels.is_dir():
        app.mount("/", StaticFiles(directory=levels, html=True), name="app")
    return app


def run():
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
