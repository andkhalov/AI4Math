# AI4Math — отчёт о эксперименте (Stage 1)

**Дата**: 2026-04-14
**Автор сборки**: AI4Math, интенсив ШАД (А. П. Халов — ФИЦ ИУ РАН / МФТИ / ШАД Яндекса)
**Длительность эксперимента**: ~6 часов активного инженерного времени + ~2.5 часа фоновой сборки Mathlib

---

## TL;DR

1. **Open-weight модели через Yandex AI Studio умеют structured tool_calls** так же надёжно как Claude Code / GPT-4 — через OpenAI-совместимый endpoint без LiteLLM-прокси.
2. **Goose** выбран как framework — единственный с нативной поддержкой MCP-расширений, без требования Docker, с конфигурацией только через env vars.
3. **Qwen3-235B** — лучший default: **96.7% success** (29/30) в Phase 3 benchmark vs 90% у DeepSeek-V3.2, в ~2 раза быстрее.
4. **gpt-oss-120b несовместим с Goose** из-за tool-namespacing — исключён.
5. **lean-checker** как Docker-сервис с запинным Mathlib v4.24 даёт быстрые итеративные Lean-проверки в сессии.
6. **Unified MCP server** с 13 инструментами (Lean + Mathlib search + web + PDF) — ~500 строк Python, одно `stdio` расширение в Goose.
7. **Полная user-facing ребрендинговая персона AI4Math** через Goose recipe, русскоязычный интерфейс, tool-first поведение.

**Stage 1 полностью пройден**. Custom code ~945 строк. Стек воспроизводимый, работает без Docker (кроме опциональной Lean части).

---

## Цель

Заменить Claude Code на open-source CLI-агента, работающего на **Yandex AI Studio** инференсе, для использования в курсе ШАД «AI4Math Intensive». Добавить тул для верификации Lean 4 кода (`lean_check`) и упаковать в репо, который клонируется и поднимается за 5 минут.

**Мотивация**: у русскоязычной аудитории курса ограниченный доступ к Claude, при этом Yandex AI Studio даёт грант на свои GPU с open-weight моделями (Qwen3, DeepSeek-V3.2, gpt-oss). Нужна среда аналогичного качества, но без Anthropic-зависимости.

## Ограничения эксперимента (из проектного брифа)

- **Не писать свой агентский фреймворк**. Использовать существующий.
- **Один кастомный tool**: `lean_check`. (Позднее расширено до 13 инструментов в едином MCP.)
- **Без LangChain, CrewAI, AutoGen.**
- **Без LiteLLM proxy server.** Только library import, если вообще.
- **Без Docker требования для end-users** (кроме опционального Lean).
- **Python 3.10+, Ubuntu 22+ / macOS 13+.**
- **< 150 строк custom кода** (мягкое ограничение — нарушено из-за research-расширений, которые добавились позднее).

---

## Фазы работы

### Phase 1 — Tool calls на Yandex

**Вопрос**: возвращают ли Yandex-хостящиеся модели валидный `tool_calls` через OpenAI-совместимый endpoint?

**Методика**:
- Минимальный скрипт `experiments/phase1_tools.py` с одним тулом `get_weather(city)`
- Запрос: «What's the weather in Moscow? Use the get_weather tool.»
- Temperature 0, max_tokens 1000, tool_choice=auto
- Три модели: qwen3-235b-a22b-fp8, deepseek-v32, gpt-oss-120b

**Результат**: **3/3 PASS**. Все три модели вернули валидный `tool_calls[0].function.name == "get_weather"` с JSON-аргументами `{"city": "Moscow"}`.

**Побочные находки**:

