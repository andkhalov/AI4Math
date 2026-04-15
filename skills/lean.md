---
name: lean
description: Lean 4 — тактики, формализация, верификация через lean_check
triggers: Lean, theorem, proof, Mathlib, norm_num, omega, ring, lean_check
combines_with: latex (при формализации из статьи), literature (при поиске нужной теоремы)
---

# Lean 4 — тактики, workflow, типичные ошибки

## Инструменты

- `lean_check(code, timeout=60)` — основная верификация через SciLib-GRC21.
  Backend: Lean 4.28-rc1 + Mathlib 4.26, Mathlib REPL.
- `lean_health()` — ping endpoint'а.
- `lean_search_scilib(lean_code, n)` — **primary**: GraphRAG premise
  retrieval. Принимает Lean goal с `sorry`, возвращает категоризированные
  hints (apply / rw / simp).
- `lean_search_loogle(query)` — поиск по типу/паттерну.
- `lean_search_leansearch(query, n)` — семантический с English descriptions.
- `lean_search_moogle(query)` — neural, best-effort.

## Шаблоны правильного вызова lean_check

Копируй эти паттерны, не изобретай свои:

```python
lean_check("example : 1 + 1 = 2 := by norm_num")
lean_check("theorem t (n : ℕ) : n + 0 = n := by simp")
lean_check("example : ∀ n : ℕ, n + 0 = n := by intro n; rfl")
lean_check("example (a b : ℝ) : a + b = b + a := by ring")
```

- `code` — строка, **одно целое Lean 4 выражение**.
- `timeout` — секунды, default 60. Если первый вызов вернул `TIMEOUT`,
  повтори с `timeout=120` максимум один раз.

## Классы ошибок SciLib checker

| Класс | Что значит | Что делать |
|---|---|---|
| `SANITY_CHECK_FAILED` | Код отвергнут как бесполезный | Замени `sorry` реальной тактикой; добавь тело если был только `import`; убери natural language |
| `PARSE_ERROR` | Синтаксис не распарсился | Проверь unicode (`ℕ` vs `\mathbb{N}`), балансы скобок, `:=` vs `:` |
| `TACTIC_FAILURE` | Тактика упала | Попробуй альтернативу из правила подбора |
| `GOAL_NOT_CLOSED` | Остались незакрытые цели | Добавь ещё тактики или разбей на части |
| `TIMEOUT` | Не уложились в timeout | Упрости proof или увеличь `timeout` до 120 |

## Правило подбора тактик

Ядро Mathlib (80% случаев):

- **Тождество алгебры** (`a + b = b + a`, `a * (b + c) = a*b + a*c`) → `ring`
- **Линейная арифметика** на `ℤ`/`ℕ`/`ℚ` без умножения переменных → `omega`
- **Линейные неравенства** с числами → `linarith`
- **Нелинейные неравенства** → `nlinarith [sq_nonneg ...]`
- **Числовой расчёт** (`2 + 2 = 4`, `3 < 5`) → `norm_num`
- **Конъюнкция** (`P ∧ Q`) → `constructor`, затем докажи части
- **Импликация** (`P → Q`) → `intro h` и затем доказывай `Q` при `h : P`
- **Forall** (`∀ x, P x`) → `intro x`
- **Equals на функциях** → `funext` + доказательство поточечно
- **Simp-нормализация** → `simp` (с осторожностью — может переписать в неожиданную форму)
- **Rewrite по известному равенству** → `rw [eq_name]`
- **Индукция** → `induction n with | zero => ... | succ k ih => ...`

Расширенные:
- `cases` — разбор case'ов
- `exact` — точное соответствие терма цели
- `apply` — применение леммы (back-chaining)
- `have h : T := by ...` — промежуточная лемма
- `show T` — переформулировка цели
- `field_simp` — нормализация дробей
- `native_decide` — decision procedure через compile-time evaluation

## Ловушки

**Natural numbers ℕ**:
- `5 - 7 = 0` (truncated subtraction)
- `7 / 2 = 3` (floor division)
- Для настоящей арифметики — `Int`, `Rat`, `Real`. Каст: `(n : ℤ)`, `(n : ℝ)`.

**sorry**:
- `sorry` — аксиома, доказывающая что угодно, включая `False`. Это маркер
  дыры, не доказательство.
- **Не подавай `sorry`-only код в `lean_check`** — SciLib sanity filter
  отвергнет. `sorry` валиден только как часть контекста для
  `lean_search_scilib`.
- После каждой итерации проверяй: `grep "sorry" <file>` → должно быть пусто
  в финальном доказательстве.

**omega vs linarith**:
- `omega` — decision procedure для арифметики Пресбургера (линейная
  `ℤ`/`ℕ` без произведений переменных). Быстрее и полнее для ℤ/ℕ.
- `linarith` — работает на любом упорядоченном поле, но только линейные
  комбинации.
- Выбирай `omega` когда цели в ℤ/ℕ. `linarith` когда ℝ/ℚ или смешанные.

**simp**:
- Мощный, но может переписать цель в неожиданную форму, после которой
  ничего не работает. Используй `simp only [<specific lemmas>]` чтобы
  ограничить.
- `simp` после других тактик — нормально. `simp` как первый шаг — опасно.

## Итеративный цикл верификации

1. Сформулируй `theorem`/`example` с конкретным телом (не `sorry`).
2. `lean_check(code=...)`.
3. Если `OK:` — готово.
4. Если `ERROR [GOAL_NOT_CLOSED]` — прочитай `error_message`, определи
   какая цель осталась. Замени тактику на альтернативу из правила подбора.
5. Если `ERROR [TACTIC_FAILURE]` — тактика не подходит. Попробуй
   `lean_search_scilib(your_code_with_sorry)` чтобы получить hints.
6. Если `ERROR [PARSE_ERROR]` — синтаксис сломан. Проверь символы.
7. Максимум **5 итераций**. После пятой — остановись, попроси у
   пользователя контекст.

## Когда использовать lean_search_*

- **Goal с `sorry` уже есть** → `lean_search_scilib` — самый точный путь.
- **Ищу лемму по форме типа** → `lean_search_loogle`.
- **Ищу по английскому описанию** → `lean_search_leansearch`.
- **Общий семантический поиск** → `lean_search_moogle` (fallback).

Если пользователь явно не указал движок — предпочитай `lean_search_scilib`
когда goal у тебя уже есть. Не спрашивай какой движок использовать каждый
раз, если контекст очевиден.

## Формализация из неформального описания

Частый workflow: пользователь даёт теорему в LaTeX/словах, просит
формализовать в Lean.

1. Прочитай формулировку, найди математический тип (алгебра/анализ/
   теория чисел/топология).
2. Выпиши Lean 4 statement — сначала без proof: `theorem t (args) : stmt := sorry`.
3. Вызови `lean_search_scilib(code)` с этим sorry, получи hints.
4. Попробуй применить apply/rw/simp hints по очереди.
5. `lean_check` после каждой версии.
6. Если зашёл в тупик — покажи пользователю текущее состояние и
   попроси подсказку.

## Anti-patterns

- `:= by sorry` как финальный ответ — это дыра, не доказательство.
- `:= by simp; sorry` — даже хуже, выглядит как попытка скрыть sorry.
- `induction n; simp; exact rfl` — смешивание одним махом; лучше `induction
  n with | zero => ... | succ k ih => ...`
- `apply` без указания леммы когда у тебя точно ничего не выводится
  — Lean не догадается. Дай конкретное имя.
- Смешивание `:` и `:=` — `theorem t : X := y` vs `def f : X := y` — читай
  внимательно.
