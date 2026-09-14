# Changelog

## v2.0.0 — 2026-09-14

**AI4Science** — second release. The agent is renamed from AI4Math and adapted
for the YSDA semester course «ИИ-ассистенты для исследователя. AI4Science»
(natural sciences). The GitHub repository keeps its address
`andkhalov/AI4Math`.

### Added

- Model switching inside a session by alias: `/model alice`,
  `/model qwen235`. Goose passes the model name as typed; the token proxy
  replaces a short name or slug with `gpt://<folder>/<slug>`.
- Aliases `alice` (`aliceai-llm/latest`) and `alice-flash`
  (`aliceai-llm-flash/latest`); command `ai4science models`; shared model
  catalogue `src/ai4science_models.py` with context windows from the Yandex AI
  Studio documentation (qwen 256k, deepseek 1M, gpt-oss and alice 128k,
  alice-flash 64k).
- README: in-session commands (`/model`, `/status`, `/compact`, …), model
  switching, uninstall instructions for macOS, Linux, WSL and Windows.

### Breaking changes

- Command `ai4math` → `ai4science` (`bin/ai4science`, `bin/ai4science.bat`,
  `bin/ai4science.py`, `bin/ai4science-mcp[.bat]`); symlink
  `~/.local/bin/ai4science`. An existing `ai4math` command on the system is
  not touched.
- MCP server `src/ai4math_mcp.py` → `src/ai4science_mcp.py`, extension name
  `ai4science`; recipe `recipes/ai4science.yaml`.
- Environment variables `AI4MATH_*` → `AI4SCIENCE_*`. Old names are still
  accepted as fallbacks.
- `.env` keys: `YANDEX_AI_API` → `YANDEX_CLOUD_API_KEY`; model selection by
  `YANDEX_CLOUD_MODEL` (alias or Yandex AI Studio slug) and
  `YANDEX_PLANNER_MODEL`. `YANDEX_QWEN`, `YANDEX_DEEPSEEK`, `YANDEX_GPTOOS`,
  `AI4MATH_MODEL` are no longer needed; `YANDEX_AI_API` and `AI4MATH_MODEL`
  are read as fallbacks.
- Token budget file: `~/.ai4science_budget.json`.

### Fixed

- `mcp` pinned to `<2`: `mcp` 2.x removed `mcp.server.fastmcp`, which broke
  fresh installs of 1.0.0.
- Default model `deepseek-v32/latest` is no longer served by Yandex AI Studio.
  New default: `qwen3.6-35b-a3b/latest`; `/plan` uses
  `qwen3-235b-a22b-fp8/latest`. Aliases: `qwen`, `qwen235`, `deepseek`
  (`deepseek-v4-flash`), `gptoss`, `junior` (`gpt-oss-20b`).
- Windows: the MCP extension is launched through `bin\ai4science-mcp.bat`;
  UTF-8 output in the token proxy.

### Changed

- Goose data (sessions, logs, input history) is stored in `<repo>/.goose`
  (`GOOSE_PATH_ROOT`): removing the agent folder removes all agent data, and a
  standalone Goose configuration is not touched. Goose telemetry is off by
  default (`GOOSE_TELEMETRY_ENABLED=false`); the first-run consent prompt is
  not shown.
- History compaction at ~45k tokens for every model of the catalogue, so that
  `/model` to a model with a smaller window does not overflow it.
  `GOOSE_CONTEXT_LIMIT` follows the documented window of the start model.
- In-session history compaction is `/compact` (`/summary` in the 1.x docs).
- Goose pinned to `v1.50.0` (was the moving `stable` channel); `setup.py`
  reinstalls Goose when the local binary differs from the pinned version.
- `setup.sh` checks system packages and delegates to `setup.py` (one
  implementation for all platforms). `setup.py` runs `doctor` at the end.
- Windows native installation is the primary Windows path: `setup.bat`
  finds Python 3.10+ (`python` or the `py` launcher, skipping the Microsoft
  Store stub), checks git, adds `<repo>\bin` to the user `PATH` (disable with
  `--no-path`) and prints the WSL2 fallback on failure.
- Wizard: non-interactive mode from `YANDEX_CLOUD_API_KEY` and
  `YANDEX_CLOUD_FOLDER` environment variables.
- `ai4science run` uses `goose run --no-session`.
- The agent reads the project contract file in the order `AGENT.md`,
  `AGENTS.md`, `CLAUDE.md`, `.cursorrules`.
- Dependencies `openai` and `python-dotenv` removed (not imported).
- CI: unit tests on Ubuntu, Windows and macOS; clean installation and
  `doctor` on all three; end-to-end Task A on Ubuntu and Windows when secrets
  are set.
- Removed course materials of the 2026 intensive from the repository
  (`docs/submission_guide.md`, peer-review section of the README) and the
  legacy bash entrypoint.

## v1.0.0 — 2026-05-20

First public release of **AI4Math** — an open-source CLI agent for AI-assisted mathematical research.

### What it is

A Claude-Code-style interactive CLI agent that combines an LLM session with tooling for the mathematician's workflow:

- **Inference-agnostic.** Any LLM backend can be plugged in; the agent does not hard-bind to a single provider.
- **Modular retriever substitution.** Context augmentation is decoupled from the inference loop; the user can swap retrievers. The default retriever provides Mathlib premise lookup through `scilibai.ru`.
- **Lean 4 proof verification.** Generated proofs are checkable end-to-end inside the session.
- **Auxiliary tools.** PDF reading and web search are exposed as MCP tools alongside retrieval and verification.

### Sessions and modes

- Interactive REPL with slash-commands: `/plan` for stepwise planning, `/mode` to switch approval mode on the fly, `/summary` for manual conversation compaction.
- Approval modes: `auto`, `smart_approve` (default for interactive), `approve`, `chat`.
- One-shot mode `ai4math run "<prompt>"` for scripts and CI.
- `ai4math doctor` for environment diagnostics.

### Platforms and CI

Linux (Ubuntu 22+, Debian 12+), macOS 13+ (Intel and Apple Silicon), Windows 10/11 (WSL2 recommended; native beta). Every push is verified on all three platforms via GitHub Actions.

### License

MIT.

### Citation

See `CITATION.cff` and `.zenodo.json`. The minted Zenodo DOI is assigned automatically when the GitHub release is published.
