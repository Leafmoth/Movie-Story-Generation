from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional before deps are installed
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv(ROOT_DIR / ".env")


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default).strip()
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if items:
        return items
    return tuple(item.strip() for item in default.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str | None
    model_name: str
    temperature: float
    max_tokens: int | None
    request_timeout: int
    output_root: Path
    prompt_dir: Path
    mock_llm: bool
    cors_allow_origins: tuple[str, ...]
    cors_allow_credentials: bool
    cors_allow_methods: tuple[str, ...]
    cors_allow_headers: tuple[str, ...]


def get_settings() -> Settings:
    _load_env()
    output_root = Path(os.getenv("OUTPUT_ROOT", ROOT_DIR / "outputs"))
    prompt_dir = Path(os.getenv("PROMPT_DIR", ROOT_DIR / "prompts"))
    max_tokens_raw = os.getenv("MAX_TOKENS", "").strip()

    return Settings(
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL") or None,
        model_name=os.getenv("MODEL_NAME", os.getenv("DEEPSEEK_MODEL", "gpt-4o-mini")),
        temperature=_float_env("TEMPERATURE", 0.7),
        max_tokens=int(max_tokens_raw) if max_tokens_raw else None,
        request_timeout=_int_env("REQUEST_TIMEOUT", 180),
        output_root=output_root,
        prompt_dir=prompt_dir,
        mock_llm=os.getenv("MOCK_LLM", "").lower() in {"1", "true", "yes", "on"},
        cors_allow_origins=_csv_env("CORS_ALLOW_ORIGINS", "*"),
        cors_allow_credentials=_bool_env("CORS_ALLOW_CREDENTIALS", False),
        cors_allow_methods=_csv_env("CORS_ALLOW_METHODS", "*"),
        cors_allow_headers=_csv_env("CORS_ALLOW_HEADERS", "*"),
    )
