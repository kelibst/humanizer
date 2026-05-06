# Humanizer — VS Code Extension

Rewrite academic markdown to lower AI-detection risk, score documents in real time, manage citations, and export to `.docx` — all from inside VS Code.

Pairs with the `humanize` CLI (installed separately). The extension talks to a local daemon you start with one command.

---

## Quick start

1. **Install the CLI** (if not already done):
   ```bash
   pip install sis-caro-humanizer
   # or use the one-file binary from the release page
   ```

2. **Start the daemon** — open the Command Palette (`Ctrl+Shift+P`) and run:
   ```
   Humanizer: Start Humanizer Daemon
   ```
   This runs `humanize serve` in a terminal on `https://localhost:9999`. The extension reads the auth token from `~/.config/humanizer/serve/token` automatically — paste it into the `humanizer.token` setting if prompted.

3. **Open a Markdown file.** The sidebar panel appears in the Activity Bar (shield icon).

4. **Score → Rewrite → Export.**

---

## Features

### AI-risk scoring

The status bar shows a live score (LOW / MEDIUM / HIGH) for the active `.md` file. Scores update on save and after every rewrite. Click the score badge to force a refresh.

A breakdown of the six contributing features (vocabulary density, burstiness, punctuation signature, triple-list rate, topic-sentence perfection, hedge-formality skew) is shown in the sidebar.

### Rewriting

| Command | What it does |
|---|---|
| **Rewrite Selection** | Rewrites only the highlighted text and replaces it in place |
| **Rewrite Section** | Rewrites the section at the cursor (headed by the nearest `##`) |
| **Rewrite All Sections** | Iterates every section in the document sequentially |

Toggle **Include LLM** in the sidebar to add a Gemma/Ollama pass on top of the deterministic transforms. Deterministic-only mode runs in ~30 ms with no Ollama required.

### Export to .docx

**Humanizer: Export to .docx** opens a file picker so you can choose any `.md` file (not just the active editor). The output `<stem>_humanized.docx` is saved next to the source file and revealed in the OS file manager.

Heading levels (`#`, `##`, `###`) map to Word heading styles. Bold and italic inline markers are preserved as styled runs. If the document has a `## References` section, APA entries get Word bookmarks and in-text citations become internal hyperlinks.

### Citation management

The **References panel** in the sidebar lists all citations found in the document. Use it to:
- Add, edit, or delete reference entries
- Import a BibTeX file (`Humanizer: Import BibTeX`)
- Export references to BibTeX (`Humanizer: Export BibTeX`)
- Resolve orphaned citations (`Humanizer: Resolve All Orphan Citations`)
- Insert a formatted citation at the cursor (`Humanizer: Insert Citation`)

### Research panels

Opened via the sidebar or `Humanizer: Open Research Dashboard`:
- **Outline** — heading hierarchy with completeness rings
- **Readability** — Flesch–Kincaid, sentence-length distribution
- **Checklist** — section-level to-do badges

### Import lecturer review

After a lecturer returns a reviewed `.docx` with tracked changes and comments:

1. Run `Humanizer: Import Lecturer Review`
2. Pick the `.docx` file
3. The extension accepts all tracked changes, shows a diff against your current draft, and surfaces the reviewer's comments

---

## Commands

All commands are accessible via the Command Palette (`Ctrl+Shift+P`, type `Humanizer`) or the **Humanizer Actions…** quick-pick (`Ctrl+Shift+P` → `Humanizer: Humanizer Actions…`).

| Command | Description |
|---|---|
| Start Humanizer Daemon | Launch `humanize serve` in a terminal (skips if already running) |
| Score File | Compute AI-risk score for the active file |
| Rewrite Selection | Rewrite selected text |
| Suggest 3 for Selection | Get three candidate rewrites for the selection |
| Rewrite Section | Rewrite the section at the cursor |
| Rewrite All Sections | Rewrite every section sequentially |
| Export to .docx | Pick a `.md` file and export a humanized Word document |
| Import Lecturer Review | Accept tracked changes from a reviewed `.docx` |
| Insert Citation | Pick a reference and insert it at the cursor |
| Open Research Dashboard | Open the analytics panel |
| Import BibTeX | Load references from a `.bib` file |
| Export BibTeX | Save the reference list as `.bib` |
| Resolve All Orphan Citations | Find and fix unmatched in-text citations |
| Show Welcome | Re-open the onboarding cards |

