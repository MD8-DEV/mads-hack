"""Model chain tests. Every HTTP call goes to httpx.MockTransport (STUBBED); nothing reaches a real API."""
from __future__ import annotations

import json

import httpx
import pytest

from config import DEFAULT_FAST_CHAIN, DEFAULT_MAIN_CHAIN, ModelRoute, Settings, parse_chain
from llm import FakeLLM, LLMError, OpenAICompatLLM, extract_json, task_id_of


def make_settings(tmp_path, main: str, *, budget: float = 0.0) -> Settings:
    return Settings(data_dir=tmp_path, main_chain=parse_chain(main), fast_chain=parse_chain(main),
                    request_timeout=5, daily_budget_usd=budget, research_enabled=False, research_timeout=5)


def ok_reply(model: str, content: str = '{"ok": true}') -> httpx.Response:
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 7, "completion_tokens": 3}})


@pytest.fixture()
def keys(monkeypatch):
    for name in ("HACKCLUB_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.setenv(name, "test-placeholder")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")


def test_parse_chain():
    routes = parse_chain("hackclub:nvidia/x:free, groq:openai/gpt-oss-120b,unknown:model,ollama:qwen3:8b,bad")
    assert [r.label for r in routes] == ["hackclub:nvidia/x:free", "groq:openai/gpt-oss-120b", "ollama:qwen3:8b"]
    assert routes[2].model == "qwen3:8b"  # the model name keeps its own colon
    assert not routes[0].paid and ModelRoute("hackclub", "some/model").paid
    assert not ModelRoute("groq", "x").paid and not ModelRoute("ollama", "qwen3:8b").paid
    assert parse_chain(DEFAULT_MAIN_CHAIN)[-1].label == "ollama:qwen3:8b"
    assert parse_chain(DEFAULT_FAST_CHAIN)[-1].label == "ollama:qwen3:8b"
    assert not any(r.paid for r in parse_chain(DEFAULT_MAIN_CHAIN) + parse_chain(DEFAULT_FAST_CHAIN))


def test_routes_without_keys_are_not_ready(tmp_path, monkeypatch):
    for name in ("HACKCLUB_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = make_settings(tmp_path, DEFAULT_MAIN_CHAIN)
    assert settings.chain("main") == []
    with pytest.raises(LLMError):
        OpenAICompatLLM(settings, client=httpx.Client(transport=httpx.MockTransport(lambda r: ok_reply("x"))))\
            .chat([{"role": "user", "content": "hi"}])
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")
    assert [r.provider for r in settings.chain("main")] == ["ollama"]


def test_paid_route_skipped_with_zero_budget(tmp_path, keys):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["model"])
        return ok_reply("openai/gpt-oss-120b")

    settings = make_settings(tmp_path, "hackclub:paid/model,groq:openai/gpt-oss-120b")
    llm = OpenAICompatLLM(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert seen == ["openai/gpt-oss-120b"]
    assert "skipped" in result.attempts[0] and result.provider == "groq" and result.cost == 0


def test_fallback_on_http_429(tmp_path, keys):
    def handler(request):
        if "hackclub" in str(request.url):
            return httpx.Response(429, json={"error": "rate limited"})
        return ok_reply("openai/gpt-oss-120b")

    settings = make_settings(tmp_path, "hackclub:free/model:free,groq:openai/gpt-oss-120b")
    llm = OpenAICompatLLM(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result.provider == "groq" and "429" in result.attempts[0]
    assert result.tokens_in == 7 and result.tokens_out == 3


def test_fallback_on_timeout_to_local_ollama(tmp_path, keys):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        if "groq" in str(request.url):
            raise httpx.ReadTimeout("timed out", request=request)
        return ok_reply("qwen3:8b")

    settings = make_settings(tmp_path, "groq:openai/gpt-oss-120b,ollama:qwen3:8b")
    llm = OpenAICompatLLM(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result.provider == "ollama" and result.model == "qwen3:8b" and result.cost == 0
    assert "ReadTimeout" in result.attempts[0]
    assert urls[-1] == "http://ollama.test:11434/v1/chat/completions"


def test_all_routes_failing_raises(tmp_path, keys):
    settings = make_settings(tmp_path, "groq:a,nvidia:b")
    llm = OpenAICompatLLM(settings, client=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down"))))
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('<think>reasoning {"no": 1}</think>\n{"a": 2}') == {"a": 2}
    assert extract_json('Here you go: {"a": [1, 2]} hope it helps') == {"a": [1, 2]}
    assert extract_json("[1, 2]") == [1, 2]
    for bad in ("", "   ", "no json here"):
        with pytest.raises(ValueError):
            extract_json(bad)


def test_fake_llm_routes_by_task_id_and_repairs_once():
    replies = {"strategist.sharpen": ["not json", {"title": "FIXTURE"}]}

    def responder(messages, tier):
        return replies[task_id_of(messages)].pop(0)

    fake = FakeLLM(responder)
    user = "TASK_ID: strategist.sharpen\nINPUT (JSON): {}"
    data, result = fake.chat_json("system", user, validate=lambda d: d if d.get("title") else 1 / 0)
    assert data == {"title": "FIXTURE"} and len(fake.calls) == 2
    assert result.model == "stub/fake-llm" and result.cost == 0
    with pytest.raises(LLMError):
        FakeLLM(lambda m, t: "never json").chat_json("s", "TASK_ID: x.y")


def test_provider_errors_are_redacted(tmp_path, keys):
    body = ('{"error": {"message": "Rate limit reached for model in organization org_01abcDEF23ghij on tokens. '
            'Key gsk_ABCdef1234567890xyz was used; also sk-proj-abcdefgh12345678 and nvapi-QWERTY12345678"}}')

    def handler(request):
        if "groq" in str(request.url):
            return httpx.Response(429, text=body)
        return ok_reply("qwen3:8b")

    settings = make_settings(tmp_path, "groq:openai/gpt-oss-120b,ollama:qwen3:8b")
    llm = OpenAICompatLLM(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = llm.chat([{"role": "user", "content": "hi"}])
    joined = " ".join(result.attempts)
    assert "HTTP 429" in joined and "[REDACTED]" in joined
    for secret in ("org_01abcDEF23ghij", "gsk_ABCdef", "sk-proj-abcdefgh", "nvapi-QWERTY"):
        assert secret not in joined
    failing = OpenAICompatLLM(make_settings(tmp_path, "groq:openai/gpt-oss-120b"),
                              client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, text=body))))
    with pytest.raises(LLMError) as err:
        failing.chat([{"role": "user", "content": "hi"}])
    assert "org_01abc" not in str(err.value) and "gsk_ABC" not in str(err.value)
