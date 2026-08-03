import json
import os
from pathlib import Path

from .models import Category, SchemaError


class CategoryStore:
    def __init__(self, root):
        self.root = Path(root)

    def load_all(self):
        pool = {}
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise SchemaError(f"{path.name}: invalid JSON: {error}")
            category = Category.from_dict(data)
            if category.id != path.stem:
                raise SchemaError(
                    f"{path.name}: inner id '{category.id}' does not match filename")
            pool[category.id] = category
        return pool

    def save(self, category):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{category.id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(category.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        os.replace(tmp, path)
        return path

    def by_status(self, status):
        return [c for c in self.load_all().values() if c.status == status]
