"""Model client: one OpenAI-compatible client with an ordered fallback chain.

Every call returns the model id, token counts and the cost the provider
reports, so the decision log never has to guess them. Free routes report a
cost of 0; paid Hack Club routes are skipped unless DAILY_BUDGET_USD > 0.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

import httpx

from config import ModelRoute, Settings, get_settings


class LLMError(RuntimeError):
    """Raised when no model in the chain returned a usable answer."""


@dataclass
class LLMResult:
    text: str
    model: str | None
    provider: str | None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float = 0.0
    latency_s: float = 0.0
    attempts: list[str] = field(default_factory=list)


_FENCE_START = re.compile(r"^```(?:json|JSON)?\s*")
_FENCE_END = re.compile(r"\s*```\s*$")
_THINK = re.compile(r"<think>.*?</think>", re.S)

# Provider error bodies can carry account metadata (organisation ids) or echo a key. Strip both before an
# error string reaches model_attempts, the decision log or the UI.
_SECRETS = re.compile(
    r"\borg_[A-Za-z0-9]+"
    r"|\b(?:sk|gsk|nvapi)[-_][A-Za-z0-9_-]{8,}"
    r"|\bBearer\s+[A-Za-z0-9._-]{8,}")


def redact(text: str | None) -> str:
    """Remove organisation ids and anything that looks like an API key from provider error text."""
    return _SECRETS.sub("[REDACTED]", text or "")


def extract_json(text: str | None) -> Any:
    """Parse the first JSON object or array in a model reply."""
    if not text or not text.strip():
        raise ValueError("empty reply")
    cleaned = _THINK.sub("", text).strip()
    cleaned = _FENCE_END.sub("", _FENCE_START.sub("", cleaned)).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON object found in the reply")
    start = min(starts)
    closer = "}" if cleaned[start] == "{" else "]"
    end = cleaned.rfind(closer)
    if end <= start:
        raise ValueError("unterminated JSON in the reply")
    return json.loads(cleaned[start:end + 1])


class BaseLLM:
    """Interface shared by the real client and the test stub."""

    def chat(self, messages: list[dict], *, tier: str = "main", max_tokens: int = 2500,
             temperature: float = 0.2) -> LLMResult:
        raise NotImplementedError

    def chat_json(self, system: str, user: str, *, tier: str = "main", max_tokens: int = 3000,
                  temperature: float = 0.2, validate: Callable[[Any], Any] | None = None,
                  retries: int = 1) -> tuple[Any, LLMResult]:
        """Ask for JSON; on a parse or validation error, ask once more with the error."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        cost, tin, tout, attempts = 0.0, 0, 0, []
        last_error: Exception | None = None
        for _ in range(retries + 1):
            result = self.chat(messages, tier=tier, max_tokens=max_tokens, temperature=temperature)
            cost += result.cost or 0.0
            tin += result.tokens_in or 0
            tout += result.tokens_out or 0
            attempts += result.attempts
            try:
                data = extract_json(result.text)
                if validate is not None:
                    data = validate(data)
            except Exception as exc:  # noqa: BLE001 - any parse/validation failure triggers one repair turn
                last_error = exc
                messages = messages + [
                    {"role": "assistant", "content": (result.text or "")[:6000]},
                    {"role": "user", "content": (
                        f"Your reply could not be used ({type(exc).__name__}: {str(exc)[:300]}). "
                        "Reply again with ONLY one valid JSON object in the requested shape. No markdown fences.")},
                ]
                continue
            result.cost = round(cost, 6)
            result.tokens_in = tin or None
            result.tokens_out = tout or None
            result.attempts = attempts
            return data, result
        raise LLMError(redact(f"model reply was not valid JSON after {retries + 1} attempts: {last_error}"))


