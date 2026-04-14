# AI4Math

**Неофициальный CLI-агент для курса ШАД «AI4Math Intensive — создание персональной AI-среды исследователя-математика».**

AI4Math — это open-source альтернатива Claude Code, работающая на инференс-бэкенде Yandex AI Studio. Персональный научный code-ассистент для математика-исследователя с поддержкой Lean 4 верификации, поиска по Mathlib через четыре движка, чтения PDF и веб-поиска.

Разработан в рамках интенсива ШАД «AI4Math Intensive» (автор: А. П. Халов — ФИЦ ИУ РАН / МФТИ / ШАД Яндекса).

---

## Зачем это

Курс учит математиков-исследователей строить **персональную AI-среду** вокруг триады:

```
Инференс  →  Контекст  →  Верификация
```

- **Инференс** — LLM генерирует код, тексты, доказательства. Без контекста — рулетка.
- **Контекст** — структурированное знание: онтология, Mathlib, журнал, память. Определяет качество инференса.
- **Верификация** — Lean, тесты, peer review. Различает «похоже на правду» от «истинно».

Claude Code хорошо умеет первую и третью часть, но (a) требует платной подписки от Anthropic, (b) у многих исследователей нет доступа к Claude. AI4Math даёт тот же класс возможностей через Yandex AI Studio + open-weight модели (Qwen3, DeepSeek-V3.2) + существующий CLI-агент Goose.

