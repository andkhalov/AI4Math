# AI4Math — архитектура

Короткий инженерный обзор того, как работает AI4Math под капотом, чтобы внести правки или диагностировать проблемы, не читая весь код.

---

## Уровни компоновки

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Пользователь                                                 │
│    ai4math [session|run] [-m qwen|deepseek|gptoss] [args]       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ bash
┌──────────────────────────────▼──────────────────────────────────┐
│ 2. bin/ai4math                  (обёртка)                       │
│    - sources .env                                               │
│    - выставляет per-model GOOSE_CONTEXT_LIMIT и т.д.            │
│    - парсит recipes/ai4math.yaml → две части:                   │
│      (a) instructions → tempfile → GOOSE_SYSTEM_PROMPT_FILE_PATH│
│      (b) extensions → --with-builtin / --with-extension flags   │
│    - exec goose session|run --no-profile                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │ exec
┌──────────────────────────────▼──────────────────────────────────┐
│ 3. .tools/goose                 (агентский loop)                │
│    - OpenAI-compatible client → Yandex AI Studio                │
│    - регистрирует tool_schemas для developer + ai4math          │
│    - agent loop: message → tool_calls → tool_exec → message ... │
│    - auto-compaction при GOOSE_AUTO_COMPACT_THRESHOLD           │
└────────────┬──────────────────┬─────────────────────────────────┘
             │ HTTPS            │ stdio JSON-RPC (MCP)
             │                  │
┌────────────▼──────────┐  ┌────▼──────────────────────────────────┐
│ 4a. Yandex AI Studio  │  │ 4b. src/ai4math_mcp.py                │
│     /v1/chat/compl    │  │     FastMCP("ai4math")                │
│     qwen / deepseek / │  │     13 tools:                         │
│     gpt-oss           │  │       lean_check, lean_health         │
└───────────────────────┘  │       lean_search_loogle/leansearch/  │
                           │         moogle/scilib + _engines      │
                           │       web_search, web_fetch           │
                           │       pdf_info/read/search            │
                           └────┬──────────────────────────────────┘
                                │ HTTP (для большинства тулов)
     ┌──────────┬───────────────┼─────────────┬──────────────┐
     │          │               │             │              │
     ▼          ▼               ▼             ▼              ▼
┌──────────┐ ┌──────┐ ┌─────────────────┐ ┌──────────┐ ┌─────────┐
│lean-     │ │Loogle│ │LeanSearch/Moogle│ │SciLib    │ │DDG/Brave│
│checker   │ │      │ │                 │ │GraphRAG  │ │         │
│(local    │ │public│ │public HTTPS     │ │private   │ │public   │
│Docker)   │ │HTTPS │ │                 │ │HTTPS     │ │HTTPS    │
└──────────┘ └──────┘ └─────────────────┘ └──────────┘ └─────────┘
```

---

## Компоненты

### 1. bin/ai4math — обёртка

- Читает `.env`, выставляет `GOOSE_PROVIDER=openai`, `OPENAI_HOST`, `OPENAI_BASE_PATH`, `OPENAI_API_KEY`, `GOOSE_MODEL=gpt://<folder>/<slug>`
- Per-model контекст: qwen 256k, deepseek/gptoss 128k (эмпирически определено, см. `EXPERIMENT_REPORT.md`)
- `GOOSE_AUTO_COMPACT_THRESHOLD=0.8` — auto-summarization при 80% заполненности окна
- Парсит recipe YAML на Python (через `.venv/bin/python -c`):
  - **instructions** → tempfile → `GOOSE_SYSTEM_PROMPT_FILE_PATH` (env var, которую Goose читает на старте)
  - **extensions** → list of `--with-builtin <name>` + `--with-extension "<env> <cmd> <args>"` флагов
- `--no-profile` — игнорирует `~/.config/goose/` (инструменты, установленные юзером раньше)
- Поддерживает `session` (интерактив), `run` (одна задача), `doctor` (sanity-check)