class OpenAICompatLLM(BaseLLM):
    """Calls OpenAI-compatible chat endpoints, trying each route in order."""

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=self.settings.request_timeout)
        self._spend_lock = threading.Lock()

    # --- spend tracking for optional paid routes (default budget is $0, so paid routes are never used)
    def _spend_file(self):
        return self.settings.data_dir / "spend.json"

    def _spent_today(self) -> float:
        try:
            data = json.loads(self._spend_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0.0
        return float(data.get(date.today().isoformat(), 0.0))

    def _add_spend(self, amount: float) -> None:
        with self._spend_lock:
            path = self._spend_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            key = date.today().isoformat()
            data[key] = round(float(data.get(key, 0.0)) + amount, 6)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def chat(self, messages: list[dict], *, tier: str = "main", max_tokens: int = 2500,
             temperature: float = 0.2) -> LLMResult:
        routes = self.settings.chain(tier)
        if not routes:
            raise LLMError(
                "No model is configured. Put a free key in .env (HACKCLUB_API_KEY, GROQ_API_KEY or "
                "NVIDIA_API_KEY), or set OLLAMA_BASE_URL to use a local Ollama model.")
        attempts: list[str] = []
        for route in routes:
            if route.paid and self._spent_today() >= self.settings.daily_budget_usd:
                attempts.append(f"{route.label}: skipped (paid route, daily budget reached)")
                continue
            started = time.time()
            try:
                result = self._call(route, messages, max_tokens, temperature)
            except Exception as exc:  # noqa: BLE001 - try the next route on any failure
                attempts.append(f"{route.label}: {type(exc).__name__}: {redact(str(exc))[:160]}")
                continue
            result.latency_s = round(time.time() - started, 2)
            result.attempts = attempts + [f"{route.label}: ok"]
            if result.cost:
                self._add_spend(result.cost)
            return result
        raise LLMError(redact("All models failed: " + " | ".join(attempts)))

    def _call(self, route: ModelRoute, messages: list[dict], max_tokens: int, temperature: float) -> LLMResult:
        base = self.settings.base_url(route.provider)
        url = f"{base}/v1/chat/completions" if route.provider == "ollama" else f"{base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        key = self.settings.api_key(route.provider)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {"model": route.model, "messages": messages, "max_tokens": max_tokens,
                   "temperature": temperature}
        resp = self.client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {redact(resp.text)[:200]}")
        data = resp.json()
        if data.get("error") and not data.get("choices"):
            raise LLMError(redact(str(data["error"]))[:200])
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content")
        if not content or not str(content).strip():
            raise LLMError(f"empty content (finish_reason={choice.get('finish_reason')})")
        usage = data.get("usage") or {}
        reported = usage.get("cost")
        # Free tiers and local models do not charge; Hack Club reports the cost it charged.
        cost = float(reported) if reported is not None else 0.0
        return LLMResult(text=str(content), model=data.get("model") or route.model, provider=route.provider,
                         tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"),
                         cost=cost)


class FakeLLM(BaseLLM):
    """STUBBED model used only by the test suite. Never used by the app."""

    def __init__(self, responder: Callable[[list[dict], str], Any] | None = None, model: str = "stub/fake-llm"):
        self.responder = responder or (lambda messages, tier: {})
        self.model = model
        self.calls: list[dict] = []

    def chat(self, messages: list[dict], *, tier: str = "main", max_tokens: int = 2500,
             temperature: float = 0.2) -> LLMResult:
        self.calls.append({"messages": messages, "tier": tier})
        reply = self.responder(messages, tier)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMResult(text=text, model=self.model, provider="stub", tokens_in=0, tokens_out=0,
                         cost=0.0, attempts=["stub: ok"])


def task_id_of(messages: list[dict]) -> str:
    """Return the TASK_ID line agents put in their user message (used by test stubs)."""
    for message in reversed(messages):
        if message.get("role") == "user":
            match = re.search(r"TASK_ID:\s*([\w.\-]+)", message.get("content") or "")
            if match:
                return match.group(1)
    return ""


def get_llm(settings: Settings | None = None) -> BaseLLM:
    return OpenAICompatLLM(settings)
