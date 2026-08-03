import re
from dataclasses import dataclass, field

VALID_STATUSES = ("draft", "approved", "rejected")
ID_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class SchemaError(ValueError):
    pass


@dataclass
class Item:
    word: dict | None = None
    ref: str | None = None

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise SchemaError(f"item must be an object, got {type(data).__name__}")
        if ("word" in data) == ("ref" in data):
            raise SchemaError("item must have exactly one of 'word' or 'ref'")
        if "word" in data:
            word = data["word"]
            if not isinstance(word, dict) or not word:
                raise SchemaError("'word' must be a non-empty object of locale to text")
            if "en" not in word:
                raise SchemaError("word item must contain an 'en' text")
            for locale, text in word.items():
                if not isinstance(text, str) or not text.strip():
                    raise SchemaError(f"word text for locale '{locale}' is empty")
            return cls(word=word)
        ref = data["ref"]
        if not isinstance(ref, str) or not ID_PATTERN.fullmatch(ref):
            raise SchemaError(f"'ref' must be a kebab-case id, got {ref!r}")
        return cls(ref=ref)

    def to_dict(self):
        if self.word is not None:
            return {"word": self.word}
        return {"ref": self.ref}


@dataclass
class Category:
    id: str
    theme: str
    difficulty: int
    status: str
    items: list = field(default_factory=list)
    names: dict = field(default_factory=dict)
    image: str | None = None
    descriptor: str | None = None
    created: str | None = None

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise SchemaError("category must be an object")
        cid = data.get("id")
        if not isinstance(cid, str) or not ID_PATTERN.fullmatch(cid):
            raise SchemaError(f"'id' must be a kebab-case string, got {cid!r}")
        theme = data.get("theme")
        if not isinstance(theme, str) or not theme.strip():
            raise SchemaError(f"{cid}: 'theme' must be a non-empty string")
        difficulty = data.get("difficulty")
        if not isinstance(difficulty, int) or isinstance(difficulty, bool) or not 1 <= difficulty <= 3:
            raise SchemaError(f"{cid}: 'difficulty' must be an integer 1-3, got {difficulty!r}")
        status = data.get("status")
        if status not in VALID_STATUSES:
            raise SchemaError(f"{cid}: 'status' must be one of {VALID_STATUSES}, got {status!r}")
        image = data.get("image")
        if image is not None and (not isinstance(image, str) or not image.strip()):
            raise SchemaError(f"{cid}: 'image' must be null or a non-empty string")
        descriptor = data.get("descriptor")
        if descriptor is not None and (
                not isinstance(descriptor, str) or not descriptor.strip()):
            raise SchemaError(
                f"{cid}: 'descriptor' must be null or a non-empty string")
        created = data.get("created")
        if created is not None and (not isinstance(created, str) or not created.strip()):
            raise SchemaError(f"{cid}: 'created' must be null or a non-empty string")
        raw_items = data.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise SchemaError(f"{cid}: 'items' must be a non-empty list")
        items = [Item.from_dict(entry) for entry in raw_items]
        names = data.get("names")
        if not isinstance(names, dict) or not isinstance(names.get("en"), str) or not names["en"].strip():
            raise SchemaError(f"{cid}: 'names' must contain a non-empty 'en' name")
        for locale, name in names.items():
            if not isinstance(name, str) or not name.strip():
                raise SchemaError(f"{cid}: name for locale '{locale}' is empty")
        return cls(id=cid, theme=theme, difficulty=difficulty, status=status,
                   items=items, names=names, image=image, descriptor=descriptor,
                   created=created)

    def to_dict(self):
        data = {
            "id": self.id,
            "theme": self.theme,
            "difficulty": self.difficulty,
            "image": self.image,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "names": self.names,
        }
        if self.descriptor is not None:
            data["descriptor"] = self.descriptor
        if self.created is not None:
            data["created"] = self.created
        return data

    def words_for(self, locale):
        return [item.word[locale] for item in self.items if item.word and locale in item.word]

    def refs(self):
        return [item.ref for item in self.items if item.ref]

    def descriptor_or_name(self):
        return self.descriptor or self.names["en"]
