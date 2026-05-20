# Changelog

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
