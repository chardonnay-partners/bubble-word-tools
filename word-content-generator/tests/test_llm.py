from types import SimpleNamespace

import pytest

from wcg.core.llm import LlmClient, LlmError


class FakeAnthropic:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        text = self.texts.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


def make_client(texts):
    fake = FakeAnthropic(texts)
    return LlmClient("test-model", max_retries=3, client=fake, backoff=0), fake


def test_parses_json_response():
    client, _ = make_client(['[{"id": "birds"}]'])
    assert client.complete_json("sys", "user") == [{"id": "birds"}]


def test_strips_code_fences():
    client, _ = make_client(['```json\n{"name": "Birds"}\n```'])
    assert client.complete_json("sys", "user") == {"name": "Birds"}


def test_retries_on_invalid_json_then_succeeds():
    client, fake = make_client(["not json at all", '{"ok": true}'])
    assert client.complete_json("sys", "user") == {"ok": True}
    assert fake.calls == 2


def test_raises_llm_error_after_max_retries():
    client, fake = make_client(["bad", "bad", "bad"])
    with pytest.raises(LlmError, match="failed after 3 attempts"):
        client.complete_json("sys", "user")
    assert fake.calls == 3


def test_parses_single_line_fenced_response():
    client, _ = make_client(['```json{"ok": true}```'])
    assert client.complete_json("sys", "user") == {"ok": True}


class FakeAnthropicBlocks:
    def __init__(self, blocks):
        self.blocks = blocks
        self.messages = self

    def create(self, **kwargs):
        return SimpleNamespace(content=self.blocks)


def test_skips_thinking_blocks():
    fake = FakeAnthropicBlocks([
        SimpleNamespace(thinking="reasoning..."),
        SimpleNamespace(text='{"ok": true}'),
    ])
    client = LlmClient("test-model", max_retries=1, client=fake, backoff=0)
    assert client.complete_json("sys", "user") == {"ok": True}


def test_no_text_blocks_raises_llm_error():
    fake = FakeAnthropicBlocks([SimpleNamespace(thinking="only thinking")])
    client = LlmClient("test-model", max_retries=1, client=fake, backoff=0)
    with pytest.raises(LlmError, match="no text blocks"):
        client.complete_json("sys", "user")
