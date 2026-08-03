from wcg.core.models import Category, Item


def make_category(cid="birds", theme="animals", status="draft",
                  words=("Pigeon", "Crow", "Eagle", "Owl"), refs=(),
                  difficulty=1, names=None):
    items = [Item(word={"en": word}) for word in words]
    items += [Item(ref=ref) for ref in refs]
    return Category(id=cid, theme=theme, difficulty=difficulty, status=status,
                    items=items, names=names or {"en": cid.replace("-", " ").title()})


class FakeLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