**Ключевая идея**: мы ничего своего не пишем, кроме ~500 строк Python. Всё тяжёлое (агентский loop, tool execution, компакция контекста) делает Goose. Всё Lean-специфичное (компиляция с Mathlib) делает отдельный Docker-сервис [lean-checker](https://github.com/andkhalov/lean-checker). Yandex AI Studio даёт совместимый с OpenAI endpoint. Мы только склеиваем.

---

## Быстрый старт

### Требования

- **Python 3.10+**
- **curl**
- **Docker + Docker Compose v2** — только если нужна Lean верификация
- **~16 ГБ RAM** — минимум для работы Lean (1.5-2.5 часа первой сборки Mathlib)

### Установка (5 минут без Lean, ~2.5 часа с Lean)

```bash
git clone https://github.com/andkhalov/AI4Math.git
cd AI4Math
./setup.sh              # без Lean
# или
./setup.sh --with-lean  # + docker compose up lean-checker
```

`setup.sh` делает:

1. Проверяет Python 3.10+
2. Создаёт `.venv` и ставит зависимости из `requirements.txt`
3. Качает Goose CLI в `.tools/` (локально, без root)
4. Запускает `cli/wizard.py` — спросит ключ Yandex AI Studio и folder id, запишет `.env`
5. Опционально: поднимает `vendor/lean-checker` через `docker compose up -d` (первая сборка Mathlib 1.5-2.5 часа)
6. Создаёт symlink `~/.local/bin/ai4math → bin/ai4math` для глобальной команды

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

### Lean 4 верификация

- **lean_check(code, import_line)** — отправляет Lean 4 фрагмент во внешний верификатор, возвращает `OK` или ошибки с координатами `L<line>:C<col>`. Mathlib 4.24 подключён автоматически.
- **lean_health()** — проверка что сервис поднят.

Типичный цикл: сформулировал теорему → вызвал `lean_check` → получил ошибку с координатами → исправил тактику → повторил. Работает в сессии быстро благодаря закешированному `lake env` в Docker.

### Поиск по Mathlib (четыре движка)

Для каждого движка — отдельный инструмент. Когда пользователь просит «найди лемму», агент спрашивает какой движок использовать, если это неочевидно:

| Движок | Вход | Сильная сторона |
|---|---|---|
| **Loogle** | тип/имя/паттерн | `?a + ?b = ?b + ?a` — тип-ориентированный поиск |
| **LeanSearch** | английское описание | «Cauchy criterion for convergent series» |
| **Moogle** | текстовый запрос | нейросетевой семантический (best-effort) |
| **SciLib GraphRAG** | Lean 4 goal с `sorry` | категоризированные apply/rw/simp hints, zero LLM calls |

SciLib GraphRAG ([scilib.tailb97193.ts.net/grag](https://scilib.tailb97193.ts.net/grag)) — собственный endpoint с premise retrieval через GraphDB + Qdrant, разработан в рамках курса.

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
| **Qwen3-235B-A22B-FP8** | 256k токенов | **По умолчанию** — быстрая (~20 tok/s), 96.7% success в Phase 3 benchmark, самая стабильная на редактировании кода |
| **DeepSeek-V3.2** | 128k токенов | Thinking-модель (~32 tok/s видимых токенов), может быть точнее на сложных математических задачах |
| gpt-oss-120b | 128k | **Не рекомендуется** как основная — несовместима с Goose tool namespacing (см. [EXPERIMENT_REPORT.md](report/EXPERIMENT_REPORT.md)) |

Переключение моделей:

```bash
ai4math -m qwen       # default
ai4math -m deepseek   # thinking
ai4math -m gptoss     # для одношаговых вопросов, где нужна скорость (~156 tok/s)
```

Смена модели в середине сессии не поддерживается Goose нативно — `/exit` и `ai4math -m <model>` заново.

---

## Бенчмарк (Phase 3)

На трёх задачах уровня Claude Code (создание файла, редактирование с argparse, multi-step анализ CSV с построением графика):

```
                Task A          Task B          Task C         Итого
qwen            10/10  10.4s    10/10  15.0s    9/10   24.9s   29/30  96.7%
deepseek        10/10  19.9s     7/10  28.4s   10/10   40.8s   27/30  90.0%
```

Полный отчёт со статистикой (McNemar + Wilcoxon + Cohen's d + bootstrap CI) — [report/phase3_benchmark.tex](report/phase3_benchmark.tex), подробности эксперимента — [report/EXPERIMENT_REPORT.md](report/EXPERIMENT_REPORT.md).

---

## Структура проекта

```
AI4Math/
├── README.md                     этот файл
├── LICENSE                       MIT
├── setup.sh                      установщик
├── requirements.txt              python-зависимости
├── .env.example                  шаблон .env
├── .gitignore
│
├── bin/
│   ├── ai4math                   основная команда-обёртка
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
│   └── install_lean.sh           docker compose up для lean-checker
│
├── docs/
│   └── ARCHITECTURE.md           как это работает внутри
│
├── report/
│   ├── EXPERIMENT_REPORT.md      полный отчёт о эксперименте
│   ├── phase3_benchmark.tex      LaTeX бенчмарка (pdflatex для PDF)
│   └── phase3_summary.json       сырые результаты бенчмарка
│
└── vendor/lean-checker/          (создаётся install_lean.sh) submodule lean-checker
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
A: Работает на Yandex AI Studio, бесплатно для исследователей с яндекс-грантом. Use cases те же, но: (a) нет Claude как модели, (b) нет Anthropic-специфичных фич (MCP маркетплейс от Anthropic, computer use), (c) добавлена Lean 4 интеграция и Mathlib поиск.

**Q: Можно ли добавить OpenAI / Anthropic / DeepSeek API как провайдера?**  
A: Архитектурно — да, обёртка `bin/ai4math` собирает env vars для Goose, а Goose умеет любой OpenAI-compatible endpoint. Сейчас wizard поддерживает только Yandex; добавление других провайдеров — ~20 строк в wizard.py и recipe.

**Q: Зачем нужен Docker lean-checker?**  
A: Lean + Mathlib = ~8 ГБ RAM для сборки, Lean 4.24 + зависимости, ~20-40 минут первой сборки. Docker изолирует и кеширует — pinned версии, не ломается от обновлений системы. Альтернатива: установить Lean локально через `elan init` + `lake init math` + `lake build` — работает, но ставит toolchain глобально.

**Q: Почему Goose, а не Aider / OpenHands?**  
A: Goose даёт: native MCP extensions (идеально для `lean_check`), отсутствие Docker-требования для самого агента, работу только по env-vars без config-файла, быструю установку через статичный бинарь. Aider не имеет plugin API, OpenHands требует Docker. Подробности решения — в [EXPERIMENT_REPORT.md](report/EXPERIMENT_REPORT.md).

**Q: Что такое «триада инференс → контекст → верификация»?**  
A: Философский каркас курса. AI4Math это каркас инструментов для исследователя, который понимает что LLM — это одна из трёх опор, а не единственная. Верификация (Lean) отделяет правду от правдоподобия. Контекст (онтология, журнал, память) определяет качество генерации.

**Q: Можно ли использовать без Lean?**  
A: Да. `./setup.sh` без `--with-lean` — всё работает как Claude Code для кода + веб + PDF. `lean_check` возвращает graceful error если сервис не поднят; агент об этом знает и ведёт себя корректно.

---

## Связанные репозитории

- **lean-checker** — Docker-сервис для верификации Lean 4 кода с Mathlib: [github.com/andkhalov/lean-checker](https://github.com/andkhalov/lean-checker)
- **Goose** — open-source AI agent framework, используется под капотом: [github.com/aaif-goose/goose](https://github.com/aaif-goose/goose)
- **SciLib GraphRAG** — premise retrieval для Lean 4 через GraphDB + Qdrant: [scilib.tailb97193.ts.net/grag/docs](https://scilib.tailb97193.ts.net/grag/docs)
- **Yandex AI Studio** — OpenAI-compatible endpoint: [yandex.cloud/ru/docs/ai-studio](https://yandex.cloud/ru/docs/ai-studio)
- **Mathlib** — стандартная библиотека Lean 4: [leanprover-community.github.io/mathlib4_docs](https://leanprover-community.github.io/mathlib4_docs/)

---

## Лицензия

MIT. См. [LICENSE](LICENSE).

Продукт разработан в рамках интенсива ШАД «AI4Math Intensive» —
А. П. Халов, ФИЦ ИУ РАН | МФТИ | ШАД Яндекса.
