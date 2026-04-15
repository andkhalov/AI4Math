# AI4Math

![CI](https://github.com/andkhalov/AI4Math/actions/workflows/test.yml/badge.svg)
![Linux](https://img.shields.io/badge/linux-supported-brightgreen)
![macOS](https://img.shields.io/badge/macOS-supported-brightgreen)
![Windows](https://img.shields.io/badge/Windows-WSL2%20%7C%20native%20beta-yellow)
![License](https://img.shields.io/badge/license-MIT-blue)

**CLI-агент для курса ШАД «AI4Math Intensive — создание персональной AI-среды исследователя-математика».**

AI4Math — это open-source альтернатива Claude Code на инференс-бэкенде Yandex AI Studio. Научный code-ассистент для математика-исследователя с Lean 4 верификацией, поиском по Mathlib через **SciLib-GRC21** и три вспомогательных движка, чтением PDF и веб-поиском.

Разработан в рамках интенсива ШАД «AI4Math Intensive» (автор: А. П. Халов — ФИЦ ИУ РАН | ФИЦ ВЦ РАН | МФТИ | ШАД Яндекса).

---

## Быстрый старт — одна команда

Клон + установка + конфигурация за одну строку. `setup.sh`/`setup.bat` сам создаёт venv, ставит зависимости, качает Goose CLI в `.tools/`, запускает wizard (спросит API-ключ Yandex AI Studio и folder id), создаёт symlink для глобальной команды `ai4math`. После — сразу готово к работе. Каждый push проверяется на всех трёх платформах через GitHub Actions (см. бейдж выше).

**Linux** (Ubuntu 22+ / Debian 12+):

```bash
sudo apt-get install -y git curl python3 python3-venv bzip2 tar libgomp1 && \
  git clone https://github.com/andkhalov/AI4Math.git && cd AI4Math && ./setup.sh
```

**macOS** 13+ (Intel / Apple Silicon):

```bash
git clone https://github.com/andkhalov/AI4Math.git && cd AI4Math && ./setup.sh
```

**Windows 10/11 + WSL2** — рекомендуемый путь для Windows:

```powershell
wsl --install -d Ubuntu
```

затем **внутри WSL Ubuntu** выполнить команду для Linux из блока выше.

**Windows нативно** (PowerShell / cmd, beta):

```batch
git clone https://github.com/andkhalov/AI4Math.git && cd AI4Math && setup.bat
```

После установки — закрой и открой терминал заново, чтобы `~/.local/bin` подхватился в PATH, и запускай:

```bash
# Linux / macOS / WSL
ai4math                              # интерактивная сессия
ai4math -m deepseek                  # выбор модели
ai4math --mode approve               # старт в режиме approve (тулы требуют подтверждения)
ai4math run "промпт"                 # одна задача
ai4math doctor                       # проверка окружения

# В интерактивной сессии
/plan <task>                         # планирование через planner-модель
/mode approve                        # переключение режима на лету
/exit                                # выход

# Windows native
bin\ai4math.bat                      интерактивная сессия
bin\ai4math.bat run "промпт"         одна задача
bin\ai4math.bat doctor               проверка
```

Ключ Yandex AI Studio получить здесь: [yandex.cloud/ru/docs/ai-studio/quickstart](https://yandex.cloud/ru/docs/ai-studio/quickstart).

### Модульные skills

AI4Math использует **on-demand loading of topic-specific skills** — вместо монолитного промпта агент динамически подгружает короткие руководства из `skills/` когда задача затрагивает конкретную область. Это стандартный паттерн Claude Code в адаптации под Goose.

Каждый skill — markdown файл с Claude-Code-совместимым YAML frontmatter:

```markdown
---
name: python
description: Python-скрипты, модули, тесты, Jupyter — execution loop и venv discipline
triggers: Python, .py, venv, pytest, script, notebook, jupyter
combines_with: debug-loop, markdown, latex
---

# Python — паттерны и дисциплина выполнения
...
```

`list_skills()` показывает все описания и совместимости, `load_skill(name)` отдаёт полное содержимое.

Доступные skills (`skills/*.md`):

| Skill | Описание |
|---|---|
| `python` | Python-скрипты, модули, тесты, Jupyter — execution loop и venv discipline |
| `latex` | LaTeX документы, статьи, теоремы/доказательства, pdflatex цикл |
| `markdown` | GitHub-Flavored Markdown — README, документация, diary, обзоры |
| `lean` | Lean 4 — тактики, формализация, верификация через lean_check |
| `literature` | Обзор литературы — web_search → pdf_download → анализ → literature/review.md |
| `debug-loop` | Дисциплина закрытого цикла write→run→observe→fix для любого языка |

**Комбинирование skills**. Skills можно загружать последовательно, несколько за сессию. Типичные комбинации:

- **python + debug-loop** — любой код с тестами и отладкой
- **latex + lean** — научная статья с формализованными теоремами
- **markdown + literature** — обзор литературы с `review.md`
- **python + latex** — графики matplotlib в tex-документ

**Проект-специфичные skills**: положи файл `skills/<name>.md` с frontmatter в корень AI4Math или свой путь через `AI4MATH_SKILLS_DIR`, и агент увидит его через `list_skills`/`load_skill`. Полезно для кастомных convention'ов, internal APIs, и т.п.

### Планирование и approval modes (нативно в Goose)

**Планирование сложных задач** — `/plan <task>` прямо в интерактивной сессии. Goose создаёт план через отдельную planner-модель (`GOOSE_PLANNER_MODEL`/`GOOSE_PLANNER_PROVIDER`, по умолчанию та же модель), показывает пользователю, и после согласия исполняет. Рекомендуемый workflow: `/mode approve` → подготовка контекста → `/plan <task>` → review → accept → auto-исполнение.

**Режимы исполнения** — 4 варианта через `GOOSE_MODE` / флаг `--mode` / slash-команду `/mode <name>`:

| Режим | Поведение |
|---|---|
| `auto` (default) | Все tool calls выполняются автоматически |
| `smart_approve` | Read-only (ls, cat, pdf_read) автоматом; write/exec спрашивают |
| `approve` | Каждый tool call требует подтверждения |
| `chat` | Никаких tool calls — только диалог и план действий |

Переключение на лету: `/mode approve` в интерактивной сессии. При старте: `ai4math --mode approve`.

### Обновление существующей установки

Если у тебя уже стоит прошлая версия AI4Math и нужно обновиться до текущей (после git pull из репо):

```bash
cd AI4Math
git pull origin main
# Полностью пересоздать .venv и переустановить Goose — гарантирует что старые
# shim-скрипты и устаревшие MCP-сервера не мешают новой версии:
rm -rf .venv .tools
./setup.sh
```

`.env` останется без изменений — wizard пропустится, потому что файл существует. Если хочешь заодно переконфигурировать API-ключ или default-модель, перед `./setup.sh` удали и `.env`.

**Важно**: после обновления запусти `ai4math doctor` — новая версия doctor проверяет что MCP-сервер `ai4math` реально отвечает (probe через JSON-RPC `tools/list`), а не только пингует Lean endpoint. Если doctor показывает `MCP ai4math: НЕ ОТВЕЧАЕТ` — значит расширение не загружается (например, `bin/ai4math-mcp` не исполняемый, нет `.venv/bin/python`, или система не может запустить Goose-бинарь). Без работающего MCP агент будет **галлюцинировать** `lean_check`/`web_search` из текста системного промпта и возвращать `-32002 Tool not found` при реальных вызовах.

### Переустановка на новой машине

Та же одна команда из секции выше. Если у тебя нет старого репо — просто клонируй и запускай:

```bash
git clone https://github.com/andkhalov/AI4Math.git && cd AI4Math && ./setup.sh
```

`.env` создастся через wizard заново. Ключ Yandex AI Studio можно скопировать из старого `.env` на исходной машине.

---

## Зачем это

Курс учит математиков-исследователей строить **персональную AI-среду** вокруг триады:

```
Инференс  →  Контекст  →  Верификация
```

- **Инференс** — LLM генерирует код, тексты, доказательства. Без контекста — рулетка.
- **Контекст** — структурированное знание: онтология, Mathlib, журнал, память. Определяет качество инференса.
- **Верификация** — Lean, тесты, peer review. Различает «похоже на правду» от «истинно».

Claude Code — хороший инструмент для первой и третьей части, но зависит от Anthropic API и требует платной подписки. AI4Math даёт сопоставимый класс возможностей через Yandex AI Studio + open-weight модели (Qwen3, DeepSeek-V3.2) + существующий CLI-агент Goose, причём Lean-верификация и premise retrieval работают через собственный сервис [SciLib-GRC21](https://github.com/andkhalov/SciLib-GRC21) курса.

**Ключевая идея**: минимум собственного кода (~500 строк Python) + готовые компоненты. Агентский loop, tool execution и компакция контекста — Goose. Lean 4 + Mathlib верификация и GraphRAG поиск лемм — SciLib-GRC21. Инференс — Yandex AI Studio. Задача AI4Math — аккуратно их связать под узнаваемой персоной для студентов курса.

---

## Детали установки

### Поддерживаемые ОС

| ОС | Статус | Install path |
|---|---|---|
| **Linux** (Ubuntu 22+ / Debian 12+) | ✅ | `./setup.sh` |
| **macOS** 13+ (Intel / Apple Silicon) | ✅ | `./setup.sh` |
| **Windows 10/11 + WSL2** | ✅ | `./setup.sh` внутри WSL |
| **Windows нативно** (PowerShell / cmd) | 🧪 beta | `setup.bat` + `bin\ai4math.bat` |

Все четыре варианта автоматически проверяются на CI (см. бейдж вверху).

### Требования

**Обязательно:**

- **Python 3.10+**
- **curl**, **git**, **tar**, **bzip2** — для установки Goose CLI и зависимостей
- **libgomp1** (Linux) — runtime Goose-бинаря (Rust + OpenMP)
- **~2 ГБ свободного места** на `.venv` + `.tools` + pip кеш

**Опционально — только если нужен локальный Lean** (по умолчанию Lean проверяется через remote SciLib, Docker не нужен):

- **Docker + Docker Compose v2** для `./setup.sh --with-lean-local`
- **~16 ГБ RAM** — минимум для первой сборки Mathlib (1.5-2.5 часа)
- **~8 ГБ свободного места** на Docker volume с готовыми olean

### Что делает установщик

1. Проверяет системные зависимости (Python 3.10+, git, curl, tar, bzip2, libgomp1 на Linux)
2. Создаёт `.venv` и ставит зависимости из `requirements.txt`
3. Качает Goose CLI в `.tools/` (локально, без root)
4. Запускает `cli/wizard.py` — спросит ключ Yandex AI Studio и folder id, запишет `.env`. По умолчанию Lean checker URL подставится на публичный SciLib endpoint (`https://scilib.tailb97193.ts.net/grag`) — локально Docker поднимать не надо.
5. Опционально: `./setup.sh --with-lean-local` дополнительно поднимает `vendor/lean-checker` через `docker compose up -d` для полностью offline-работы (первая сборка Mathlib 1.5-2.5 часа)
6. Создаёт symlink `~/.local/bin/ai4math → bin/ai4math` для глобальной команды (Linux/macOS)

Получить ключ Yandex AI Studio: [yandex.cloud/ru/docs/ai-studio/quickstart](https://yandex.cloud/ru/docs/ai-studio/quickstart).

### Первый запуск

```bash
ai4math                       # интерактивная сессия с моделью по умолчанию
ai4math -m deepseek           # выбор модели
ai4math run "промпт"          # одна задача, вывод в консоль, выход
ai4math doctor                # проверка окружения (ключ, Lean, Goose)
ai4math --help                # справка
```

---

## Возможности

### Как Claude Code

- **shell** — bash в текущем рабочем каталоге, агент сам выбирает команды
- **text_editor** — создание, чтение и правка файлов (precise edit с before/after)
- **todo** — локальный список задач для текущей сессии
- **Автовосстановление** из ошибок — агент сам пересоздаёт venv, переключается на `python3` если нет `python`, исправляет edge cases
- **Многоуровневый контекст** — Goose управляет окном, автоматически суммаризирует при переполнении (auto-compact при 80% от `GOOSE_CONTEXT_LIMIT`, см. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md))

### Lean 4 верификация через SciLib-GRC21

- **lean_check(code, timeout=60)** — отправляет Lean 4 фрагмент в верификатор на базе [SciLib-GRC21](https://github.com/andkhalov/SciLib-GRC21) (Lean 4.28-rc1 + Mathlib 4.26, Mathlib REPL). Возвращает `OK` или структурированную ошибку с одним из классов: `PARSE_ERROR`, `TACTIC_FAILURE`, `GOAL_NOT_CLOSED`, `TIMEOUT`, `SANITY_CHECK_FAILED`.
- **lean_health()** — проверка что endpoint доступен.

По умолчанию используется публичный endpoint `https://scilib.tailb97193.ts.net/grag` — ничего локально поднимать не нужно, `setup.sh` просто подставит этот URL в `.env`. Для полностью offline-работы есть `./setup.sh --with-lean-local` — поднимает упрощённый Docker-чекер на базе [andkhalov/lean-checker](https://github.com/andkhalov/lean-checker) (Lean 4.24 + Mathlib 4.24); MCP автоматически определит старую схему и будет работать с ним.

Sanity-фильтр SciLib отвергает бесполезные подачи: `sorry`-only proofs, bare imports, natural language text, comment-only submissions. Это заложено в системный промпт агента — он не будет тратить tool calls на такие вещи.

Типичный цикл: сформулировал теорему → вызвал `lean_check` → получил класс ошибки + текст → поправил тактику → повторил. 20-50 ms на проверку после первого warm-up.

### Поиск по Mathlib (SciLib GraphRAG + три внешних движка)

Основной инструмент — **`lean_search_scilib`** на базе GraphRAG pipeline нашего собственного SciLib-GRC21 endpoint'а: GraphDB (33.8M RDF триплетов онтологии Mathlib) + PostgreSQL (213K Lean statements) + Qdrant vector search. Принимает Lean goal с `sorry`, возвращает категоризированные hints по тактикам (apply / rw / simp). Zero LLM calls.

Вспомогательные внешние движки для случаев когда goal ещё не сформулирован:

| Движок | Вход | Когда подходит |
|---|---|---|
| **SciLib GraphRAG** ⭐ | Lean goal с `sorry` | уже есть goal, нужны конкретные леммы для применения |
| Loogle | тип/паттерн | знаешь форму искомой леммы (`?a + ?b = ?b + ?a`) |
| LeanSearch | английское описание | «Cauchy criterion for convergent series» |
| Moogle | текстовый запрос | нейросетевой семантический поиск (best-effort) |

SciLib-GRC21 — собственный сервис, разработан в рамках курса, публичный endpoint: [scilib.tailb97193.ts.net/grag](https://scilib.tailb97193.ts.net/grag) ([API docs](https://github.com/andkhalov/SciLib-GRC21/blob/main/docs/api.md)).

### Веб

- **web_search(query)** — Brave Search API (если задан `BRAVE_API_KEY`) или DuckDuckGo (keyless, default)
- **web_fetch(url)** — скачать URL, HTML → plain text, truncate

### PDF

- **pdf_info(path)** — метаданные, количество страниц, размер
- **pdf_read(path, pages)** — извлечь текст из указанных страниц (`"1-5,10"`)
- **pdf_search(path, query)** — подстрочный поиск с контекстом

Полезно для быстрого ознакомления с научными статьями внутри сессии.

---

## Поддерживаемые модели

Все через Yandex AI Studio OpenAI-compatible endpoint:

| Модель | Контекст | Роль |
|---|---|---|
| **Qwen3-235B-A22B-FP8** | 256k токенов | **По умолчанию** — быстрая (~20 tok/s), 96.7% success в бенчмарке, самая стабильная на редактировании кода |
| **DeepSeek-V3.2** | 128k токенов | Thinking-модель, альтернативная опция, может быть точнее на сложных математических задачах |
| gpt-oss-120b | 128k | Только для one-shot запросов без tool chains — несовместима с Goose tool namespacing (см. [EXPERIMENT_REPORT.md](report/EXPERIMENT_REPORT.md)) |

Переключение моделей:

```bash
ai4math -m qwen       # default
ai4math -m deepseek
ai4math -m gptoss
```

Смена модели в середине сессии не поддерживается Goose — `/exit` и `ai4math -m <model>` заново.

---

## Бенчмарк

На трёх задачах уровня Claude Code (создание файла, редактирование с argparse, multi-step CSV-анализ с графиком), 10 trials на каждую:

```
                Task A          Task B          Task C         Итого
qwen            10/10  10.4s    10/10  15.0s    9/10   24.9s   29/30  96.7%
deepseek        10/10  19.9s     7/10  28.4s   10/10   40.8s   27/30  90.0%
```

Полные числа со статистикой (McNemar + Wilcoxon + Cohen's d + bootstrap CI) — [report/phase3_benchmark.tex](report/phase3_benchmark.tex), методика — [report/EXPERIMENT_REPORT.md](report/EXPERIMENT_REPORT.md).

---

## Структура проекта

```
AI4Math/
├── README.md                     этот файл
├── LICENSE                       MIT
├── setup.sh / setup.py / setup.bat   установщик (Linux/кросс-платформа/Windows)
├── requirements.txt              python-зависимости
├── .env.example                  шаблон .env
├── .gitignore
│
├── bin/
│   ├── ai4math                   основной shell shim (Linux/macOS)
│   ├── ai4math.py                cross-platform Python entrypoint
│   ├── ai4math.bat               Windows cmd shim
│   └── ai4math-mcp               stdio launcher для MCP-сервера
│
├── src/
│   └── ai4math_mcp.py            единый MCP-сервер (13 tools)
│
├── recipes/
│   └── ai4math.yaml              Goose recipe: персона + список расширений
│
├── cli/
│   └── wizard.py                 интерактивный wizard первой настройки
│
├── scripts/
│   ├── install_lean.sh           опциональный local Docker lean-checker
│   └── clean_room_test.sh        воспроизводимый тест установки в python:3.12-slim
│
├── .github/workflows/
│   └── test.yml                  CI: linux + macOS + Windows setup + Task A
│
├── docs/
│   └── ARCHITECTURE.md           инженерный обзор
│
├── report/
│   ├── EXPERIMENT_REPORT.md      отчёт о эксперименте и методике бенчмарка
│   ├── phase3_benchmark.tex      LaTeX сводка (pdflatex для PDF)
│   └── phase3_summary.json       сырые результаты бенчмарка
│
└── vendor/lean-checker/          (создаётся --with-lean-local) опциональный локальный чекер
```

---

## Файл инструкций проекта (AGENTS.md)

В своих проектах пользователя AI4Math автоматически читает один файл с контекстными инструкциями при старте сессии — в таком приоритете:

1. **`AGENTS.md`** — открытый cross-agent стандарт ([agentsmd.io](https://agentsmd.io/), используется Goose, OpenAI и др.). **Предпочтительный формат.**
2. **`CLAUDE.md`** — fallback для проектов, мигрирующих с Claude Code.
3. **`.cursorrules`** — fallback для проектов из Cursor.

Читается **первый найденный**. В этот файл пиши правила проекта: стиль кода, структуру, запреты, чек-листы, стандартные команды. Пример шаблона:

```markdown
# My project

Python 3.12, pytest, ruff. Lean 4 + Mathlib.

## Стиль
- Код без комментариев кроме WHY-комментов
- Пути файлов в формате `path/file.py:42`
- Русский в документации, английский в коде

## Команды
- Тесты: `pytest -q`
- Lint: `ruff check .`
- Lean build: `lake build`

## Чего не делать
- Не коммить `.env`
- Не использовать `sorry` в финальных доказательствах
- Не создавать новые README.md без запроса
```

Правила этого файла **важнее** общих инструкций AI4Math в части конкретных правил проекта. Но идентичность агента (русский язык, роль, стиль триады) остаётся системной.

**Почему AGENTS.md, а не `AI4Math.md`?** Не вводим ещё один вендор-специфичный файл. AI4Math — не отдельная экосистема, а удобный клиент к Yandex AI Studio моделям. Пользователи курса могут параллельно использовать Claude Code, Cursor, GitHub Copilot — один и тот же `AGENTS.md` будет работать везде, где этот стандарт поддерживается.

---

## FAQ

**Q: Чем это отличается от Claude Code?**  
A: Работает на Yandex AI Studio с open-weight моделями, бесплатно для исследователей с яндекс-грантом. Набор возможностей аналогичен: bash/text_editor/todo tools, персональная среда через Goose recipe, tool-first поведение. Отличия: (a) нет модели от Anthropic, (b) нет Anthropic-специфичных фич (их MCP маркетплейс, computer use), (c) добавлена Lean 4 верификация и Mathlib-поиск через SciLib-GRC21.

**Q: Можно ли подключить OpenAI / Anthropic / DeepSeek API напрямую?**  
A: Архитектурно — да, обёртка `bin/ai4math.py` собирает env vars для Goose, а Goose принимает любой OpenAI-compatible endpoint. Wizard сейчас спрашивает только про Yandex; добавить других провайдеров — ~20 строк в `cli/wizard.py` и recipe.

**Q: Нужен ли Docker для работы?**  
A: Нет. По умолчанию Lean верификация идёт через публичный SciLib-GRC21 endpoint (`https://scilib.tailb97193.ts.net/grag`) — ничего локально поднимать не надо. Docker нужен только если хочется полностью offline-режим через `./setup.sh --with-lean-local`.

**Q: Почему Goose, а не Aider / OpenHands?**  
A: Goose поддерживает MCP-расширения нативно (идеально для кастомных инструментов вроде `lean_check`), не требует Docker для самого агента, настраивается только env-переменными без config-файла, ставится как статичный бинарь. Методика выбора описана в [EXPERIMENT_REPORT.md](report/EXPERIMENT_REPORT.md).

**Q: Что такое «триада инференс → контекст → верификация»?**  
A: Философский каркас курса: LLM — одна из трёх опор, не единственная. Верификация (Lean) отделяет правду от правдоподобия. Контекст (онтология, журнал, память) определяет качество генерации. Исследовательская среда ценна сама по себе, даже без CLI-агента.

**Q: Приватность — куда уходит мой Lean код при проверке?**  
A: По умолчанию — на публичный SciLib-GRC21 endpoint курса. Для чувствительных доказательств используй `./setup.sh --with-lean-local` и переключи `LEAN_CHECKER_URL` в `.env` на `http://localhost:8888` — код остаётся локально в Docker-контейнере.

---

## Связанные проекты

- **[SciLib-GRC21](https://github.com/andkhalov/SciLib-GRC21)** — собственный сервис курса: Lean 4 верификация + GraphRAG premise retrieval, Lean 4.28 + Mathlib 4.26. Используется AI4Math как основной Lean backend. [API docs](https://github.com/andkhalov/SciLib-GRC21/blob/main/docs/api.md).
- **[andkhalov/lean-checker](https://github.com/andkhalov/lean-checker)** — упрощённый локальный Docker-чекер (Lean 4.24 + Mathlib 4.24), опциональная альтернатива SciLib для offline-работы.
- **[Goose](https://github.com/aaif-goose/goose)** — open-source AI agent framework, используется под капотом.
- **[Yandex AI Studio](https://yandex.cloud/ru/docs/ai-studio)** — OpenAI-compatible endpoint с open-weight моделями.
- **[Mathlib](https://leanprover-community.github.io/mathlib4_docs/)** — стандартная библиотека Lean 4.

---

## Лицензия

MIT. См. [LICENSE](LICENSE).

Продукт разработан в рамках интенсива ШАД «AI4Math Intensive» —
А. П. Халов, ФИЦ ИУ РАН | ФИЦ ВЦ РАН | МФТИ | ШАД Яндекса.