### 2. recipes/ai4math.yaml — Goose recipe

Стандартный Goose recipe format:

```yaml
version: "1.0.0"
title: "AI4Math"
description: ...
extensions:
  - type: builtin
    name: developer          # bash + text_editor + todo
  - type: stdio
    name: ai4math            # наш MCP
    cmd: bin/ai4math-mcp
    timeout: 180
instructions: |
  # Идентичность
  Ты — AI4Math, CLI-агент для курса ...
```

`instructions` содержит:

- Идентичность (AI4Math, не goose, не Claude)
- Философию курса (триада инференс → контекст → верификация)
- Стиль коммуникации (русский, коротко, tool-first, без эмодзи)
- Каталог инструментов с описаниями
- Правила выбора поискового движка (ask-first когда пользователь не указал)
- Правила работы с Lean (ядро тактик, ловушки ℕ, `sorry`)
- Правила работы с локальным контекстом проекта (CLAUDE.md, diary.md, memory/, ontology/)
- Список «что не делать»
- Правила безопасности

Формат `|` (block literal) — читаемый, правится вручную.

### 3. src/ai4math_mcp.py — единый MCP сервер

- `FastMCP("ai4math")` с 13 инструментами
- Stdio транспорт, запускается Goose'ом через `bin/ai4math-mcp`
- Каждый инструмент — декорированная функция `@mcp.tool()` с docstring (становится описанием для модели)

**Группы инструментов**:

1. **Lean верификация** (2): `lean_check`, `lean_health` — HTTP к lean-checker
2. **Mathlib search** (5): `lean_search_engines`, `lean_search_loogle/leansearch/moogle/scilib` — HTTP к публичным endpoint + к нашему SciLib GraphRAG
3. **Web** (2): `web_search` (Brave или DDG), `web_fetch` (HTML → plain text)
4. **PDF** (3): `pdf_info`, `pdf_read`, `pdf_search` — через `pypdf`

**Env-toggles**:

- `AI4MATH_LEAN_DISABLED=1` — `lean_check` возвращает "disabled"
- `AI4MATH_WEB_DISABLED=1` — `web_*` возвращает "disabled"

### 4. Внешние зависимости