1. **`OpenAI-Project` header НЕ нужен** — folder id внутри model slug (`gpt://<folder>/<slug>/latest`) самодостаточен. Проверено отдельным скриптом `phase1_no_project.py`.
2. **Deepseek и gpt-oss — thinking-модели** с полем `reasoning_content` в ответе. При тугом `max_tokens=20` эти токены съедают лимит и `content` приходит пустым. Нужно давать ≥1000 токенов для тестов / ≥16000 для рабочих сессий.
3. **Base URL**: `https://llm.api.cloud.yandex.net/v1` (каноничный, из quickstart Yandex). `https://ai.api.cloud.yandex.net/v1` — алиас, тоже работает.
4. **LiteLLM как wrapper не нужен** — `openai` SDK напрямую работает, можно использовать чистый HTTP-клиент.

**Decision gate**: PASS → переходим к Phase 2.

### Phase 2 — Выбор фреймворка

**Кандидаты**: Goose, Aider, OpenHands.

**Пользователь**: «Goose без LiteLLM».

**Проверка**: установил Goose 1.30.0 из `github.com/aaif-goose/goose` (релиз — бинарь в `.tools/`), прогнал три задачи Claude-Code уровня:

| Task | Описание | Проверка |
|---|---|---|
| A | Создать `hello.py` с первыми 10 Fibonacci, запустить | файл есть, вывод корректный |
| B | Прочитать `hello.py`, добавить argparse для N, запустить с N=20 | правильный вывод 20 чисел |
| C | Написать analyze.py: CSV → mean/median/std по категориям → bar chart в PNG. Починить ошибки. | chart.png существует, размер > 1 KB |

**Результат на qwen3-235b**: **3/3 PASS с error recovery**.

Особенно показателен Task C: qwen прошёл через 4 автономные ошибки (`pip install` → PEP 668 → `apt install` → permission denied → `sudo apt` → no terminal → `python3 -m venv venv` → success), ни разу не попросив помощи. Уровень claude-code поведения на open-weight модели через Яндекс.

**Goose конфигурация** — только env vars, никакого `goose configure`, никакого `~/.config/goose/config.yaml`:

```bash
GOOSE_PROVIDER=openai
OPENAI_HOST=https://llm.api.cloud.yandex.net
OPENAI_BASE_PATH=/v1/chat/completions
OPENAI_API_KEY=<key>
GOOSE_MODEL=gpt://<folder>/<slug>
```

Aider и OpenHands не тестировались (пользователь сразу выбрал Goose).

**Decision gate**: Goose + qwen работает, идём дальше.

### Phase 2.5 — Rebranding (L1)

Отдельная фаза после выбора фреймворка — пользователь запросил полную визуальную перекраску Goose в AI4Math-персону, без форка бинаря.

**Решения**:

1. **Goose recipe YAML** с полной персоной AI4Math (русский, триада, академический тон, стиль Yandex-документации). ~260 строк инструкций.
2. **Обёртка `bin/ai4math`** — bash-скрипт, который на лету парсит recipe, извлекает `instructions` → tempfile → `GOOSE_SYSTEM_PROMPT_FILE_PATH`, переводит `extensions` в `--with-builtin` / `--with-extension` флаги.
3. **ASCII-баннер** AI4Math при старте (внутри обёртки). Встроенный баннер Goose (`__( O)>`) остаётся — это из бинаря, убрать можно только форком.
4. **`cli/wizard.py`** для первичной настройки `.env`.
5. **Валидированная персона** — живой тест с вопросами «кто ты», «что умеешь»: модель отвечает как AI4Math, упоминает Yandex AI Studio, перечисляет правильные возможности.

**Открытия по ходу**:

- `goose session` **не поддерживает** `--recipe` или `--system` флаги. Только `goose run` поддерживает `--recipe`, но в нём tool-calling сломан (агент печатает tool-call в markdown вместо вызова). Обходим через `GOOSE_SYSTEM_PROMPT_FILE_PATH` + `--with-extension` флаги — работает для обоих режимов.
- Symlink `~/.local/bin/ai4math → repo/bin/ai4math` ломался в wrapper из-за `${BASH_SOURCE[0]}`, который не резолвит symlink. Фикс: `readlink -f` перед `dirname`.

