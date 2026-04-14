# AI4Math — отчёт о эксперименте и методика

Этот документ фиксирует **что было проверено**, **какие цифры получены** и **какие решения приняты** при проектировании AI4Math. Без хронологии, без обсуждения отклонённых альтернатив (они в `scripts/_legacy/` и git history). Цель — чтобы любой инженер/исследователь, глядя только на этот файл, мог повторить измерения и понять, почему продукт устроен именно так.

**Автор**: А. П. Халов — ФИЦ ИУ РАН | ФИЦ ВЦ РАН | МФТИ | ШАД Яндекса.
**Версия документа**: пост-релиз Stage 2, актуально на момент первого публичного push в `github.com/andkhalov/AI4Math`.

---

## Цель и ограничения

**Цель.** Собрать open-source CLI-агента, эквивалентного Claude Code по возможностям кодирования, с дополнительными функциями верификации Lean 4 и поиска по Mathlib, работающего на Yandex AI Studio open-weight моделях (Qwen3, DeepSeek-V3.2, gpt-oss-120b), для курса ШАД «AI4Math Intensive».

**Жёсткие ограничения** (из постановки):

- Не писать собственный агентский фреймворк — использовать готовый.
- Не тянуть LangChain, CrewAI, AutoGen.
- Не использовать LiteLLM proxy server (библиотечный импорт допустим, прокси — нет).
- Docker **не требуется** для базовой работы агента (только опционально для локальной Lean верификации).
- Ubuntu 22+ / macOS 13+ / Windows 10+ (WSL2 или нативно).
- Python 3.10+.
- Минимизировать объём собственного кода.

---

## Стек (финальный)

