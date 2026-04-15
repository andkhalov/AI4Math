# LaTeX — паттерны и компиляция

## Когда использовать LaTeX vs Markdown

- **LaTeX** — научные статьи, диссертации, книги, слайды Beamer, документы с
  сложной математикой (теоремы, доказательства на 2+ страницах, большие формулы).
- **Markdown** — README, документация, краткие заметки, diary.md, обзоры
  литературы, notebook-подобные отчёты. Github-рендерит MD с подсветкой
  кода и базовой математикой через KaTeX.
- **Правило**: если пользователь попросил `.md` — не отдавай `.tex`. Если
  попросил научную статью / диссертацию — `.tex`. Если не уверен — спроси.

## Минимальный preamble для математики

```latex
\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T2A]{fontenc}          % Русский
\usepackage[russian,english]{babel}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{mathtools}              % расширение amsmath
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage{hyperref}
\hypersetup{colorlinks=true,linkcolor=blue!70!black,urlcolor=blue!60!black}
\usepackage{graphicx}
\usepackage{booktabs}               % красивые таблицы: \toprule \midrule \bottomrule
\usepackage{microtype}              % улучшенный кернинг
\usepackage{listings}               % код
\usepackage{xcolor}
```

Для Beamer-презентаций замени `article` на `beamer` и добавь `\usetheme{metropolis}`
(требует `metropolistheme` или `beamerthememetropolis`).

## Математика

- **Inline**: `$x^2 + 1$`, **display**: `\[ \int_0^\infty e^{-x^2}\,dx \]`.
- **Не используй `$$...$$`** — это устаревший plain TeX. Только `\[...\]` или
  environments `equation`, `align`, `gather`.
- **Нумерация**: `equation` нумеруется, `equation*` — нет. `align` — по строкам,
  `align*` — без номеров.
- **Теоремы**:

  ```latex
  \newtheorem{theorem}{Теорема}[section]
  \newtheorem{lemma}[theorem]{Лемма}
  \newtheorem{definition}[theorem]{Определение}
  \theoremstyle{remark}
  \newtheorem*{remark}{Замечание}
  ```

- **Доказательства**: `\begin{proof} ... \end{proof}` — автоматически ставит
  `∎` в конце.
- **Числовые множества**: `\mathbb{R}`, `\mathbb{Z}`, `\mathbb{N}`, `\mathbb{Q}`,
  `\mathbb{C}`. Кастомный shortcut: `\newcommand{\R}{\mathbb{R}}`.
- **Пробелы в формулах**: `\,` (тонкий), `\;` (средний), `\quad`, `\qquad`.
  В интегралах перед `dx`: `\int f(x)\,dx`.

## Таблицы

```latex
\begin{table}[h]
  \centering
  \begin{tabular}{lrr}
    \toprule
    Model & Success & Latency \\
    \midrule
    qwen3      & 96.7\%  & 16.8 s \\
    deepseek-v3 & 90.0\% & 29.7 s \\
    \bottomrule
  \end{tabular}
  \caption{Бенчмарк}
  \label{tab:bench}
\end{table}
```

`\toprule`/`\midrule`/`\bottomrule` из `booktabs` — всегда. Вертикальные линии
в таблицах (`|l|r|`) считаются bad taste.

## Рисунки

```latex
\begin{figure}[h]
  \centering
  \includegraphics[width=0.7\linewidth]{figures/plot.pdf}
  \caption{Описание}
  \label{fig:plot}
\end{figure}
```

- Предпочитай **PDF** для векторных графиков (matplotlib `savefig('plot.pdf')`).
- PNG — для растров (скриншоты).
- Никогда не используй JPEG для научных графиков.

## Ссылки

- `\label{sec:intro}` + `\ref{sec:intro}` — секции
- `\label{thm:main}` + `\ref{thm:main}` — теоремы
- `\label{eq:gauss}` + `\eqref{eq:gauss}` — формулы (круглые скобки)
- `\cite{key}` + `\usepackage{biblatex}` с `.bib` файлом — литература
- `\url{https://...}` / `\href{url}{text}` — гиперссылки

## Компиляция — закрытый цикл

**После записи `.tex` файла ОБЯЗАТЕЛЬНО запусти компиляцию и проверь результат.**

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

Если используешь `biblatex` / ссылки:

```bash
pdflatex main.tex && biber main && pdflatex main.tex && pdflatex main.tex
```

(Дважды в конце чтобы ссылки разрешились.)

Анализ вывода:

- **Errors** (`! ` в начале строки) — падаем, правим, перекомпилируем.
- **Undefined references** (`LaTeX Warning: Reference 'xxx' undefined`) —
  нормально на первом прогоне, исчезнет после второго.
- **Overfull hbox** — текст вылезает за поля. Минор, но стоит посмотреть.
- **Missing $** — забыл math mode. Оберни `$...$`.

Если `pdflatex` не установлен на системе — скажи пользователю одну фразу
(`sudo apt install texlive-latex-recommended texlive-fonts-recommended`).
Не пытайся ставить полный texlive-full сам — это 5 GB.

## Anti-patterns (не делай)

- Не используй `\begin{center}...\end{center}` для выравнивания — используй
  `\centering` внутри окружений.
- Не делай `\\` в обычном тексте для переноса — это плохой стиль. Для новых
  абзацев пустую строку.
- Не комбинируй `\section` с ручной нумерацией — LaTeX сам нумерует.
- Не пиши формулы текстом (`x^2 + 1`) — это читается ужасно. Либо `$x^2 + 1$`,
  либо display mode.
- Не забывай про `~` (неразрывный пробел) перед ссылками: `Theorem~\ref{thm:x}`.
