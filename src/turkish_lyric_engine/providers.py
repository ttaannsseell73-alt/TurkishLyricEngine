"""Bounded stdlib JSON model adapters; API keys never enter manifests/logs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ProviderError(ValueError):
    pass


class JsonProvider(Protocol):
    name: str
    model: str
    live: bool
    def complete(self, stage: str, system: str, payload: dict, schema: dict) -> dict: ...


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpJsonProvider:
    live = True

    def __init__(self, model: str, *, kind: str = "openai", base_url: str | None = None,
                 api_key: str | None = None, timeout: float = 60, max_output_tokens: int = 8000):
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise ProviderError("a model name must be configured explicitly")
        if kind not in {"openai", "compatible", "ollama"}:
            raise ProviderError("unknown provider kind")
        self.name, self.model = kind, model
        self.base_url = (base_url or ("http://127.0.0.1:11434" if kind == "ollama" else "https://api.openai.com/v1")).rstrip("/")
        parsed = urlsplit(self.base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
            raise ProviderError("invalid model base URL")
        if parsed.scheme not in {"https", "http"}:
            raise ProviderError("model endpoint must use HTTP(S)")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ProviderError("remote model endpoint requires HTTPS")
        self._key = api_key or (os.environ.get("OPENAI_API_KEY") if kind == "openai" else os.environ.get("TLE_API_KEY"))
        if kind == "openai" and not self._key:
            raise ProviderError("OPENAI_API_KEY is missing; configure it locally, never put it in GitHub/chat")
        if not 0 < timeout <= 120 or not 100 <= max_output_tokens <= 32000:
            raise ProviderError("invalid timeout/token bound")
        self.timeout, self.max_output_tokens = timeout, max_output_tokens
        self.last_usage: dict = {}
        self._opener = build_opener(NoRedirect())

    def complete(self, stage: str, system: str, payload: dict, schema: dict) -> dict:
        prompt = json.dumps(payload, ensure_ascii=False)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        if self.name == "ollama":
            url = self.base_url + "/api/chat"
            body = {"model": self.model, "messages": messages, "stream": False, "format": schema,
                    "options": {"num_predict": self.max_output_tokens}}
        else:
            url = self.base_url + "/chat/completions"
            body = {"model": self.model, "messages": messages, "max_completion_tokens": self.max_output_tokens,
                    "response_format": {"type": "json_schema", "json_schema": {"name": stage, "strict": True, "schema": schema}}}
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = "Bearer " + self._key
        request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ProviderError("model response exceeds size limit")
            envelope = json.loads(data)
        except HTTPError as exc:
            # Provider error bodies can echo private prompt/API data. Never log them.
            exc.close()
            raise ProviderError(f"model HTTP {exc.code}; no automatic retry") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError("model connection failed or timed out; no automatic retry") from None
        except (ValueError, TypeError) as exc:
            raise ProviderError("model transport returned invalid JSON") from None
        try:
            if self.name == "ollama":
                if envelope.get("done") is not True or envelope.get("done_reason") not in {None, "stop"}:
                    raise ProviderError("model response was incomplete/refused")
                content = envelope["message"]["content"]
                self.last_usage = {k: envelope[k] for k in ("prompt_eval_count", "eval_count") if k in envelope}
            else:
                choice = envelope["choices"][0]
                if choice.get("finish_reason") != "stop":
                    raise ProviderError("model response was incomplete/refused")
                message = choice["message"]
                if message.get("refusal"):
                    raise ProviderError("model refused this generation")
                content = message["content"]
                self.last_usage = envelope.get("usage") or {}
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError("model did not return a complete JSON object") from None
        if not isinstance(result, dict):
            raise ProviderError("model JSON root must be an object")
        return result


class ReplayProvider:
    """Explicit fixture playback only; never a live generation success."""
    name, model, live = "replay", "technical-fixture", False

    def __init__(self, path: str | Path):
        self._rows = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(self._rows, list):
            raise ProviderError("replay must contain an ordered response array")
        self._index = 0

    def complete(self, stage: str, system: str, payload: dict, schema: dict) -> dict:
        if self._index >= len(self._rows):
            raise ProviderError("replay responses exhausted")
        row = self._rows[self._index]
        self._index += 1
        if not isinstance(row, dict) or row.get("stage") != stage or not isinstance(row.get("response"), dict):
            raise ProviderError("replay stage mismatch")
        return json.loads(json.dumps(row["response"]))


def configured_provider(*, kind: str | None = None, model: str | None = None, base_url: str | None = None) -> HttpJsonProvider:
    return HttpJsonProvider(model or os.environ.get("TLE_MODEL", ""), kind=kind or os.environ.get("TLE_PROVIDER", "openai"),
                            base_url=base_url or os.environ.get("TLE_BASE_URL"))