---

## Settings

| Setting | Default | Description |
|---|---|---|
| `humanizer.daemonUrl` | `https://localhost:9999` | URL of the running daemon |
| `humanizer.token` | _(empty)_ | Bearer token — copy from `~/.config/humanizer/serve/token` |
| `humanizer.profile` | `default_ghanaian` | Voice profile name (must exist in `~/.config/humanizer/profiles/`) |
| `humanizer.backend` | `ollama` | LLM backend (`ollama`, `gemini`, or `openai`) |
| `humanizer.binaryPath` | `humanize` | Path to the `humanize` binary if not on PATH |
| `humanizer.autoScore` | `true` | Score the active file on save and update the status bar |
| `humanizer.includeLlm` | `false` | Include the LLM stage in transforms by default |
| `humanizer.idleScore` | `true` | Refresh research panels on save |

Open all settings at once: `Ctrl+Shift+P` → `Humanizer: Open Humanizer Settings`.

---

## Multiple VS Code windows

The daemon is a single process shared across all windows. Only the first **Start Humanizer Daemon** call actually starts a process — subsequent calls from other windows detect the running daemon and do nothing. All windows connect to the same `humanizer.daemonUrl`.

---

## Requirements

| Dependency | Required | Notes |
|---|---|---|
| `humanize` CLI | Yes | `pip install sis-caro-humanizer` or download the binary |
| Ollama + gemma3:4b | For LLM stage | `ollama pull gemma3:4b`; not needed for deterministic-only |
| Java 17+ | For grammar stage | LanguageTool; the stage is skipped if absent |
| `python-docx` | For `.docx` export | Installed automatically with the Python package |

---

## Reloading and reinstalling

### Reload the extension window (fastest — no reinstall needed)

Use this after any settings change or when the extension stops responding:

```
Ctrl+Shift+P → Developer: Reload Window
```

### Restart the daemon only

If the daemon process crashed or you changed the port:

1. Kill the old terminal: click the trash icon on the **Humanizer Daemon** terminal.
2. Run `Humanizer: Start Humanizer Daemon` again.
3. Wait for `Application startup complete` in the terminal before issuing commands.

### Reinstall the extension from source

Use this after pulling code changes or when `make extension` is needed:

```bash
cd /path/to/humanizer
make extension
# Then reload VS Code:
# Ctrl+Shift+P → Developer: Reload Window
```

`make extension` compiles the TypeScript, packages a `.vsix`, uninstalls the old version, installs the new one, and prints a reminder to reload.

### Install manually from a `.vsix` file

If you have a pre-built `humanizer.vsix`:

1. Open VS Code.
2. `Ctrl+Shift+P` → `Extensions: Install from VSIX…`
3. Pick the `.vsix` file.
4. Reload the window when prompted.

Or from the terminal:
```bash
code --install-extension humanizer.vsix
```

### Full reset (extension + daemon)

If something is deeply broken:

```bash
# 1. Kill any running daemon
pkill -f "humanize serve" 2>/dev/null || true

# 2. Uninstall the extension
code --uninstall-extension sis-caro-humanizer

# 3. Reload VS Code window, then reinstall
make extension

# 4. Restart the daemon from the Command Palette
# Humanizer: Start Humanizer Daemon
```

---

## Troubleshooting

**Status bar shows "daemon not running"**
Run `Humanizer: Start Humanizer Daemon` and wait for `Application startup complete` in the terminal, then retry.

**Token error (401)**
Copy the token from `~/.config/humanizer/serve/token` into `humanizer.token` in VS Code settings.

**LLM stage fails (502)**
Ensure Ollama is running (`ollama serve`) and the model is pulled (`ollama list`). Or untick **Include LLM** to use deterministic-only mode.

**Extension not responding after install**
Reload the window: `Ctrl+Shift+P` → `Developer: Reload Window`.