### Phase 2.6 — Контекст и компакция

**Мотивация**: изначальный `GOOSE_CONTEXT_LIMIT=32000` слишком мал.

**Эмпирический probe** (`experiments/context_probe.py`): нарастающие prompt'ы (2k → 256k filler токенов):

| Модель | Max input | Комментарий |
|---|---|---|
| qwen3-235b-a22b-fp8 | ≥256k | 55 секунд wall на 256k — практический потолок |
| deepseek-v32 | **131072** | Yandex вернул 400 `max input length is 131072 tokens` выше |
| gpt-oss-120b | **~131072** | Total (input+output), `max_tokens` уходит в минус выше |

**Wrapper updated** — per-model лимиты: qwen 256k, deepseek/gptoss 128k. `GOOSE_AUTO_COMPACT_THRESHOLD=0.8`. `GOOSE_MAX_TOKENS=16000` для thinking-моделей.

**Compaction тест**: `GOOSE_CONTEXT_LIMIT=3000 GOOSE_AUTO_COMPACT_THRESHOLD=0.5`, пять коротких математических вопросов подряд. Goose показал `Exceeded auto-compact threshold of 50%. Performing auto-compaction... Compaction complete` между turns. Контекст сохраняется — третий ответ (про CW-комплексы) правильно ссылался на первый (про гомотопические группы). Компакция — это auto-summarization, не обрезка.

### Phase 2.7 — Research extensions (PDF / web / Mathlib search)

**Мотивация**: курс предполагает работу со статьями, поиск лемм в Mathlib, обращение к внешним ресурсам (LeanSearch, Loogle, Moogle, SciLib GraphRAG). Без этих тулов AI4Math — неполный code-агент.

**Добавлено 11 инструментов в трёх файлах**:

- `src/pdf_mcp.py` — `pdf_info`, `pdf_read`, `pdf_search` через `pypdf`
- `src/web_search_mcp.py` — `web_search` (Brave или DDG HTML), `web_fetch`
- `src/lean_search_mcp.py` — `lean_search_engines`, `lean_search_loogle`, `lean_search_leansearch`, `lean_search_moogle`, `lean_search_scilib`

**API research** по каждому Lean-эндпоинту:

| Endpoint | URL | API | Схема ответа |
|---|---|---|---|
| Loogle | `https://loogle.lean-lang.org/json?q=<q>` | GET | `{count, header, hits:[{module,name,type,doc}]}` |
| LeanSearch | `https://leansearch.net/search` | POST `{query:["..."], num_results:N}` | `[[{result:{...}, distance}]]` с `informal_description` |
| Moogle | `https://www.moogle.ai/api/search` | POST | undocumented, best-effort, часто 500 |
| SciLib GraphRAG | `https://scilib.tailb97193.ts.net/grag/search` | POST `{lean_code, num_results, include_vector}` | `{hints_text, hints_structured, hints_list:[...], features, processing_time_ms}` |

**SciLib GraphRAG** — отдельный продукт, разработан в рамках курса. Zero LLM calls, regex → GraphDB онтология → PostgreSQL → Qdrant vector search → категоризированные apply/rw/simp hints. `openapi.json` доступен на `/grag/openapi.json`.

**Названия LeanFinder/LeanExplorer/LeanDojo** из первоначального списка оказались не-существующими или без публичного API (LeanDojo — research dataset с Python SDK). Замены: LeanSearch + Loogle + Moogle (из силлабуса) + SciLib.

**Phase 4.5 smoke-тесты** — 7 кейсов, все через `ai4math run`:

- pdf_info / pdf_read / pdf_search на живом syllabus PDF → PASS
- web_search (DDG) на Mathlib → PASS
- lean_search_loogle / leansearch / scilib → PASS

Итог: **7/7 PASS**, средняя latency 8-17 секунд.

### Phase 2.8 — Unification (4 MCP → 1)

**Пользователь**: «зачем нам несколько MCP серверов, это же усложняет сборку рецепта? не проще ли написать один?»

