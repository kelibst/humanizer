# humanize

A local CLI that rewrites academic text to read as a specific person, not a language model. It runs on your machine (Ollama + Gemma 3/4), captures your personal writing style as a YAML profile, and applies a multi-stage pipeline that beats stylometric AI detectors without flattening your meaning.

## Why

Most "humanizers" are paraphrasers. They swap synonyms and re-arrange clauses. Modern detectors (Turnitin, GPTZero, Pangram, Winston, 2025-2026) catch them because they fingerprint *style*: sentence-length variance, punctuation distribution, vocabulary frequency, paragraph shape, hedge formality. Beating those means writing in a real person's idiosyncratic voice, not just paraphrasing.

`humanize` does that by:

1. Building a profile of *your* writing from samples you provide.
2. Rewriting input through a local LLM with that profile in the system prompt.
3. Applying deterministic post-edits the LLM is too polished to make on its own (em-dash stripping, "less" for "fewer", "data shows", "as such" connectors, sentence-length anti-clustering, three-item-list breaking, dialect-specific quirks).
4. Running grammar checks (LanguageTool + Vale + proselint) that suppress warnings on your *intentional* bluppers.
5. Reporting an AI-risk score before and after so you can see the move.

## Install

```bash
pipx install sis-caro-humanizer
# or, from source:
pip install -e .[dev]
```

External dependencies the binary does not bundle:

- **Ollama** (https://ollama.com) — required. `humanize doctor` will tell you if it is missing.
- **Java 17+** — required for LanguageTool. Optional if you don't use the grammar stage.
- **Vale** (https://vale.sh) — optional. Skipped if not on PATH.

## Quick start

```bash
# 1. One-time setup check
humanize doctor

# 2. Build a profile from 5-10k words of your own writing
humanize profile create akua chapter1.md methodology.md essays/*.md

# 3. Score a document for AI-detection risk
humanize check draft.md

# 4. Rewrite a document in your voice
humanize transform draft.md --profile akua -o draft.humanized.md
```

## Build a standalone binary

To ship `humanize` to colleagues who do not have Python installed, build a
single-file Linux binary with PyInstaller:

```bash
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller packaging/pyinstaller.spec --clean --noconfirm
# binary at dist/humanize
```

The bundled binary embeds the default Ghanaian profile, the LLM-favoured
vocabulary list, and the Vale style folder. External tools (Ollama, Java for
LanguageTool, the `vale` binary) are still required on the target machine.

## Status

v0.1, alpha. See [PLAN](https://github.com/keli-booster/humanizer/blob/main/PLAN.md) for milestones.

## License

MIT.
