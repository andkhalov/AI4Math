# AI4Math — архитектура

Инженерный обзор того, как работает AI4Math изнутри — чтобы вносить правки или диагностировать проблемы без чтения всего кода.

---

## Уровни компоновки

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Пользователь                                                 │
│    ai4math [session|run] [-m qwen|deepseek|gptoss] [args]       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ bash / cmd
┌──────────────────────────────▼──────────────────────────────────┐
│ 2. bin/ai4math (shim) → bin/ai4math.py (cross-platform core)    │
│    - загружает .env                                             │
│    - выставляет per-model GOOSE_CONTEXT_LIMIT и прочие тюнинги  │
│    - парсит recipes/ai4math.yaml → две части:                   │
│      (a) instructions → tempfile → GOOSE_SYSTEM_PROMPT_FILE_PATH│
│      (b) extensions → --with-builtin / --with-extension flags   │
│    - exec goose session|run --no-profile                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │ exec (POSIX) / subprocess (Windows)
┌──────────────────────────────▼──────────────────────────────────┐
│ 3. .tools/goose                 (агентский loop)                │
│    - OpenAI-compatible client → Yandex AI Studio                │
│    - tool_schemas для developer builtin + ai4math stdio         │
│    - agent loop: message → tool_calls → tool_exec → message ... │
│    - auto-compaction при GOOSE_AUTO_COMPACT_THRESHOLD (0.8)     │
└────────────┬──────────────────┬─────────────────────────────────┘
             │ HTTPS            │ stdio JSON-RPC (MCP)
             │                  │
┌────────────▼──────────┐  ┌────▼──────────────────────────────────┐
│ 4a. Yandex AI Studio  │  │ 4b. src/ai4math_mcp.py                │
│     /v1/chat/compl    │  │     FastMCP("ai4math") — 13 tools     │
│     qwen / deepseek / │  │       lean_check, lean_health         │
│     gpt-oss           │  │       lean_search_scilib  ⭐ primary  │
└───────────────────────┘  │       lean_search_loogle/leansearch/  │
                           │         moogle + _engines             │
                           │       web_search, web_fetch           │
                           │       pdf_info/read/search            │
                           └────┬──────────────────────────────────┘
                                │ HTTPS (для большинства инструментов)
  ┌────────────┬────────┬───────┼──────────┬───────────┬───────────┐
  │            │        │       │          │           │           │
  ▼            ▼        ▼       ▼          ▼           ▼           ▼
┌────────┐ ┌──────┐ ┌─────────┐ ┌─────────────┐ ┌──────┐ ┌───────────┐
│SciLib- │ │Loogle│ │LeanSrch │ │Moogle       │ │DDG   │ │pypdf      │
│GRC21   │ │      │ │         │ │             │ │Brave │ │(local)    │
│/check  │ │      │ │         │ │             │ │      │ │           │
│/search │ │      │ │         │ │best-effort  │ │      │ │           │
└────────┘ └──────┘ └─────────┘ └─────────────┘ └──────┘ └───────────┘
   primary                                                 
   Lean +                                                  
   GraphRAG                                                
```

**Lean backend** по умолчанию — `https://scilib.tailb97193.ts.net/grag` (SciLib-GRC21). Опциональный локальный fallback — `http://localhost:8888` (андkhalov/lean-checker, старая схема). MCP автоматически определяет нужную схему по URL.

---

## Компоненты

### 1. bin/ai4math (shim) + bin/ai4math.py (core)

Кросс-платформенный Python entrypoint. Shim-скрипт `bin/ai4math` для Linux/macOS и `bin/ai4math.bat` для Windows делегируют к `bin/ai4math.py`, который:

- Читает `.env` (stdlib-only, без python-dotenv, чтобы работать до установки зависимостей)
- Выставляет `GOOSE_PROVIDER=openai`, `OPENAI_HOST`, `OPENAI_BASE_PATH`, `OPENAI_API_KEY`, `GOOSE_MODEL=gpt://<folder>/<slug>`
- Per-model контекст: qwen 256k, deepseek/gptoss 128k (см. [EXPERIMENT_REPORT.md](../report/EXPERIMENT_REPORT.md) — «Context window probe»)
- `GOOSE_AUTO_COMPACT_THRESHOLD=0.8` — auto-summarization при 80% заполнении окна
- Парсит recipe YAML:
  - `instructions` → tempfile → `GOOSE_SYSTEM_PROMPT_FILE_PATH` (env var, которую читает Goose)
  - `extensions` → list of `--with-builtin <name>` + `--with-extension "<env> <cmd> <args>"` флагов
- `--no-profile` — игнорирует `~/.config/goose/` (чужие extensions)
- Поддерживает `session`, `run`, `doctor`, `--help`, `--model`, `--no-lean`
- На POSIX делает `os.execvp` для process replace, на Windows — `subprocess.run`