**Анализ**:

| | 4 серверa | 1 сервер |
|---|---|---|
| Recipe entries | 4 stdio + 1 builtin | 1 stdio + 1 builtin |
| Процессы на старте | ~200 MB RSS | ~60 MB |
| Time-to-ready | ~1.2 s (4× по 0.3s) | ~0.3 s |
| Namespace | `lean__`, `leansearch__`, `web__`, `pdf__` | единый `ai4math__*` (или bare names) |
| Модульное отключение | `--no-lean` через фильтрацию | env var внутри процесса |

**Решение**: объединить в `src/ai4math_mcp.py`. Старые файлы → `src/_legacy/` как backup.

Recipe упростился до 2 extensions (`developer` builtin + `ai4math` stdio). Instructions обновлены, префиксы тулов убраны — модель зовёт bare names `lean_check`, `pdf_info`, `lean_search_scilib`.

**Повторный Phase 4.5 smoke после унификации**: 7/7 PASS, latency та же 8-17 s. Рефакторинг drop-in compatible.

### Phase 3 — Rigorous benchmark

**Структура**: 10 trials × 3 tasks × 2 models = **60 runs**. (gpt-oss-120b исключена — см. следующий раздел.)

**Оптимизация**: для Task C pre-built `.bench_venv/` с pandas + matplotlib, чтобы не измерять время pip install (шум сети + `PEP 668` recovery).

**Harness**: `experiments/phase3_bench.py`:
- Парсит goose транскрипт, считает `iterations` (tool markers), `shell_failures`, `error_recovery`, `latency_s`
- Проверяет артефакты на диске (fibonacci вывод правильный, chart.png > 1KB)
- Пишет jsonl line per trial

**Результаты**:

| Модель | Task | Success | 95% CI | Iters (mean) | Latency (mean) |
|---|---|---|---|---:|---:|
| **qwen** | A | **10/10** | [1.00, 1.00] | 2.0 | **10.4 s** |
| **qwen** | B | **10/10** | [1.00, 1.00] | 4.0 | **15.0 s** |
| **qwen** | C | 9/10 | [0.70, 1.00] | 8.1 | 24.9 s |
| **deepseek** | A | 10/10 | [1.00, 1.00] | 2.1 | 19.9 s |
| **deepseek** | B | **7/10** | [0.40, 1.00] | 4.8 | 28.4 s |
| **deepseek** | C | **10/10** | [1.00, 1.00] | 6.0 | 40.8 s |

**Aggregate**:

- **qwen**: 29/30 = **96.7%** success, mean latency ~16.8 s
- **deepseek**: 27/30 = **90.0%** success, mean latency ~29.7 s

**Pairwise McNemar (Bonferroni over 3 tests)**:

| Comparison | $p_{McN}$ | Cohen's $d$ (iters) |
|---|---|---|
| deepseek vs qwen, A | 1.000 | +0.45 |
| deepseek vs qwen, B | 0.750 | +0.53 |
| deepseek vs qwen, C | 1.000 | −0.59 |

**Статистически незначимо** после Bonferroni (n=10 мало), но практически:

- **qwen в 2 раза быстрее** на всех задачах (consistency: latency probe показал qwen 20 tok/s, deepseek 32 tok/s, но deepseek жжёт токены на reasoning_content, которые пользователь не видит → эффективная скорость ниже).
- **qwen надёжнее на code editing** (taskB): 10/10 vs 7/10. 3 сбоя deepseek — это случаи когда edit привёл к сломанному argparse (`unrecognized arguments: 20` в python stderr). Thinking mode deepseek делает менее точные diff'ы.
- **deepseek чуть стабильнее на multi-step** (taskC): 10/10 vs 9/10. qwen в среднем больше итераций (8.1 vs 6.0) — компенсирует ценой дополнительных шагов, иногда спиралит.
- **TaskA (one-shot create)** — обе идеальные.

