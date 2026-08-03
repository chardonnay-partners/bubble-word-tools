import json
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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

    # Tabbed shell: Level Generator (default) + Word Content, served as one app.
    @app.get("/", response_class=HTMLResponse)
    def shell():
        return SHELL_HTML

    # Level generator — self-contained static tool, served as the default tab.
    levels = Path(levels_dir) if levels_dir else \
        Path(os.environ.get("WCG_LEVELS_DIR",
                            Path(__file__).resolve().parents[3] / "level-generator"))
    if levels.is_dir():
        app.mount("/levels", StaticFiles(directory=levels, html=True), name="levels")

    # Word Content generator UI (this app's own frontend; talks to /api/*).
    app.mount("/word", StaticFiles(directory=Path(__file__).parent / "static",
                                   html=True), name="word")
    return app


SHELL_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bubble Word Tools</title>
<style>
  html,body{margin:0;height:100%;background:#0f1420;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  .tabs{display:flex;gap:4px;background:#171e2e;border-bottom:1px solid #2a3552;padding:6px 10px;align-items:center;height:33px;box-sizing:border-box}
  .tabs .brand{color:#e6ebf5;font-weight:700;margin-right:14px;font-size:14px;white-space:nowrap}
  .tabs button{font:inherit;color:#8b97b5;background:transparent;border:1px solid transparent;border-radius:7px;padding:5px 15px;cursor:pointer}
  .tabs button:hover{color:#e6ebf5}
  .tabs button.active{color:#e6ebf5;background:#1e2740;border-color:#38456b}
  .frames{position:absolute;top:46px;left:0;right:0;bottom:0}
  iframe{border:0;width:100%;height:100%;display:none;background:#0f1420}
  iframe.active{display:block}
</style></head><body>
  <div class="tabs">
    <span class="brand">🫧 Bubble Word Tools</span>
    <button data-t="levels" class="active">Level Generator</button>
    <button data-t="word">Word Content</button>
  </div>
  <div class="frames">
    <iframe id="f-levels" class="active" src="/levels/"></iframe>
    <iframe id="f-word" src="/word/" loading="lazy"></iframe>
  </div>
  <script>
    const btns=document.querySelectorAll('.tabs button');
    function show(t){
      btns.forEach(x=>x.classList.toggle('active',x.dataset.t===t));
      document.querySelectorAll('iframe').forEach(f=>f.classList.toggle('active',f.id==='f-'+t));
    }
    btns.forEach(b=>b.addEventListener('click',()=>show(b.dataset.t)));
    // Relay the Word Content -> Level Generator hand-off between the two iframes.
    window.addEventListener('message',(e)=>{
      const m=e.data;
      if(m && m.type==='bw-import-categories'){
        const f=document.getElementById('f-levels');
        if(f&&f.contentWindow) f.contentWindow.postMessage(m,'*');
        show('levels');
      }
    });
  </script>
</body></html>"""


def run():
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
