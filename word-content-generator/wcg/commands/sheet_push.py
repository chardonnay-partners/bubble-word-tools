import csv
import json
from pathlib import Path

from ..core.sheet import SheetPushError, push_rows


def run(config_dir, csv_path):
    config_path = Path(config_dir) / "sheet.json"
    if not config_path.exists():
        print(f"ERROR {config_path} not found. "
              "See docs/sheet-webhook-setup.md for setup.")
        return 2
    config = json.loads(config_path.read_text(encoding="utf-8"))
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"ERROR {csv_path} not found")
        return 2
    with open(csv_path, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))[1:]
    if not rows:
        print("nothing to push")
        return 0
    try:
        result = push_rows(rows, config["webhook_url"], config["token"])
    except SheetPushError as error:
        print(f"ERROR {error}")
        return 1
    print(f"pushed {len(rows)} rows: {result.get('inserted', 0)} inserted, "
          f"{result.get('skipped', 0)} already in sheet")
    return 0