- **Yandex AI Studio** (`https://llm.api.cloud.yandex.net/v1/chat/completions`) — LLM inference через OpenAI-совместимый протокол. Модель id: `gpt://<folder>/<slug>/latest`. Folder id встроен в slug — дополнительный `OpenAI-Project` header не нужен.
- **lean-checker** (Docker, `localhost:8888`) — FastAPI с `/health` и `/check`, внутри Lean 4.24 + Mathlib с кешированным `lake env`. Клонируется из [github.com/andkhalov/lean-checker](https://github.com/andkhalov/lean-checker) в `vendor/lean-checker/`.
- **Loogle** — `https://loogle.lean-lang.org/json?q=...`
- **LeanSearch** — `https://leansearch.net/search` POST
- **Moogle** — `https://www.moogle.ai/api/search` POST
- **SciLib GraphRAG** — `https://scilib.tailb97193.ts.net/grag/search` POST (разработан в рамках курса)

---

## Жизненный цикл сессии

### Запуск `ai4math`

1. Bash wrapper sourcing `.env`.
2. Per-model env vars.
3. Python-парсинг recipe → tempfile с `instructions` + list of `--with-*` флагов.
4. Print ASCII-баннер (если `AI4MATH_QUIET≠1`).
5. `exec .tools/goose session --no-profile --with-builtin developer --with-extension "<cmd>"`.
6. Goose:
   - читает `GOOSE_SYSTEM_PROMPT_FILE_PATH` → grabs instructions
   - запускает stdio-подпроцесс `bin/ai4math-mcp` (python + FastMCP), ждёт `initialize` ответа
   - регистрирует все 13 инструментов + 3 `developer` инструмента в schema для LLM
   - открывает интерактивный REPL

### Каждый turn

1. User input → Goose: build `messages` (system + history + user).
2. Goose → OpenAI-compat API: `POST /v1/chat/completions` с `tools=[...]`, `model="gpt://..."`.
3. Yandex возвращает `message` с `content` или `tool_calls`.
4. Если `tool_calls`:
   - Goose матчит name → extension
   - Для стандартных инструментов (`shell`, `text_editor`) — builtin handler
   - Для наших — посылает JSON-RPC `tools/call` в stdio процесс MCP
   - MCP возвращает результат как строку
   - Goose добавляет `{role: tool, content: ...}` в history и делает следующий вызов LLM
5. Когда LLM возвращает `content` без tool_calls — Goose печатает финальный ответ и ждёт следующий user input.

### Auto-compaction

Когда `usage.total_tokens` в последнем ответе превышает `GOOSE_CONTEXT_LIMIT * GOOSE_AUTO_COMPACT_THRESHOLD` (для qwen: 256000 × 0.8 = 204800):

1. Goose сам вызывает LLM с промптом суммаризации исторических сообщений
2. Заменяет список history на {system + compaction_summary + N последних turns}
3. Продолжает сессию с меньшим окном
4. Пользователь видит сообщение `Exceeded auto-compact threshold of 80%. Performing auto-compaction...`, а затем `Compaction complete`

Проверено на `GOOSE_CONTEXT_LIMIT=3000 GOOSE_AUTO_COMPACT_THRESHOLD=0.5` в эксперименте — компакция прозрачная, контекст (например ссылки на ранние теоремы) сохраняется через суммаризацию.

---

## Ключевые ограничения

### gpt-oss-120b несовместим с Goose namespacing

gpt-oss strippит `developer__` префикс с tool names, вызывает `text_editor` напрямую, MCP возвращает `-32002: Tool not found`, сессия закрывается. qwen и deepseek используют полные имена корректно. Подробности в `report/EXPERIMENT_REPORT.md`.

Рабочий обход: использовать gpt-oss только для one-shot ответов без tool-цепей. Полное исправление требует либо форка Goose, либо написания name-rewriting middleware.

### Смена модели mid-session

Goose не поддерживает. `/exit` + `ai4math -m <other>` — единственный путь.

### Lean-checker первый прогрев

После `docker compose up -d` первый `/health` запрос может занять до 90 секунд — Lean компилирует health.lean файл, прогревая `lake env`. Последующие `/check` запросы — быстрые (1-5 секунд на небольшой фрагмент).

### Auto-compaction vs Yandex rate limits

При частых compaction'ах Goose делает дополнительные LLM-вызовы для суммаризации. На qwen это ~2-5 секунд на compaction, некритично. На deepseek может быть до 15 секунд из-за thinking tokens. При активной сессии в час набегает порядка 5-10 compaction'ов, не проблема для квоты.

---

## Сборка и версии

Pinned версии (на момент Phase 3 benchmark, 2026-04-14):

- **Goose**: 1.30.0 (скачивается из github.com/aaif-goose/goose releases)
- **Lean**: 4.24.0 (зафиксировано в `vendor/lean-checker/docker-compose.yml`)
- **Mathlib**: v4.24.0 (там же)
- **Yandex модели**:
  - `qwen3-235b-a22b-fp8/latest`
  - `deepseek-v32/latest`
  - `gpt-oss-120b/latest`
- **Python**: 3.10+ (минимум)
- **MCP SDK**: `mcp>=0.9` (FastMCP API)

---

## Отладка

```bash
ai4math doctor                    # проверка всех компонент окружения
RUST_LOG=debug ai4math run "..."  # подробный лог Goose
docker logs lean-checker-lean-server-1  # логи lean-checker
curl localhost:8888/health        # проверка lean-checker напрямую
```

Рабочий каталог Goose-session: `/tmp/goose/<session-id>/`. Сессии хранятся в `~/.config/goose/sessions/` — можно посмотреть через `goose session list`.
