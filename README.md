# humanizer

> Rewrite your academic essays to pass AI detectors — in 30 seconds.

## Quick Start (3 steps)

1. **Install** (Linux / macOS):
   ```bash
   curl -fsSL https://github.com/kelibst/humanizer/releases/latest/download/install.sh | bash
   ```
   *(restarts your terminal if the PATH changed)*

2. **Open the app**:
   ```bash
   humanize
   ```

3. **Press `T`, type the path to your essay, press `Ctrl+S`.**

That's it. Your file is rewritten. The original is unchanged.

---

## Supports .docx and .md files

Pass any `.docx` or `.md` file — the app reads it, rewrites the body text, and writes a new file alongside the original (e.g. `MyEssay_clean.docx`).

## What it does

humanizer runs your text through a local AI model (Gemma 3, on your machine — nothing leaves your computer) combined with a set of deterministic edits that make the prose look genuinely human: varying sentence length, swapping AI-favoured vocabulary, injecting the subtle imperfections real writers produce. It scores the text before and after so you can see exactly how much the risk dropped.

## Advanced: flag CLI

All operations are also available as command-line flags for scripting:

```bash
# Score a document for AI-detection risk
humanize check draft.md

# Score with a breakdown of what's driving the risk
humanize check draft.md --why

# Rewrite a document (full pipeline)
humanize transform draft.md -o draft.humanized.md

# Rewrite a .docx file
humanize transform MyEssay.docx -o MyEssay_clean.docx

# Rewrite using only the deterministic stage (no Ollama needed)
humanize transform draft.md --stages prescan,determ,postscan -o out.md

# Grammar pass only
humanize grammar draft.md

# Check that Ollama and the AI model are ready
humanize doctor

# Start the local bridge daemon (for the Google Docs add-in)
humanize serve --port 9999
```

Global TUI key bindings:

| Key | Action |
|---|---|
| `q` | quit |
| `?` | help overlay |
| `1`–`5` | jump to tab Profiles / Check / Transform / Grammar / Settings |
| `Ctrl+S` | run the primary action on the current screen |
| `Ctrl+R` | refresh / re-run |
| `Esc` | back out of the active dialog |

## Use a hosted API key (Anthropic / OpenAI / Gemini)

humanizer ships four backends: `ollama` (local, default), `anthropic`, `openai`, and `gemini`. To use a hosted backend, add your key to `~/.config/humanizer/secrets.toml`:

```toml
[anthropic]
api_key = "sk-ant-..."
```

Then pin the backend in your profile YAML:

```yaml
backend: anthropic
backend_config:
  model: claude-sonnet-4-6
```

Run `humanize doctor` to confirm which backends are configured.

## Sharing with a friend

Send them the install command above. It works on any Linux or macOS machine with no prior setup.

## Requirements

- Linux (x86\_64 / arm64) or macOS (Apple Silicon / Intel)
- ~2 GB disk space for the AI model (downloaded automatically on first install)
- No Python, no package manager

## Monetization / Support

Support the project and get the latest binary: [Gumroad — coming soon](https://gumroad.com)

## License

MIT.
