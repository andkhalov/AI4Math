"""Каталог моделей Yandex AI Studio для AI4Science: алиасы, окна контекста, URI.

Общий модуль для bin/ai4science.py (запуск Goose) и src/token_proxy.py
(подстановка полного URI, если в запросе короткое имя модели; так работает
`/model <алиас>` внутри сессии). Только стандартная библиотека.
"""
from __future__ import annotations

DEFAULT_MODEL = "qwen3.6-35b-a3b/latest"
DEFAULT_PLANNER = "qwen3-235b-a22b-fp8/latest"
DEFAULT_CONTEXT = 131_072

# (алиас, slug, окно контекста в токенах, вызывает инструменты агента, назначение).
# Окна — по документации Yandex AI Studio «Available generative models».
# Вызов инструментов — проверка 2026-09-14 в Goose 1.50: задача «создать файл
# через инструмент» в `ai4science run`; модели Alice в 6 из 6 запусков писали
# вызов текстом и сообщали о выполнении, файл не создавался.
CATALOG: list[tuple[str, str, int, bool, str]] = [
    ("qwen", "qwen3.6-35b-a3b/latest", 262_144, True, "модель по умолчанию"),
    ("qwen235", "qwen3-235b-a22b-fp8/latest", 262_144, True, "модель для /plan; точнее и дороже"),
    ("deepseek", "deepseek-v4-flash/latest", 1_048_576, True, "альтернатива для сравнения"),
    ("gptoss", "gpt-oss-120b/latest", 131_072, True, "короткие цепочки инструментов"),
    ("junior", "gpt-oss-20b/latest", 131_072, True, "экономия суточного лимита"),
    ("alice", "aliceai-llm/latest", 131_072, False, "Alice AI LLM; только диалог"),
    ("alice-flash", "aliceai-llm-flash/latest", 65_536, False, "Alice AI LLM Flash; только диалог"),
]

MODEL_ALIASES: dict[str, str] = {alias: slug for alias, slug, *_ in CATALOG}
MODEL_ALIASES.update({
    "qwen35": "qwen3.6-35b-a3b/latest",
    "gpt-oss": "gpt-oss-120b/latest",
    "aliceai": "aliceai-llm/latest",
    "aliceflash": "aliceai-llm-flash/latest",
})
MODEL_CONTEXT: dict[str, int] = {slug: ctx for _, slug, ctx, *_ in CATALOG}
NO_TOOLS: frozenset[str] = frozenset(slug for _, slug, _, tools, _ in CATALOG if not tools)
TOOL_MODELS = ", ".join(alias for alias, _, _, tools, _ in CATALOG if tools)

# После `/model` Goose не пересчитывает окно контекста, поэтому точка сжатия
# истории одна для всех моделей каталога: история вместе с ответом модели
# помещается в самое короткое окно.
MAX_OUTPUT_TOKENS = 16_000
COMPACT_AT_TOKENS = min(100_000, min(MODEL_CONTEXT.values()) - MAX_OUTPUT_TOKENS - 4_000)

URI_SCHEMES = ("gpt://", "emb://", "art://", "ds://")


def resolve_model(raw: str) -> str:
    """Алиас или slug → slug вида `<модель>/<версия>`; пусто → модель по умолчанию."""
    raw = (raw or "").strip()
    if not raw:
        return DEFAULT_MODEL
    if raw in MODEL_ALIASES:
        return MODEL_ALIASES[raw]
    return raw if "/" in raw else f"{raw}/latest"


def context_for(model_slug: str) -> int:
    return MODEL_CONTEXT.get(model_slug, DEFAULT_CONTEXT)


def calls_tools(model_slug: str) -> bool:
    """False для моделей, которые в сессии агента не вызывают инструменты."""
    return model_slug not in NO_TOOLS


def model_uri(folder: str, raw: str) -> str:
    """Полный URI модели `gpt://<folder>/<slug>`; готовый URI возвращается без изменений."""
    raw = (raw or "").strip()
    if raw.startswith(URI_SCHEMES):
        return raw
    return f"gpt://{folder}/{resolve_model(raw)}"


def format_context(tokens: int) -> str:
    """262144 → '256k', 1048576 → '1M' (как в документации Yandex AI Studio)."""
    if tokens >= 1_048_576:
        return f"{tokens // 1_048_576}M"
    return f"{tokens // 1024}k"