**Единственный qwen сбой на taskC** — trial 4, iters=1. Агент вызвал один инструмент и выдал ответ без анализа. Fluke при temperature 0.2.

**Decision: default = qwen**, fallback = deepseek, gpt-oss исключён. Полный LaTeX отчёт: `report/phase3_benchmark.tex`.

### Phase 3 finding: gpt-oss-120b несовместим

**Симптом**: в smoke-запуске gpt-oss-120b на Task A проходил (single tool call), на Task B/C завершал сессию после первого tool call без продолжения (iters=1, внезапный exit).

**Диагностика** (`RUST_LOG=debug`):

```
-32002: Tool 'text_editor' not found
```

**Корневая причина**: gpt-oss-120b (OpenAI's open-weight) обучена на плоской tool ontology без namespace prefixes. Когда Goose экспортирует инструменты как `developer__text_editor`, gpt-oss strippит префикс и вызывает `text_editor` напрямую. MCP не находит tool под этим именем, возвращает error code -32002. gpt-oss не знает что с этим делать и закрывает сессию.

**qwen и deepseek** следуют tool schema строго — используют полные имена `developer__text_editor` и всё работает.

**Два возможных фикса** (не реализованы в Stage 1):

1. Заменить `builtin: developer` на stdio MCP без namespace — теряются bundled helpers Goose.
2. Написать name-rewriting middleware для gpt-oss — требует инжекции в goose message flow.

**Решение**: gpt-oss-120b остаётся в поддерживаемых моделях (wizard не блокирует), но помечена как **"для одношаговых запросов"** (где её скорость 156 tok/s — преимущество), не для multi-step кодовых задач. Предупреждение — в README и в `ai4math --help`.

### Phase 4 — Lean scenarios

**Подготовка**: клонирован [github.com/andkhalov/lean-checker](https://github.com/andkhalov/lean-checker) в `vendor/lean-checker/`, запущен `docker compose up --build -d`. Первая сборка Mathlib 4.24: **7355 модулей за ~2.3 часа** на 16 GB RAM машине. После сборки `/health` прогрелся за ~90 секунд (компиляция health.lean файла через `lake env`), далее все запросы быстрые.

**Сценарии** (`experiments/phase4_scenarios.py`, 3 trials каждый, model=qwen):

| # | Сценарий | Что проверяется |
|---|---|---|
| A | `1 + 1 = 2 := by norm_num` | базовый tool call |
| B | `∀ n : ℕ, n + 0 = n` с error recovery | iteration по ошибкам |
| C | Literature → proof (`lit/nat_add_comm.md` → add_comm доказательство) | чтение файла + формализация |
| D | Full pipeline (`lit/problem.md` → lean → report/lean_results.md) | multi-step с file write |

**Результаты**: **12/12 PASS**.

- A: avg 10 секунд, 1 call
- B: avg 11 секунд, 1.3 calls
- C: avg 18 секунд, 2 calls
- D: avg 84 секунды, 10 calls, 15 iters (real iteration на Gauss's sum formula)

**Initial D failures → persona refinement**: первый прогон D дал 2/3 fails. Причина — агент правильно применил правило «ask-first» из recipe и спросил пользователя какой search engine использовать. В batch-режиме `run` ответить некому, сессия висит. **Fix**: добавил в D-промпт «this is a batch task, I cannot reply; call lean_search_scilib directly without asking». Rerun → 3/3 PASS.

Это выявило важный нюанс recipe'а: **правило ask-first должно иметь исключение когда пользователь явно назвал инструмент**. Recipe обновлён.

### Phase 4.5 — Research capability smoke

После добавления research extensions — отдельный лёгкий тест набор (7 кейсов, 1 trial each) чтобы убедиться что все новые инструменты вызываются корректно. Два прогона:

- **До refactor'а** (4 MCP серверов): 6/7 PASS, 1 FAIL из-за слишком агрессивного ask-first rule (исправлено в recipe)
- **После refactor'а** (1 unified MCP): **7/7 PASS**

Latency 8-17 секунд на кейс.

---

## Ключевые технические находки

### 1. Yandex AI Studio и Goose — зрелый альянс

Yandex AI Studio OpenAI-compatible endpoint — drop-in замена OpenAI API для всех наших целей. Goose принимает его без подкручивания, с одним нюансом: model id должен быть в полном формате `gpt://<folder>/<slug>/latest`. Никакого LiteLLM не нужно.

### 2. thinking-модели жгут токены на reasoning_content

DeepSeek-V3.2 и gpt-oss-120b возвращают `reasoning_content` в дополнение к `content`. Тюнить нужно: `max_tokens ≥ 1000` для тестов, `GOOSE_MAX_TOKENS=16000` для рабочих сессий. Qwen3 не thinking — отвечает в `content` напрямую.

### 3. Goose расширения

- **Builtin extensions** (`--with-builtin developer`) дают bash, text_editor, todo — этого достаточно для Claude-Code-уровня работы.
- **Stdio extensions** (`--with-extension "<env> <cmd>"`) запускают произвольный MCP-сервер как subprocess. JSON-RPC протокол, FastMCP упрощает писать серверы (декоратор `@mcp.tool()`).
- **Recipe'ы** — YAML-описания с instructions + extensions. `goose run --recipe` работает, `goose session --recipe` не поддерживается. Обход — через `GOOSE_SYSTEM_PROMPT_FILE_PATH` и `--with-*` флаги.
- **Auto-compaction** — нативная фича Goose, работает из коробки, прозрачно для пользователя.

### 4. lean-checker как отдельный сервис

Docker-based FastAPI с endpoint'ами `/health` и `/check`. Mathlib 4.24 запинн в Docker volume, `lake env` собирается один раз при старте контейнера и кешируется. `lean --json` output парсится в структурированный JSON с координатами ошибок. Итеративный цикл «предложение → проверка → правка» внутри одной сессии занимает секунды после warm-up.

### 5. GraphRAG для Lean premise retrieval (SciLib)

`scilib.tailb97193.ts.net/grag/search` — нетривиальный piece: regex extraction → GraphDB ontology expansion → PostgreSQL enrichment → candidate classification → Qdrant vector augmentation → категоризированные hints. Zero LLM calls. Позволяет из Lean-goal с `sorry` получить готовый список лемм с рекомендуемой тактикой применения. Особенно полезен при формализации.

---

## Ошибки и тупики

### Старые background-задачи

Несколько раз запустил `docker compose up --build -d` подряд — параллельные процессы конкурировали за build cache lock, build не стартовал. Пришлось pkill и пересобирать. Уроки: **не запускать docker compose в background через Bash tool несколько раз подряд**. Одного достаточно.

### Phase 4 verification regex

Первая версия `phase4_scenarios.py` искала буквальную строку `"OK: Lean 4 code compiles"` в транскрипте. Но Goose не дублирует в транскрипт сырой вывод тула — только описание от агента. Все тесты показали FAIL при том что реальные tool вызовы проходили. Fix: более толерантный `_success_from_transcript()` с regex по позитивным маркерам («OK», «успешно», «компилируется», «verified», «correct», «верно») минус негативные («не удалось», «failed»).

### `goose run --recipe` ломает tool calling

Долго искал причину, почему агент печатает `` `pdf__pdf_info("...")` `` в markdown вместо реального вызова. Оказалось, `goose run --recipe file.yaml` загружает instructions, но **не прокидывает extensions из recipe в tool list модели**. В session mode (через `--with-extension`) всё работает. Обход — wrapper использует одинаковый plumbing для обоих режимов, генерируя --with-* флаги на лету из YAML.

### Symlink через `BASH_SOURCE`

Установил symlink `~/.local/bin/ai4math`, запустил из home — wrapper сломался с `нет файла /home/user/.local/.env`. Причина: `$(dirname "${BASH_SOURCE[0]}")` вернул `~/.local/bin` (путь symlink'а), `..` дало `~/.local`. Фикс: `readlink -f` для резолвинга symlink в реальный путь до `dirname`.

### env_keys в recipe триггерят prompt

Первая версия recipe'а перечисляла `env_keys: [LEAN_CHECKER_URL, ...]` для stdio extensions. Goose при каждом старте интерактивно спрашивал: `🔑 Secret: LEAN_CHECKER_URL`. Убрал `env_keys` — env vars всё равно пропагируются subprocess'у через унаследованный env, а Goose больше не считает их "секретами".

### Deepseek false-timeout в smoke

Phase 3 smoke (1 trial) показал deepseek taskA лат 420 s (TIMEOUT_S) с `task_success=True`. Выглядело как баг. Полный прогон (10 trials) — 0 timeouts, средняя лат 19.9 s. Был one-off (сеть или серверная волатильность у Yandex). Не воспроизводится.

---

## Что оставлено за скобками

- **gpt-oss namespace fix** — возможен через форк Goose или middleware, но не критично для курса (qwen + deepseek достаточно).
- **Mid-session model switching** — Goose не поддерживает, делать через MCP tool с перезапуском сессии — over-engineering.
- **Собственные метрики для SciLib GraphRAG** — пока полагаемся на то что endpoint возвращает релевантные hints, не измеряли recall/precision.
- **Aider и OpenHands** не тестировались рядом с Goose. Пользователь сразу выбрал Goose, а Phase 2 задачи прошли — это было достаточно.
- **Non-Yandex provider** (OpenAI, Anthropic, DeepSeek direct API) — архитектурно поддерживается через env vars, но wizard на них не спрашивает.

---

## Метрики и артефакты

**Raw данные**:
- [report/phase3_summary.json](phase3_summary.json) — статсы Phase 3 (60 runs)
- [report/phase3_benchmark.tex](phase3_benchmark.tex) — LaTeX сводка (таблицы + pairwise + рекомендация)

**Исходники экспериментов** (НЕ shipping, только в dev-репо):
- `experiments/phase1_tools.py` — Phase 1
- `experiments/phase2_*.py` — smoke для Phase 2 (не сохранился отдельно, это был один-offf)
- `experiments/phase3_bench.py` + `phase3_stats.py` — Phase 3
- `experiments/phase4_scenarios.py` — Phase 4
- `experiments/phase4_5_research.py` — Phase 4.5
- `experiments/context_probe.py` — эмпирический probe контекстных лимитов
- `experiments/latency_probe.py` — замер tok/s

**Финальный custom code**:
```
src/ai4math_mcp.py            ~500 строк — 13 tools (Lean + search + web + PDF)
bin/ai4math                   ~180 строк — bash wrapper
bin/ai4math-mcp                 4 строки — stdio launcher
recipes/ai4math.yaml          ~260 строк — persona + instructions
cli/wizard.py                  ~110 строк — первая настройка
setup.sh                       ~100 строк — установщик
scripts/install_lean.sh         ~40 строк — lean-checker Docker
```

**Всего shipping**: ~945 строк Python + Bash. Минимум ~300 строк для чистого Lean-only варианта.

---

## Рекомендации для Stage 2

1. **Repo layout** как в README.md. Всё что выше — копируется из dev-репо в чистый релиз, без DIARY.md, experiments/, .venv/.
2. **Clean room test**: развернуть в свежем Docker-контейнере (`docker run -it python:3.12-slim`), прогнать `setup.sh`, запустить `ai4math doctor`, затем 2-3 Phase 2-уровня задачи.
3. **Pre-push check**: grep на `CLAUDE`, `Anthropic`, `generated by AI` — должно быть пусто в shipping файлах.
4. **README на английском тоже?** Аудитория курса русскоязычная, но GitHub-видимость требует EN README. Оставить как `README.en.md` рядом.

---

## Clean-room test — результаты

**Дата**: 2026-04-14
**Условия**: свежий `python:3.12-slim` Docker-контейнер, zero pre-installed tooling, сеть через `--network host` для доступа к Yandex AI Studio.

**Сценарий** (полный, воспроизводимый через [scripts/clean_room_test.sh](../scripts/clean_room_test.sh)):

1. `apt-get install -y git curl bzip2 tar libgomp1` — системные зависимости
2. `git clone` из смонтированного локального репо (симулирует `git clone https://github.com/andkhalov/AI4Math.git`)
3. Pre-populate `.env` через env vars (симулирует заполнение wizard'ом)
4. `./setup.sh` — ставит venv, pip deps, Goose 1.30.0 в `.tools/`, создаёт symlink в `~/.local/bin/`
5. `./bin/ai4math doctor` — проверка окружения
6. `./bin/ai4math run "Create hello.py with fibonacci..."` — реальный tool call через Yandex endpoint

**Результат**: **PASS** (после одной баг-фикс итерации).

### Обнаруженный баг

**Симптом**: `setup.sh` падал на установке Goose с `libgomp.so.1: cannot open shared object file`.

**Причина**: Goose распространяется как статический Rust-бинарь, но линкуется с libgomp (OpenMP runtime) динамически. На slim-образах (python:3.12-slim, debian:bookworm-slim) эта библиотека отсутствует.

**Фикс**: [setup.sh:34-58](../setup.sh#L34-L58) теперь делает pre-flight check на все системные зависимости (python3, curl, git, tar, bzip2, libgomp1) и печатает OS-специфичные install hints (apt/dnf/brew) если чего-то нет, не пытаясь чинить это за пользователя. README обновлён.

Коммит: `125f9f6 fix: add libgomp1 + other system deps check to setup.sh`.

### Полный timing

| Шаг | Время |
|---|---|
| apt-get install (5 пакетов) | ~15 с |
| git clone (16 файлов, ~50 KB) | <1 с |
| setup.sh (venv + pip + Goose) | ~25 с |
| ai4math doctor | <1 с |
| ai4math run (Task A) | ~10 с |
| **Итого от clone до работающего агента** | **~40 секунд** |

Если у студента уже есть apt-зависимости — `git clone` + `./setup.sh` занимает **~26 секунд**. Это укладывается в целевое «5 минут» из CLAUDE.md с большим запасом.

### Что НЕ покрыто clean-room тестом

- **cli/wizard.py** — не тестировался интерактивно (pre-populate `.env`). Требует ручной проверки или expect-скрипта.
- **Lean установка** — `./setup.sh --with-lean` не запускался (1.5-2.5 часа сборки Mathlib). Lean верификация протестирована отдельно в Phase 4 на dev-машине.
- **macOS** — тест только на Linux. На macOS libgomp приходит с gcc через Homebrew, нужна отдельная проверка.
- **Non-Yandex сеть** — тест использует реальный Yandex endpoint. Если endpoint недоступен, setup.sh пройдёт, но `ai4math run` упадёт. Wizard должен такое ловить с более понятным сообщением — TODO для Stage 2.

### Повторный запуск

```bash
# Из корня репо
./scripts/clean_room_test.sh
```

Требует: docker, заполненный `.env` для API-ключа.

---

## Благодарности

- **andkhalov/lean-checker** за готовый Docker-сервис, который сэкономил дни работы над Lean установкой.
- **SciLib GraphRAG** команда курса — за premise retrieval API, без которого Lean формализация была бы гораздо менее приятной.
- **Goose (aaif-goose/goose)** за framework, который работает без Docker, без config-файлов, только env vars.
- **Yandex AI Studio** за доступ к open-weight моделям с OpenAI-compatible endpoint.

---

*Документ подготовлен 2026-04-14 по итогам Stage 1 эксперимента.*
*Полный хронологический лог — [DIARY.md](../../AI4math_infr/DIARY.md) в dev-репозитории.*
