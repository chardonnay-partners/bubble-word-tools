import argparse
import json
import os
import sys
from pathlib import Path

from .core.store import CategoryStore
from .commands import validate as validate_cmd


def load_settings(config_dir):
    return json.loads((Path(config_dir) / "settings.json").read_text(encoding="utf-8"))


def require_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    print("ERROR ANTHROPIC_API_KEY is not set. Get a key at "
          "https://console.anthropic.com and run: export ANTHROPIC_API_KEY=sk-ant-...")
    return False


def build_parser():
    parser = argparse.ArgumentParser(prog="wcg")
    parser.add_argument("--data-dir", default="data/categories")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--output-dir", default="output")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    generate = sub.add_parser("generate")
    generate.add_argument("--theme")
    generate.add_argument("--count", type=int, default=20)
    generate.add_argument("--parents", action="store_true")
    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_sub.add_parser("export")
    review_import = review_sub.add_parser("import")
    review_import.add_argument("csv_path")
    localize = sub.add_parser("localize")
    localize.add_argument("--locale", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--format", choices=("bubble", "ws"), default="bubble")
    compile_parser.add_argument("--locale")
    sub.add_parser("stats")
    sub.add_parser("sheet-push")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config_dir)
    store = CategoryStore(Path(args.data_dir))
    reports_dir = Path(args.reports_dir)
    if args.command == "validate":
        return validate_cmd.run(store, settings, reports_dir / "validation.md")
    if args.command == "generate":
        if not require_api_key():
            return 2
        from .core.llm import LlmClient
        from .commands import generate as generate_cmd
        themes = json.loads(
            (Path(args.config_dir) / "themes.json").read_text(encoding="utf-8"))["themes"]
        llm = LlmClient(settings["model"], settings.get("max_llm_retries", 3))
        if args.parents:
            result = generate_cmd.run_generate_parents(args.count, store, llm, settings)
            print(f"parents: {len(result['accepted'])} accepted, "
                  f"{len(result['rejected'])} rejected")
            return validate_cmd.run(store, settings, reports_dir / "validation.md")
        if not args.theme:
            print("ERROR --theme is required unless --parents is set")
            return 2
        theme_ids = [t["id"] for t in themes] if args.theme == "all" else [args.theme]
        report_lines = []
        for theme_id in theme_ids:
            result = generate_cmd.run_generate(
                theme_id, args.count, store, llm, settings, themes)
            print(f"{theme_id}: {len(result['accepted'])} accepted, "
                  f"{len(result['rejected'])} rejected")
            report_lines += [f"- [{theme_id}] {label}: {reason}"
                             for label, reason in result["rejected"]]
        if report_lines:
            reports_dir.mkdir(parents=True, exist_ok=True)
            with open(reports_dir / "generate.md", "a", encoding="utf-8") as handle:
                handle.write("\n".join(report_lines) + "\n")
        return validate_cmd.run(store, settings, reports_dir / "validation.md")
    if args.command == "review":
        from .commands import review as review_cmd
        if args.review_command == "export":
            count = review_cmd.export_drafts(store, reports_dir / "review.csv")
            print(f"exported {count} drafts to {reports_dir / 'review.csv'}")
            return 0
        try:
            result = review_cmd.import_decisions(store, Path(args.csv_path), settings)
        except review_cmd.ReviewImportError as error:
            print(f"IMPORT ABORTED, no changes applied:\n{error}")
            return 1
        print(f"approved {result['approved']}, rejected {result['rejected']}, "
              f"skipped {result['skipped']}")
        return validate_cmd.run(store, settings, reports_dir / "validation.md")
    if args.command == "localize":
        if not require_api_key():
            return 2
        from .core.llm import LlmClient
        from .core.localize import run_localize
        llm = LlmClient(settings["model"], settings.get("max_llm_retries", 3))
        result = run_localize(args.locale, store, llm, settings)
        print(f"localized {len(result['localized'])}, failed {len(result['failed'])}")
        for cid, reason in result["failed"]:
            print(f"FAILED {cid}: {reason}")
        return 0 if not result["failed"] else 1
    if args.command == "compile":
        from .commands import compile_cmd
        locales = (args.locale.split(",") if args.locale else settings["locales"])
        return compile_cmd.run(store, settings, Path(args.output_dir),
                               args.format, locales)
    if args.command == "stats":
        from .commands import stats as stats_cmd
        return stats_cmd.run(store, settings)
    if args.command == "sheet-push":
        from .commands import sheet_push
        return sheet_push.run(args.config_dir,
                              Path(args.data_dir).parent / "localization.csv")
    return 2


if __name__ == "__main__":
    sys.exit(main())
