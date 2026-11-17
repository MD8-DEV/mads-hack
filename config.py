"""Runtime settings, read from environment variables (and an optional .env file).

No paid service is required. The default model chains use free open-weight
models (Hack Club free tier, Groq free tier, NVIDIA build free tier) and fall
back to a local Ollama model when OLLAMA_BASE_URL is set.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv reads .env for local runs; Docker passes env vars directly
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent
if load_dotenv is not None:
    load_dotenv(ROOT / ".env", override=False)

# provider -> (base-url env var, default base url, api-key env var)
PROVIDERS: dict[str, tuple[str, str, str | None]] = {
    "hackclub": ("HACKCLUB_BASE_URL", "https://ai.hackclub.com/proxy/v1", "HACKCLUB_API_KEY"),
    "groq": ("GROQ_BASE_URL", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "nvidia": ("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "ollama": ("OLLAMA_BASE_URL", "", None),
}

# Ordered fallback chains, "provider:model" separated by commas.
DEFAULT_MAIN_CHAIN = (
    "hackclub:nvidia/nemotron-3-ultra-550b-a55b:free,"
    "groq:openai/gpt-oss-120b,"
    "nvidia:nvidia/nemotron-3-ultra-550b-a55b,"
    "hackclub:nvidia/nemotron-3.5-super-vl:free,"
    "ollama:qwen3:8b"
)
DEFAULT_FAST_CHAIN = (
    "hackclub:google/gemma-4-26b-a4b-it:free,"
    "groq:openai/gpt-oss-120b,"
    "hackclub:nvidia/nemotron-3.5-super-vl:free,"
    "nvidia:nvidia/nemotron-3-ultra-550b-a55b,"
    "ollama:qwen3:8b"
)


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def paid(self) -> bool:
        """Hack Club models without the ':free' suffix draw on credits; everything else is free or local."""
        return self.provider == "hackclub" and not self.model.endswith(":free")


def parse_chain(text: str) -> list[ModelRoute]:
    routes: list[ModelRoute] = []
    for part in (text or "").split(","):
        part = part.strip()
        if ":" not in part:
            continue
        provider, model = part.split(":", 1)
        provider, model = provider.strip().lower(), model.strip()
        if provider in PROVIDERS and model:
            routes.append(ModelRoute(provider, model))
    return routes


@dataclass
class Settings:
    data_dir: Path
    main_chain: list[ModelRoute]
    fast_chain: list[ModelRoute]
    request_timeout: float
    daily_budget_usd: float
    research_enabled: bool
    research_timeout: float

    def base_url(self, provider: str) -> str:
        env_name, default, _ = PROVIDERS[provider]
        return (os.getenv(env_name) or default).rstrip("/")

    def api_key(self, provider: str) -> str | None:
        key_env = PROVIDERS[provider][2]
        value = os.getenv(key_env) if key_env else None
        return value or None

    def route_ready(self, route: ModelRoute) -> bool:
        if route.provider == "ollama":
            return bool(self.base_url("ollama"))
        return bool(self.api_key(route.provider))

    def chain(self, tier: str = "main") -> list[ModelRoute]:
        routes = self.fast_chain if tier == "fast" else self.main_chain
        return [r for r in routes if self.route_ready(r)]

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    def describe_models(self) -> dict[str, list[str]]:
        return {
            "main": [r.label for r in self.chain("main")],
            "fast": [r.label for r in self.chain("fast")],
        }


def load_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR") or (ROOT / "data"))
    return Settings(
        data_dir=data_dir,
        main_chain=parse_chain(os.getenv("MODEL_CHAIN_MAIN") or DEFAULT_MAIN_CHAIN),
        fast_chain=parse_chain(os.getenv("MODEL_CHAIN_FAST") or DEFAULT_FAST_CHAIN),
        request_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS") or 90),
        daily_budget_usd=float(os.getenv("DAILY_BUDGET_USD") or 0),
        research_enabled=os.getenv("RESEARCH_ENABLED", "1").strip().lower() not in ("0", "false", "no"),
        research_timeout=float(os.getenv("RESEARCH_TIMEOUT_SECONDS") or 20),
    )


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = load_settings()
    return _SETTINGS
