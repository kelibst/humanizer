# humanizer v1.2

## What's new

**One-command install.** A single `curl | bash` now sets up Ollama, downloads the AI model, and drops the binary in `~/.local/bin/` — no Python, no package manager required.

**Full-screen TUI.** Run `humanize` with no arguments to open an interactive app. Navigate with number keys, score a document on the Check tab, run the full rewrite pipeline on the Transform tab, and watch the AI-risk gauge drop in real time.

**`.docx` support.** Pass a Word document directly — `humanize transform MyEssay.docx -o MyEssay_clean.docx` reads the body text, rewrites it, and writes back a new `.docx` with heading structure preserved.

**Multi-backend support.** In addition to local Ollama (default), you can now configure Anthropic, OpenAI, or Gemini as the rewrite backend. Set your API key in `~/.config/humanizer/secrets.toml` and pin the backend in your profile YAML.

**Google Docs add-in.** A sidebar for Google Docs exposes Score, Rewrite, and Suggest 3 buttons backed by a local HTTPS bridge daemon (`humanize serve`). See `addons/google-docs/README.md` for the setup recipe.

---

## Install

1. **Install** (Linux / macOS):
   ```bash
   curl -fsSL https://github.com/YOUR_REPO/humanizer/releases/latest/download/install.sh | bash
   ```

2. **Open the app**:
   ```bash
   humanize
   ```

3. **Press `T`, type the path to your essay, press `Ctrl+S`.**

Your file is rewritten. The original is unchanged.

---

## System requirements

- Linux (x86\_64 or arm64) or macOS (Apple Silicon or Intel)
- ~2 GB free disk for the AI model (downloaded automatically)
- No Python, no package manager

---

## Full documentation

See the [README](https://github.com/YOUR_REPO/humanizer#readme) for the complete flag CLI reference, multi-backend setup, Google Docs add-in instructions, and advanced options.