### 2. recipes/ai4math.yaml — Goose recipe

Формат Goose recipe:

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

- Идентичность (AI4Math, не Claude, не goose)
- Философия курса (триада инференс → контекст → верификация)
- Стиль коммуникации (русский, коротко, tool-first, без эмодзи)
- Каталог инструментов с описаниями
- Правила выбора поискового движка (scilib primary, ask-first для остальных)
- Правила работы с Lean (ядро тактик, ловушки ℕ, sanity-filter ограничения)
- Правила работы с локальным контекстом проекта (AGENTS.md / CLAUDE.md / .cursorrules приоритет)
- Список «что не делать»
- Правила безопасности

### 3. src/ai4math_mcp.py — единый MCP сервер

`FastMCP("ai4math")` с 15 инструментами, stdio транспорт. Запускается Goose'ом через `bin/ai4math-mcp`.

**Skills — modular on-demand loading** (2):

- `list_skills()` — enumerate topic-specific guides available in `$AI4MATH_SKILLS_DIR` (default `<repo>/skills/`)
- `load_skill(name)` — read and return full content of `skills/<name>.md`

Skills are short (~100-200 lines) markdown files covering one domain each: `python.md`, `latex.md`, `markdown.md`, `lean.md`, `literature.md`, `debug-loop.md`. Recipe instructions match task types to skill names and require the agent to call `load_skill(...)` before starting work in that domain. This keeps the core system prompt ~250 lines instead of 600+ and enables hot-swapping best-practices without editing the recipe.

Project-specific skills can be added as additional `.md` files in the skills directory — no code changes needed. Path is overridable via `AI4MATH_SKILLS_DIR` env var.

**Lean верификация** (2):

- `lean_check(code, timeout=60)` — HTTP запрос к Lean checker. Автоматически определяет схему (SciLib vs lean-checker) по URL:
  - URL содержит `/grag` → SciLib /check схема: `{lean_code, timeout}` → `{success, error_class, error_message, sanity_ok, ...}`
  - иначе → legacy схема: `{code, import_line}` → `{ok, messages}`
- `lean_health()` — probe `/health`

**Mathlib search** (5):

- `lean_search_scilib(lean_code, n)` — **primary**: POST `{SCILIB}/search` с GraphRAG pipeline
- `lean_search_loogle(query)` — GET `loogle.lean-lang.org/json?q=...`
- `lean_search_leansearch(query, n)` — POST `leansearch.net/search` с `{query: [...]}`
- `lean_search_moogle(query)` — POST `moogle.ai/api/search`
- `lean_search_engines()` — health-check всех четырёх с сравнением

**Web** (2):

- `web_search(query, n)` — Brave Search API если задан `BRAVE_API_KEY`, иначе DuckDuckGo HTML scrape
- `web_fetch(url, max_chars)` — HTTP GET, HTML → plain text, truncate

**PDF** (4) — через `pypdf` + `requests` streaming:

- `pdf_download(url, dest_path)` — binary-safe загрузка PDF с проверкой `%PDF-` magic bytes (для HTML-редиректов удаляет файл)
- `pdf_info(path)` — metadata, pages, size
- `pdf_read(path, pages, max_chars)` — extract text по 1-indexed спеку `"1-5,10"`
- `pdf_search(path, query, context)` — подстрочный поиск

**Env-toggles**:

- `AI4MATH_LEAN_DISABLED=1` — `lean_check` / `lean_health` возвращают "disabled"
- `AI4MATH_WEB_DISABLED=1` — `web_*` и `pdf_download` возвращают "disabled"
- `AI4MATH_LEAN_SCHEMA=scilib|lean-checker` — явный override автодетекта
- `AI4MATH_SKILLS_DIR=/path/to/skills/` — переопределить путь skill-директории

### 4. Внешние зависимости