| Слой | Компонент | Версия |
|---|---|---|
| Агентский loop | [Goose](https://github.com/aaif-goose/goose) | 1.30.0 |
| LLM backbone | Yandex AI Studio OpenAI-compatible | — |
| Модель по умолчанию | Qwen3-235B-A22B-FP8 | `qwen3-235b-a22b-fp8/latest` |
| Альтернативная модель | DeepSeek-V3.2 | `deepseek-v32/latest` |
| Lean верификация | [SciLib-GRC21](https://github.com/andkhalov/SciLib-GRC21) `/check` | Lean 4.28-rc1 / Mathlib 4.26 |
| Lean локальный fallback | [andkhalov/lean-checker](https://github.com/andkhalov/lean-checker) | Lean 4.24 / Mathlib 4.24 |
| Mathlib search primary | SciLib-GRC21 `/search` (GraphRAG) | GraphDB + PostgreSQL + Qdrant |
| Mathlib search auxiliary | Loogle, LeanSearch, Moogle | публичные endpoint'ы |
| Web search | DuckDuckGo (default) или Brave Search API | — |
| PDF | pypdf | ≥4.0 |
| MCP SDK | [`mcp`](https://modelcontextprotocol.io/) (FastMCP) | ≥0.9 |

**Собственный код**: ~945 строк (Python + YAML + bash), в том числе ~540 строк единого MCP-сервера с 13 инструментами и ~380 строк кросс-платформенной обёртки. Всё остальное — чистые зависимости или конфигурация.

---

## Фаза 1 — Tool calls на Yandex AI Studio

**Вопрос.** Возвращают ли open-weight модели Yandex валидный `tool_calls` через OpenAI-совместимый endpoint?

**Методика.** Один тривиальный тул `get_weather(city)`, запрос «What's the weather in Moscow? Use the get_weather tool», `temperature=0`, `max_tokens=1000`, `tool_choice=auto`. Три модели.

**Результат.** 3/3 PASS. Все три модели вернули валидный `tool_calls[0].function.name == "get_weather"` с JSON-аргументами `{"city": "Moscow"}`.

**Побочные находки, повлиявшие на дизайн**:

1. **`OpenAI-Project` header не нужен** — folder id внутри model slug (`gpt://<folder>/<slug>/latest`) самодостаточен.
2. **DeepSeek и gpt-oss — thinking-модели** с дополнительным полем `reasoning_content` в ответе. При `max_tokens < 1000` этот reasoning съедает лимит и `content` приходит пустым. В рабочих сессиях поставлен `GOOSE_MAX_TOKENS=16000`.
3. **Canonical base URL** — `https://llm.api.cloud.yandex.net/v1`.
4. **LiteLLM wrapper не требуется** — `openai` SDK напрямую работает с Yandex без любых адаптеров.

---

## Фаза 2 — Выбор agentic framework

**Требования**: MCP-расширения, нет Docker для самого агента, конфигурация только env vars, готовые code tools (bash/edit/etc).

**Выбран Goose** по совокупности характеристик:

- Нативная поддержка MCP stdio/HTTP extensions → `lean_check` реализуется как MCP-инструмент, фреймворк-агностичный
- Распространяется как статичный Rust-бинарь (Linux/macOS/Windows), без Docker
- Конфигурируется только env vars (`GOOSE_PROVIDER`, `OPENAI_HOST`, `GOOSE_MODEL`, …) — без config-файла
- Встроенные builtin extensions: `developer` (bash + text_editor + todo)
- Auto-compaction контекста через summarization при превышении `GOOSE_AUTO_COMPACT_THRESHOLD`
- Быстрый startup (~0.3 с на сессию)

**Smoke validation** (Qwen3 + Goose, одна модель × три Claude-Code-уровня задачи, одна попытка на каждую):

| Задача | Описание | Результат |
|---|---|---|
| A | Создать `hello.py` с первыми 10 числами Фибоначчи, запустить | PASS с автовосстановлением от `python: command not found` на `python3` |
| B | Прочитать `hello.py`, добавить argparse для N, запустить с N=20 | PASS с одной итерацией |
| C | Написать `analyze.py`: CSV → mean/median/std по категориям → bar chart PNG. Починить ошибки. | PASS после 4 шагов автономного error recovery (`pip install` → PEP 668 → `apt install` → permission denied → `sudo apt` → no terminal → `python3 -m venv` → успех) |

Всё через базовый `developer` builtin + нашу тонкую обёртку. Никакого custom кода для самого агентского loop.

**Конфигурация Goose без config-файла** (используется AI4Math обёрткой):

```
GOOSE_PROVIDER=openai
OPENAI_HOST=https://llm.api.cloud.yandex.net
OPENAI_BASE_PATH=/v1/chat/completions
OPENAI_API_KEY=<key>
GOOSE_MODEL=gpt://<folder>/<slug>
GOOSE_CONTEXT_LIMIT=<per-model>
GOOSE_AUTO_COMPACT_THRESHOLD=0.8
GOOSE_MAX_TOKENS=16000
GOOSE_SYSTEM_PROMPT_FILE_PATH=/tmp/<recipe-instructions>.md
```

---

## Фаза 3 — Бенчмарк моделей

**Задачи**. Те же A/B/C, что в Фазе 2.

**Модели**: qwen3-235b-a22b-fp8, deepseek-v32. gpt-oss-120b исключена (см. раздел «Несовместимость gpt-oss» ниже).

**Trials**: 10 на каждую пару (модель, задача) = **60 runs**.

**Оптимизация Task C**: предварительно создан shared venv с `pandas`+`matplotlib`, чтобы не измерять время `pip install` (шум сети + PEP 668 recovery). Это фокусирует метрику на агентских возможностях, а не на удаче с pip.

### Результаты

| Модель | Task | Success | 95% CI | Iters (mean) | Latency (mean) |
|---|---|---|---|---:|---:|
| **qwen** | A (fibonacci create) | **10/10** | [1.00, 1.00] | 2.0 | **10.4 s** |
| **qwen** | B (argparse edit) | **10/10** | [1.00, 1.00] | 4.0 | **15.0 s** |
| **qwen** | C (CSV + chart) | 9/10 | [0.70, 1.00] | 8.1 | 24.9 s |
| **deepseek** | A | 10/10 | [1.00, 1.00] | 2.1 | 19.9 s |
| **deepseek** | B | **7/10** | [0.40, 1.00] | 4.8 | 28.4 s |
| **deepseek** | C | 10/10 | [1.00, 1.00] | 6.0 | 40.8 s |

**Aggregate**:

- **qwen**: 29/30 = **96.7 %** success, mean latency across tasks ~16.8 s
- **deepseek**: 27/30 = **90.0 %** success, mean latency across tasks ~29.7 s

### Pairwise сравнение (Bonferroni над 3 тестами)

| Сравнение | $p_{McN}$ | Cohen's $d$ (iters) |
|---|---|---|
| deepseek vs qwen, Task A | 1.000 | +0.45 |
| deepseek vs qwen, Task B | 0.750 | +0.53 |
| deepseek vs qwen, Task C | 1.000 | −0.59 |

Статистически незначимо после Bonferroni при $n=10$ на клетку (малая мощность), но практические наблюдения:

- **qwen примерно в 2 раза быстрее** на всех задачах.
- **qwen надёжнее на code editing** (Task B): 10/10 vs 7/10. Три сбоя deepseek — случаи когда edit даёт сломанный argparse (`unrecognized arguments: 20` в python stderr). Thinking mode делает менее точные diff'ы.
- **deepseek чуть стабильнее на multi-step** (Task C): 10/10 vs 9/10. qwen использует больше итераций в среднем (8.1 vs 6.0) — компенсирует стабильность ценой дополнительных шагов.
- **Task A (one-shot create)** — обе идеальные.

### Решение

**Default model = qwen.** Рекомендация автоматизирована в `cli/wizard.py`. DeepSeek — опция через `ai4math -m deepseek` для задач, где точность thinking-mode может помочь (сложные proofs, длинные цепи рассуждений).

---

## Фаза 4 — Lean верификация через SciLib

**Задачи**: четыре сценария возрастающей сложности, по 3 trial каждый, на qwen.

| Сценарий | Описание | Результат | Avg latency | Avg `lean_check` calls |
|---|---|---|---|---|
| A | `example : 1 + 1 = 2 := by norm_num` | 3/3 | 10 s | 1 |
| B | `∀ n : ℕ, n + 0 = n` с error recovery при неправильной тактике | 3/3 | 11 s | 1.3 |
| C | Прочитать `lit/nat_add_comm.md` → сформулировать и доказать коммутативность сложения | 3/3 | 18 s | 2 |
| D | Прочитать `lit/problem.md` (сумма первых n натуральных) → формализовать → верифицировать → записать report/lean_results.md | 3/3 | 84 s | 10 |

**Итог**: 12/12 PASS.

D — самый реалистичный пример: агент сам ищет `Finset.sum_range_id`, формализует statement, многократно вызывает `lean_check` до получения `OK`, записывает отчёт. В среднем 15 итераций и 10 вызовов проверки на прохождение.

### Lean backend архитектура

Верификация работает через SciLib-GRC21 endpoint (`POST {URL}/check`):

- **Request**: `{"lean_code": "...", "timeout": 60}`
- **Response**: `{"success": bool, "error_class": str?, "error_message": str, "sanity_ok": bool, "sanity_reason": str, "time_ms": int, "processing_time_ms": int}`

Классы ошибок: `PARSE_ERROR`, `TACTIC_FAILURE`, `GOAL_NOT_CLOSED`, `TIMEOUT`, `SANITY_CHECK_FAILED`.

**Sanity filter**: endpoint отвергает `sorry`-only proofs, bare imports, comment-only, natural language, пустые подачи. Агент об этом знает из system prompt и не тратит tool calls на такие фрагменты.

**Локальный fallback**: `./setup.sh --with-lean-local` поднимает упрощённый Docker (`andkhalov/lean-checker`, Lean 4.24 + Mathlib 4.24) с другой схемой (`{code, import_line}` → `{ok, messages}`). MCP автоматически детектирует схему по URL (наличие `/grag`) и использует нужный формат.

**Warm-up**: первый запрос к SciLib endpoint может занять до 90 секунд (прогрев `lake env` + Mathlib). Последующие — 20-50 мс. Default `timeout` в `lean_check` — 60 секунд, покрывает worst-case холодный старт.

---

## Фаза 4.5 — Research capability

Дополнительно к коду и Lean, агент поддерживает работу с литературой, вебом и Mathlib-поиском. Smoke tests (по одному trial на кейс):

| Кейс | Инструмент | Latency |
|---|---|---|
| PDF info из syllabus | `pdf_info` | 8.9 с |
| PDF summarize (3 страницы) | `pdf_read` (×2) | 15.8 с |
| PDF search (`sorry` в тексте) | `pdf_search` | 8.3 с |
| Web search — Mathlib docs | `web_search` (DDG) | 17.2 с |
| Loogle — `Nat.add_comm` | `lean_search_loogle` | 8.8 с |
| LeanSearch — «commutativity of addition on naturals» | `lean_search_leansearch` | 11.9 с |
| SciLib GraphRAG — goal с `sorry` | `lean_search_scilib` | 15.4 с |

**Итог**: 7/7 PASS.

**Важный нюанс выбора поискового движка** (обнаружен при первой итерации D-сценария): агент, получив инструкцию «спроси пользователя какой движок использовать», приостанавливался для уточнения при любом поисковом запросе. В `run` mode (неинтерактивный stdin) это приводило к зависанию. Решено уточнением правила в recipe: «ask-first применяется только когда пользователь НЕ назвал конкретный движок явно». Явно названный инструмент вызывается напрямую.

Для случаев, когда контекст очевиден (у агента уже есть Lean goal с `sorry`), он напрямую зовёт `lean_search_scilib` — это основной и предпочтительный движок, разработан в рамках того же курса.

---

## Context window и auto-compaction

### Эмпирический probe контекстных лимитов на Yandex

Промпты нарастающего размера (2k → 256k filler tokens) на каждую модель:

| Модель | Max input observed | Поведение на границе |
|---|---|---|
| qwen3-235b-a22b-fp8 | ≥256k (wall ~55 с на 256k) | Верхняя граница не достигнута; практический потолок 256k из-за латентности |
| deepseek-v32 | **131072** (жёсткий) | Yandex возвращает HTTP 400 `max input length is 131072 tokens` выше |
| gpt-oss-120b | **~131072** (комбинированный) | Total (input + output) capped; `max_tokens` уходит в минус выше этого |

### Per-model конфигурация (реализована в `bin/ai4math.py`)

- qwen: `GOOSE_CONTEXT_LIMIT=256000`
- deepseek: `GOOSE_CONTEXT_LIMIT=128000`
- gptoss: `GOOSE_CONTEXT_LIMIT=128000`
- Все: `GOOSE_AUTO_COMPACT_THRESHOLD=0.8`, `GOOSE_MAX_TOKENS=16000`, `GOOSE_TEMPERATURE=0.2`

### Валидация auto-compaction

Тест с искусственно малым окном: `GOOSE_CONTEXT_LIMIT=3000`, `GOOSE_AUTO_COMPACT_THRESHOLD=0.5`, последовательность пяти связных математических вопросов. Goose при превышении 50% порога выводит `Exceeded auto-compact threshold of 50%. Performing auto-compaction... Compaction complete` между turns. Контекст сохраняется — третий ответ (CW-комплексы) корректно ссылается на первый (гомотопические группы). Auto-compaction — это auto-summarization, не обрезка, прозрачно для пользователя.

### Latency вне контекста окна

Independent probe на короткий запрос (одно сообщение, 420 completion tokens):

| Модель | Wall | tok/s |
|---|---|---|
| qwen3-235b | 20.6 с | 20.4 |
| deepseek-v32 | 18.6 с | 32.0 |
| gpt-oss-120b | 3.3 с | 156.2 |

gpt-oss в ~5-8 раз быстрее qwen/deepseek на одношаговых запросах. Но (см. ниже) она не годится для multi-step tool chains из-за совместимости с Goose.

---

## Несовместимость gpt-oss-120b с Goose

**Симптом**: gpt-oss-120b в бенчмарке проходит Task A (один tool call), но на Task B и C зависает после первого tool call (`iters=1`), сессия закрывается без продолжения.

**Корневая причина** (найдена с `RUST_LOG=debug`):

```
-32002: Tool 'text_editor' not found
```

Goose экспортирует инструменты с namespace-префиксами (`developer__text_editor`). qwen и deepseek используют полные имена из tool schema строго. gpt-oss strippит префикс `developer__` и зовёт `text_editor` напрямую — MCP возвращает error code `-32002 Tool not found`, gpt-oss не знает как обработать эту ошибку и прекращает генерацию.

**Статус**: gpt-oss-120b помечена как модель **для one-shot запросов без tool chains**, где её скорость (156 tok/s) — преимущество. Не рекомендуется как default для multi-step code задач. Полное исправление требует либо форка Goose, либо tool-name rewriting middleware — оставлено вне scope Stage 1/2.

---

## Стандарт AGENTS.md

AI4Math читает файл project-level инструкций при старте сессии. Приоритет поиска:

1. `AGENTS.md` — открытый cross-agent стандарт, используется Goose, OpenAI и др.
2. `CLAUDE.md` — fallback для проектов с Claude Code.
3. `.cursorrules` — fallback для проектов из Cursor.

Читается **первый найденный**. Никакого `AI4Math.md` — чтобы не плодить вендор-специфичные файлы. Студент может использовать один `AGENTS.md` параллельно в Claude Code, Cursor, Copilot, AI4Math.

---

## Clean-room тест установки

Реализован в `scripts/clean_room_test.sh`. Запускает в свежем Docker-контейнере `python:3.12-slim` (zero pre-installed tooling):

1. `apt-get install -y git curl bzip2 tar libgomp1` — системные зависимости
2. `git clone https://github.com/andkhalov/AI4Math.git` — клонирование из публичного GitHub
3. Pre-populate `.env` из env vars хоста (симулирует заполнение wizard'ом)
4. `./setup.sh` — венв, pip deps, Goose 1.30.0, symlink в `~/.local/bin/`
5. `./bin/ai4math doctor` — проверка окружения
6. `./bin/ai4math run "Create hello.py with fibonacci..."` — реальный tool call через Yandex endpoint
7. Верификация артефакта: `python3 hello.py` output matches expected sequence

**Результат**: PASS.

**Timing**:

| Шаг | Время |
|---|---|
| apt install (5 пакетов) | ~15 с |
| git clone | <1 с |
| setup.sh (venv + pip + Goose) | ~25 с |
| ai4math doctor | <1 с |
| ai4math run (Task A) | ~10 с |
| **Total clone-to-working-agent** | **~40 секунд** |

Если apt-пакеты предустановлены: `git clone` + `./setup.sh` занимает **~26 секунд**. Целевое «5 минут» из постановки — с большим запасом.

### libgomp1 зависимость (находка clean-room теста)

Goose Rust-бинарь динамически линкуется с libgomp (OpenMP runtime), которая отсутствует в slim-образах (python:3.12-slim, debian:bookworm-slim). `setup.sh` и `setup.py` теперь делают pre-flight check и печатают OS-специфичный install hint (apt/dnf/pacman/brew) при отсутствии.

---

## CI (GitHub Actions)

`.github/workflows/test.yml` запускает три параллельных job на каждый push:

- **linux-clean-room** — Ubuntu latest + clean-room test
- **macos-setup** — macOS latest + setup.sh + ai4math run Task A
- **windows-setup** — Windows latest + setup.bat + bin\ai4math.bat run Task A

Каждый job делает полный setup и выполняет Task A (fibonacci + verify output). Secrets `YANDEX_AI_API` и `YANDEX_CLOUD_FOLDER` загружаются из repository secrets.

CI отметит любой регресс прямо в PR — сломанные платформы видны сразу.

---

## Метрики — сводная таблица

| Метрика | Значение |
|---|---|
| Собственный код shipping | ~945 строк |
| `src/ai4math_mcp.py` (единый MCP-сервер) | ~540 строк, 13 tools |
| `bin/ai4math.py` (cross-platform core) | ~380 строк |
| `recipes/ai4math.yaml` (persona + tools) | ~265 строк |
| `setup.py` / `setup.sh` | ~300 + ~120 строк |
| `cli/wizard.py` | ~157 строк |
| Phase 3 benchmark runs | 60 trials × 2 модели × 3 задачи |
| Phase 4 Lean scenarios | 12 trials × 4 сценария |
| Phase 4.5 research smoke | 7 кейсов × 1 trial |
| Clean-room test PASS time (from GitHub clone) | ~40 секунд |
| qwen success rate (Phase 3 aggregate) | **96.7 %** |
| deepseek success rate (Phase 3 aggregate) | **90.0 %** |
| qwen mean latency (across all 3 tasks) | ~16.8 с |
| deepseek mean latency | ~29.7 с |
| Lean verification latency after warm-up (SciLib) | 20-50 мс |
| Lean verification warm-up (cold start) | up to 90 с |

---

## Артефакты

- [`report/phase3_summary.json`](phase3_summary.json) — сырые метрики 60 runs из Phase 3 benchmark
- [`report/phase3_benchmark.tex`](phase3_benchmark.tex) — LaTeX сводка со статистикой (McNemar, Wilcoxon, Cohen's d, bootstrap CI). Компилируется через `pdflatex main.tex`.
- [`scripts/clean_room_test.sh`](../scripts/clean_room_test.sh) — воспроизводимый тест установки в `python:3.12-slim`.

---

## Ссылки

- [SciLib-GRC21 API docs](https://github.com/andkhalov/SciLib-GRC21/blob/main/docs/api.md) — спецификация `/check` и `/search`
- [Goose GitHub](https://github.com/aaif-goose/goose) — agentic framework
- [Yandex AI Studio quickstart](https://yandex.cloud/ru/docs/ai-studio/quickstart) — получение API ключа
- [Mathlib documentation](https://leanprover-community.github.io/mathlib4_docs/) — стандартная библиотека Lean 4

---

*Документ поддерживается вместе с кодом. При значимых изменениях стека (новая модель, другой framework, изменение архитектуры Lean backend) обновляется в том же commit.*
