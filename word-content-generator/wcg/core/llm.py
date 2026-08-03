import json
import time

import anthropic


class LlmError(Exception):
    pass


class LlmClient:
    def __init__(self, model, max_retries=3, client=None, backoff=1.0):
        self.model = model
        self.max_retries = max_retries
        self.backoff = backoff
        self._client = client or anthropic.Anthropic()

    def complete_json(self, system, user):
        last_error = None
        for attempt in range(self.max_retries):
            if attempt:
                time.sleep(self.backoff * (2 ** (attempt - 1)))
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=8192,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                text = "".join(
                    getattr(block, "text", "") or "" for block in response.content)
                if not text.strip():
                    raise LlmError("response contained no text blocks")
                return self._parse(text)
            except (anthropic.APIError, LlmError) as error:
                last_error = error
        raise LlmError(f"LLM call failed after {self.max_retries} attempts: {last_error}")

    @staticmethod
    def _parse(text):
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removeprefix("json")
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise LlmError(f"response is not valid JSON: {error}")