- **Yandex AI Studio** (`https://llm.api.cloud.yandex.net/v1/chat/completions`) — LLM инференс через OpenAI-compatible протокол. Model id: `gpt://<folder>/<slug>/latest`. Folder id встроен в slug, отдельный `OpenAI-Project` header не нужен.
- **SciLib-GRC21** (`https://scilib.tailb97193.ts.net/grag`, [API docs](https://github.com/andkhalov/SciLib-GRC21/blob/main/docs/api.md)) — основной backend для Lean верификации (`/check`) и premise retrieval (`/search`). Lean 4.28-rc1 + Mathlib 4.26 + GraphDB + PostgreSQL + Qdrant.
- **andkhalov/lean-checker** (опционально, `localhost:8888` через Docker) — упрощённый локальный fallback с Lean 4.24 + Mathlib 4.24. Клонируется скриптом `scripts/install_lean.sh` при `--with-lean-local`.
- **Loogle** — `https://loogle.lean-lang.org/json?q=...`
- **LeanSearch** — `https://leansearch.net/search` POST
- **Moogle** — `https://www.moogle.ai/api/search` POST

---

## Жизненный цикл сессии

### Запуск `ai4math`

1. Shim (bash / bat) вычисляет пути, вызывает `python bin/ai4math.py`.
2. Python загружает `.env`, выставляет GOOSE env vars по модели.
3. Парсит recipe → tempfile с `instructions` + list of `--with-*` флагов.
4. Печатает ASCII-баннер (если `AI4MATH_QUIET != 1`).
5. `exec .tools/goose session --no-profile --with-builtin developer --with-extension "<cmd>"`.
6. Goose:
   - читает `GOOSE_SYSTEM_PROMPT_FILE_PATH` → загружает instructions
   - запускает stdio подпроцесс `bin/ai4math-mcp` (Python + FastMCP), ждёт `initialize` ответ
   - регистрирует 13 инструментов MCP + 3 builtin `developer` инструмента в tool schema
   - открывает интерактивный REPL

### Каждый turn

1. User input → Goose формирует `messages` (system + history + user).
2. Goose → OpenAI-compat API: `POST /v1/chat/completions` с `tools=[...]`, `model="gpt://..."`.
3. Yandex возвращает `message` с `content` или `tool_calls`.
4. Если `tool_calls`:
   - Goose матчит имя → extension
   - Для стандартных инструментов (`shell`, `text_editor`) — builtin handler
   - Для наших — JSON-RPC `tools/call` в stdio процесс MCP
   - MCP возвращает результат как строку
   - Goose добавляет `{role: tool, content: ...}` в history и делает следующий LLM-вызов
5. Когда LLM возвращает `content` без tool_calls — Goose печатает финальный ответ и ждёт следующий user input.

### Auto-compaction

Когда `usage.total_tokens` в последнем ответе превышает `GOOSE_CONTEXT_LIMIT * GOOSE_AUTO_COMPACT_THRESHOLD`:

1. Goose сам вызывает LLM с промптом суммаризации исторических сообщений
2. Заменяет history на {system + compaction_summary + N последних turns}
3. Продолжает сессию с меньшим окном
4. Пользователь видит `Exceeded auto-compact threshold of 80%. Performing auto-compaction... Compaction complete`

---

## Ключевые ограничения

### gpt-oss-120b несовместима с Goose namespacing

gpt-oss strippит префикс `developer__` с tool names, вызывает `text_editor` напрямую, MCP возвращает `-32002: Tool not found`, сессия закрывается. qwen и deepseek используют полные имена корректно. Рабочий обход: использовать gpt-oss только для one-shot ответов без tool-цепей. Полное исправление требует форка Goose или name-rewriting middleware.

### Смена модели mid-session

Goose не поддерживает. `/exit` + `ai4math -m <other>` — единственный путь.

### SciLib sanity filter

Endpoint отвергает бесполезные подачи: `sorry`-only proofs, bare imports, comment-only, natural language. Агент об этом знает и не отправляет такие фрагменты.

### Lean checker первый прогрев

После старта SciLib endpoint первый запрос может занять до 90 секунд (прогрев `lake env` + Mathlib). Последующие запросы — 20-50 ms. Default timeout в `lean_check` — 60 секунд, покрывает первый warm-up.

### Privacy

По умолчанию Lean-код отправляется на публичный SciLib-GRC21 endpoint (в рамках курсовой инфраструктуры). Для чувствительных доказательств — `./setup.sh --with-lean-local` и `LEAN_CHECKER_URL=http://localhost:8888` в `.env`.

---

## Версии

Pinned versions (актуально на момент последнего бенчмарка):

- **Goose**: 1.30.0 (GitHub releases `aaif-goose/goose`)
- **Lean (SciLib default)**: 4.28.0-rc1 + Mathlib 4.26.0
- **Lean (local fallback)**: 4.24.0 + Mathlib 4.24.0
- **Yandex models**:
  - `qwen3-235b-a22b-fp8/latest`
  - `deepseek-v32/latest`
  - `gpt-oss-120b/latest`
- **Python**: 3.10+ (минимум)
- **MCP SDK**: `mcp>=0.9` (FastMCP API)

---

## Отладка

```bash
ai4math doctor                          # проверка окружения
RUST_LOG=debug ai4math run "..."        # verbose Goose лог
curl https://scilib.tailb97193.ts.net/grag/health   # remote Lean endpoint
curl http://localhost:8888/health       # local Lean endpoint (если установлен)
docker logs lean-checker-lean-server-1  # логи local Lean контейнера
goose session list                      # список прошлых сессий
```

Рабочие каталоги сессий — `~/.config/goose/sessions/` (POSIX) или `%APPDATA%\goose\sessions\` (Windows).
