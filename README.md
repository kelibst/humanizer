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

- **Ollama** (https://ollama.com) — required if you use the local backend. `humanize doctor` will tell you if it is missing.
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

## Run the interactive TUI

```bash
humanize          # opens the full-screen Textual app
```

With no subcommand, `humanize` boots a Textual app with five tabs across the top: **Profiles**, **Check**, **Transform**, **Grammar**, **Settings**, plus a **Home** landing screen. The Check tab loads a file (or pasted text) and renders the AI-risk gauge with the top contributing features. The Transform tab runs the full pipeline with a live stage strip (`prescan → llm → determ → grammar → postscan`), a side-by-side before/after diff, and a post-score gauge. The Grammar tab shows LanguageTool / Vale / proselint findings in a sortable table with intentional bluppers marked as suppressed. The Profiles tab browses every profile under `~/.config/humanizer/profiles/` plus the bundled default. The Settings tab shows backend status, the bridge daemon row, and the active default profile.

Global key bindings:

| Key | Action |
|---|---|
| `q` | quit |
| `?` | help overlay |
| `1`–`5` | jump to tab P / C / T / G / S |
| `Ctrl+R` | refresh / re-run last action on the current screen |
| `Ctrl+S` | run the primary action on the current screen (score, transform, save) |
| `Esc` | back out of the active dialog |

The flag CLI is unchanged; scripts that call `humanize check`, `humanize transform`, etc. keep working exactly as before.

## Run the local bridge daemon

```bash
humanize serve --port 9999
```

The bridge is a small FastAPI HTTPS daemon that exposes `humanize` to other clients on your machine — most notably the Google Docs sidebar (see below). On first launch it generates a self-signed cert at `~/.config/humanizer/certs/{cert.pem,key.pem}` and a per-session bearer token at `~/.config/humanizer/serve/token`, then prints both to stderr along with an OS-trust install one-liner so your browser stops complaining about the cert.

CORS is locked to two origins: `https://docs.google.com` and `https://script.google.com`. No `*`, no localhost — the daemon is loopback-only by design (`127.0.0.1` default host) and only the Google Docs sidebar is allowed to talk to it from the browser.

Smoke test the daemon with curl:

```bash
TOKEN=$(cat ~/.config/humanizer/serve/token)
curl -sk -H "Authorization: Bearer $TOKEN" https://localhost:9999/v1/health
# {"ok":true,"version":"1.2.0",
#  "backends_available":["ollama","anthropic","openai","gemini"],
#  "backends_configured":["ollama"]}
```

The daemon exposes five routes under `/v1/`: `health`, `profiles`, `score`, `transform`, `suggest`. See [`plan/BRIDGE_CONTRACT.md`](plan/BRIDGE_CONTRACT.md) for the full request/response shapes. To install the matching Google Docs sidebar, follow [`addons/google-docs/README.md`](addons/google-docs/README.md).

## Use a hosted API key (Anthropic / OpenAI / Gemini)

`humanize` ships with four backends: `ollama` (local, default), `anthropic`, `openai`, and `gemini`. The hosted backends each need an API key, picked up in this order:

1. Explicit `backend_config` in the active profile.
2. Environment variable: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.
3. `~/.config/humanizer/secrets.toml` (chmod 600 — `humanize` will warn if the file is world-readable).

Example `secrets.toml`:

```toml
[anthropic]
api_key = "sk-ant-..."

[openai]
api_key = "sk-..."

[gemini]
api_key = "AIza..."
```

Pin the backend in your profile YAML (one entry per profile under `~/.config/humanizer/profiles/<name>.yaml`):

```yaml
backend: anthropic       # one of: ollama | anthropic | openai | gemini
backend_config:
  model: claude-sonnet-4-6
  # host: https://api.anthropic.com    # optional override
```

Then run as usual — the profile pins the backend and model:

```bash
humanize transform draft.md --profile akua -o out.md
```

`humanize doctor` reports which backends have keys configured and which are reachable.

## Install the Google Docs add-in

The `addons/google-docs/` directory contains an Apps Script project that adds **Score**, **Rewrite**, and **Suggest 3** buttons to a Google Doc sidebar, talking to your local `humanize serve` daemon over loopback HTTPS. Full installation instructions live in [`addons/google-docs/README.md`](addons/google-docs/README.md); the short version:

```bash
humanize serve --port 9999                         # leave this running
cd addons/google-docs
npm install -g @google/clasp && clasp login
clasp create --type docs --title "Humanizer (dev)"
clasp push
```

Then open the Doc, run **Extensions → Apps Script → Run `onOpen`** once to register the menu, and the **Humanizer** menu appears. Open the sidebar, paste the bearer token from `~/.config/humanizer/serve/token` into the Settings panel, and you're set.

## Build a standalone binary

To ship `humanize` to colleagues who do not have Python installed, build a
single-file Linux binary with PyInstaller:

```bash
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller packaging/pyinstaller.spec --clean --noconfirm
# binary at dist/humanize
```

The bundled binary embeds the default Ghanaian profile, the LLM-favoured
vocabulary list, the Vale style folder, the Textual TUI assets, and the
FastAPI / hosted-SDK runtimes. External tools (Ollama, Java for
LanguageTool, the `vale` binary) are still required on the target machine.

The v1.2 binary is larger than the v1.0/v1.1 21 MB baseline (expect roughly
30–50 MB) because the bundle now also carries Textual, FastAPI + Uvicorn,
and the three hosted-LLM SDKs (Anthropic, OpenAI, Google Generative AI).
The Google Docs add-in under `addons/google-docs/` is **not** bundled — it
ships as a separate Apps Script project per the section above.

## Status

v1.2, beta. See [PLAN](https://github.com/keli-booster/humanizer/blob/main/PLAN.md) for milestones.

## License

MIT.
