# Humanizer v1.2 — End-to-End Walkthrough

This is the single document to follow if you want to see every piece of v1.2 working at the same time: the multi-backend pipeline, the Textual TUI, the local bridge daemon, the Google Docs add-in, and the three new voice profiles (`ioannidis`, `greenhalgh`, `krieger`).

Tick the phases off in order. Each phase is self-contained — you can stop after any phase and still have a working subset.

**Total time, first run:** ~30 minutes (most of it spent in Phase 5 doing the one-time Google add-in install). Subsequent runs: under 60 seconds to start the daemon and open the sidebar.

---

## Pre-flight — what you need installed

Run this checklist once. If anything is missing, install it before continuing.

| Need | Why | Check |
|---|---|---|
| Python 3.12 venv at `.venv` | runs the humanizer | `.venv/bin/python --version` |
| Ollama running locally | default LLM backend | `curl -s localhost:11434/api/tags \| head -c 80 && echo` |
| `gemma3:4b` pulled | the default model | `ollama list \| grep gemma3` |
| Node.js + npm | needed for `clasp` (Google Apps Script CLI) | `node --version && npm --version` |
| `clasp` (Google's Apps Script CLI) | sideloads the add-in | `clasp --version` (install with `npm install -g @google/clasp` if missing) |
| A Google account | to host the add-in | one you can log into in a browser |
| (Optional) Anthropic / OpenAI / Gemini API key | hosted-LLM rewrites | env var or `~/.config/humanizer/secrets.toml` |

**Quick health check:**

```bash
cd /home/kelib/Desktop/moreprojects/humanizer
.venv/bin/humanize doctor
```

You want green ticks for **Ollama daemon** and **gemma3:4b**. The other three rows (Java, vale, proselint) all gate the optional grammar pass — if any are MISSING, fix them with the recipe in the next section. The pipeline still works without them; only the `humanize grammar` subcommand and the TUI's Grammar tab will degrade.

---

## Pre-flight fixes — making `humanize doctor` go fully green (5–10 min)

Run these only if the corresponding row showed **MISSING**. All three are independent; install whichever you need.

### Fix 1: `proselint` (and `language-tool-python`) — Python deps in the venv

If the doctor row reads `proselint MISSING — import failed: No module named 'proselint'`, the venv is missing one or both grammar deps. Reinstall:

```bash
cd /home/kelib/Desktop/moreprojects/humanizer
.venv/bin/pip install "proselint>=0.14" "language-tool-python>=2.8"
.venv/bin/pip check                # should print: No broken requirements found.
.venv/bin/humanize doctor          # proselint row should now read OK
```

(`language-tool-python` is the Python wrapper — it doesn't fix the Java row, but the `humanize grammar` subcommand will fail at import time without it. Better to install both in one shot.)

If you ever rebuild the venv from scratch, `pip install -e ".[dev]"` should pull both. The regression above happened because the v1.2 dependency bump didn't re-resolve previously-installed deps, leaving these two stranded.

### Fix 2: Java (LanguageTool runtime)

LanguageTool is a JAR; it needs a JRE on `PATH`. On **deepin / Debian / Ubuntu**:

```bash
sudo apt update
sudo apt install -y default-jre        # ~80 MB; installs OpenJDK 17+ JRE
java --version                         # confirm
.venv/bin/humanize doctor              # Java row should now read OK
```

On **Fedora / RHEL**: `sudo dnf install -y java-17-openjdk-headless`. On **macOS**: `brew install openjdk@17`. On **Windows**: download the OpenJDK MSI from [adoptium.net](https://adoptium.net) and run it.

The first time `humanize grammar` runs, `language-tool-python` downloads ~250 MB of language-model JARs into `~/.cache/language_tool_python/`. That happens once.

### Fix 3: Vale (style linter)

Vale is a Go binary, **not** in deepin's apt repos. Install the upstream release tarball into `~/.local/bin/`.

> **Note (2026):** the upstream repo moved from `errata-ai/vale` → `vale-cli/vale`. The old URL still 301-redirects, but the canonical URL avoids redirect-chain timeouts. Use the canonical URL below.

```bash
# Pick the latest tag from https://github.com/vale-cli/vale/releases
VALE_VERSION="3.14.1"        # current as of 2026-05; bump if you want newer
mkdir -p ~/.local/bin
cd /tmp
curl -fL --max-time 180 --connect-timeout 10 \
  -o vale.tar.gz \
  "https://github.com/vale-cli/vale/releases/download/v${VALE_VERSION}/vale_${VALE_VERSION}_Linux_64-bit.tar.gz"
tar xzf vale.tar.gz
mv vale ~/.local/bin/
chmod +x ~/.local/bin/vale
rm -f vale.tar.gz README.md LICENSE 2>/dev/null
```

**Make sure `~/.local/bin` is on `PATH`.** This trips zsh users on deepin:
- `~/.profile` adds it automatically — but only for **login** shells (TTY login, `bash -l`).
- `~/.zshrc` ships with the equivalent line **commented out**, so a fresh **zsh** terminal won't see `vale`.

Check first:
```bash
echo "$PATH" | tr ':' '\n' | grep -c "$HOME/.local/bin"
```

If the answer is `0`, uncomment (or add) the PATH line in your shell rc:
```bash
# zsh:
sed -i 's|^# export PATH=$HOME/bin:$HOME/.local/bin|export PATH=$HOME/bin:$HOME/.local/bin|' ~/.zshrc
# bash:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# Reload your shell (or open a new terminal):
exec $SHELL
```

Confirm:
```bash
which vale                              # /home/<you>/.local/bin/vale
vale --version
cd /home/kelib/Desktop/moreprojects/humanizer
.venv/bin/humanize doctor               # vale row should now read OK
```

The Sis-Caro Vale style folder is bundled in the repo at `vale_styles/` — you don't need to install rules separately. The bridge daemon and the binary both find it via `config.bundle_dir()`.

### Confirm everything green

```bash
.venv/bin/humanize doctor
```

Expected:

```
┃ component           ┃ status  ┃ note                                ┃
┃ Ollama daemon       │ OK      │ http://localhost:11434              ┃
┃ model gemma3:4b     │ OK      │ ...                                 ┃
┃ Java (LanguageTool) │ OK      │ ...                                 ┃
┃ vale binary         │ OK      │ ...                                 ┃
┃ proselint           │ OK      │ import OK                           ┃
```

If any row is still MISSING, re-read the corresponding fix above. Phase 1 onward will work either way — the grammar pass just degrades to "tool reports zero issues" rather than failing.

---

## Phase 1 — CLI sanity (3 min)

Goal: prove the source-tree CLI works and the three new profiles are discoverable.

```bash
cd /home/kelib/Desktop/moreprojects/humanizer

# 1. List available profiles. You should see at least four:
#      default_ghanaian, ioannidis, greenhalgh, krieger
.venv/bin/humanize profile list

# 2. Show one profile's voice spec to confirm it parsed.
.venv/bin/humanize profile show ioannidis | head -30

# 3. Score the canonical AI-flavoured paragraph.
#    Expected: AI-risk score around 0.745, band HIGH.
.venv/bin/humanize check /tmp/ai_sample.md --why
```

If `/tmp/ai_sample.md` does not exist, create one:

```bash
cat > /tmp/ai_sample.md <<'EOF'
AI loves to delve into multifaceted, intricate, and nuanced topics — it really does.
Furthermore, the navigated landscape of contemporary research presents a rich tapestry
of insights. Moreover, leveraging holistic frameworks allows scholars to embark on
robust, rigorous, and reproducible inquiries. In conclusion, the paradigm shift
demands that we foster, nurture, and sustain a culture of intellectual humility.
EOF
```

**Verify before moving on:** the score panel renders, the band is HIGH (≥ 0.67), and the top contributor is `llm_vocab_density` or `burstiness_deficit`.

---

## Phase 2 — TUI tour (3 min)

Goal: see the full-screen app you can hand to someone non-technical.

```bash
.venv/bin/humanize        # bare command, no args, no flags
```

What to do inside:

1. **Home screen.** You see five tabs in the top bar (`P C T G S`) and a six-item menu in the body. Footer shows your current profile + backend.
2. Press `c` (or `2`). **Check screen** opens.
3. Type `/tmp/ai_sample.md` into the input field, press `Ctrl+S`. The score gauge fills to ~0.745 in the red HIGH band; three contributors appear under the gauge.
4. Press `t` (or `3`). **Transform screen** opens.
5. Same file. Tick stages: `prescan`, `determ`, `postscan` (leave `llm` and `grammar` off for a fast deterministic-only pass). Press `Ctrl+S`. Watch the **stage strip** animate `⏺ → ⏳ → ✓` and the diff render below.
6. Note the post-score: **0.31 LOW** (or thereabouts). The deterministic pass alone takes ~30 ms.
7. Press `5` (or `s`). **Settings screen** shows the backend picker, the bridge daemon row (currently stopped), and your default profile.
8. Press `q` to quit.

**Verify before moving on:** all five tabs reachable via digits; no crashes; the diff actually shows changes (em-dashes gone, vocab swaps applied, comma splices, etc.).

---

## Phase 3 — Try the three voice profiles back-to-back (5 min)

Goal: see how each new profile shapes the rewrite differently.

Use the same input three times so the only variable is the profile.

```bash
cd /home/kelib/Desktop/moreprojects/humanizer

INPUT=/tmp/ai_sample.md

.venv/bin/humanize transform "$INPUT" --profile ioannidis  --stages prescan,determ,postscan -o /tmp/out_io.md
.venv/bin/humanize transform "$INPUT" --profile greenhalgh --stages prescan,determ,postscan -o /tmp/out_gh.md
.venv/bin/humanize transform "$INPUT" --profile krieger    --stages prescan,determ,postscan -o /tmp/out_nk.md

echo "=== Ioannidis (short, declarative, however-heavy) ==="
cat /tmp/out_io.md
echo
echo "=== Greenhalgh (clinical-narrative, moderate length) ==="
cat /tmp/out_gh.md
echo
echo "=== Krieger (long, parenthetical-rich, social-epi) ==="
cat /tmp/out_nk.md
```

The deterministic stage doesn't yet differentiate sentence-shape between profiles (that's an LLM-stage job), but you'll already see different vocab swaps and blupper rates because each profile's `vocabulary` and `blupper_probabilities` differ.

**To see the full voice difference**, run the LLM stage (Ollama needs to be up):

```bash
.venv/bin/humanize transform "$INPUT" --profile krieger -o /tmp/out_nk_llm.md
diff /tmp/out_nk.md /tmp/out_nk_llm.md | head -40
```

---

## Phase 4 — Hosted backend (optional, 2 min)

Skip this phase if you're staying on Ollama. Otherwise pick one provider.

```bash
# Pick one. The CLI reads env vars; persistence is at ~/.config/humanizer/secrets.toml.
export ANTHROPIC_API_KEY="sk-ant-..."
# export OPENAI_API_KEY="sk-..."
# export GEMINI_API_KEY="..."

# Confirm the backend is recognised:
.venv/bin/python -c "from sis_caro_humanizer.backends import list_available; print(list_available())"
# Expected: ['ollama', 'anthropic']  (or whichever you set the key for)

# Run a transform through Anthropic. (~5–15 s for a paragraph.)
.venv/bin/humanize transform /tmp/ai_sample.md \
    --profile greenhalgh \
    --model claude-sonnet-4-6 \
    -o /tmp/out_anthropic.md
# The --backend flag is implicit: the profile's `backend` field can pin it,
# OR you set it via the bridge / TUI Settings, OR the env-var path picks it.
```

---

## Phase 5 — Bridge daemon + Google Docs add-in (one-time, 15 min)

This is the install-once-then-forget part. Three sub-steps: (5a) start the daemon, (5b) trust the cert in your browser, (5c) sideload the add-in.

### 5a. Start the bridge daemon

```bash
cd /home/kelib/Desktop/moreprojects/humanizer
.venv/bin/humanize serve --port 9999
```

Leave this terminal running. It prints a banner like:

```
humanize-bridge v1.2.0
  listening on  https://127.0.0.1:9999
  bearer token  ytag9bO2ilEZRv4k9brHfzfswfUJEyrUBpjbyFmc3hc
  token file    /home/kelib/.config/humanizer/serve/token
  cert          /home/kelib/.config/humanizer/certs/cert.pem
  ...
```

**Copy the bearer token** (or read it later from the token file — same value).

### 5b. Trust the self-signed cert in your browser

The sidebar runs at `https://docs.google.com` and will refuse to call `https://localhost:9999` unless that cert is trusted. Easiest path:

1. In the **same Chrome/Firefox profile** you use Google Docs with, visit:
   ```
   https://localhost:9999/v1/health
   ```
2. The browser will warn "Your connection is not private". Click **Advanced → Proceed to localhost (unsafe)**.
3. You should now see a JSON blob: `{"error":"unauthorised", ...}`. That's expected — you didn't send the bearer header. **The 401 means the cert is now trusted for this browser.**

If you want the cert trusted system-wide (for `curl` etc.), run the one-liner the daemon printed:
```bash
sudo cp ~/.config/humanizer/certs/cert.pem /usr/local/share/ca-certificates/humanizer-bridge.crt && sudo update-ca-certificates
```

### 5c. Sideload the Google Docs add-in via clasp

```bash
# In a NEW terminal (leave the daemon running):
cd /home/kelib/Desktop/moreprojects/humanizer/addons/google-docs

# 1. Authenticate clasp (opens a browser tab; one-time).
clasp login

# 2. Create a new Apps Script project bound to a doc. Pick any title.
clasp create --type docs --title "Humanizer (dev)"
# This creates a new Google Doc + bound script project. clasp prints the
# scriptId; it is also written into .clasp.json automatically.

# !!! 2a. clasp create OVERWRITES appsscript.json with a default stub
#         (no oauthScopes) — restore the committed version:
git checkout HEAD -- appsscript.json
cat appsscript.json   # confirm oauthScopes are back

# !!! 2b. clasp v3 has two file-naming gotchas with Apps Script:
#  - .css files are not tracked by clasp's default extensions
#  - same-basename files of different types collide on push
#    (e.g. sidebar.html + sidebar.js both want to be "sidebar")
#
# The standard Apps Script fix is to rename CSS and companion JS files
# to *.html so clasp pushes them as HTML templates. Apps Script stores
# them under their leading basename, so include('sidebar.css') still
# resolves. Apply once:
mv sidebar.css     sidebar.css.html  2>/dev/null
mv sidebar.js      sidebar.js.html   2>/dev/null
mv settings.js     settings.js.html  2>/dev/null

# 3. Push your local source up to that project.
clasp push --force
# Expected output: "Pushed 7 files." with appsscript.json, Code.gs,
# settings.html, settings.js.html, sidebar.css.html, sidebar.html,
# sidebar.js.html.

# 4. Open the bound doc in your browser.
#    NOTE: `clasp` v3 split the old `clasp open` into three commands.
clasp open-container       # opens the bound Google Doc
# clasp open-script         # opens the Apps Script IDE
# clasp open-web-app        # opens a deployed web app

# 5. In the Apps Script editor that just opened (or via Extensions →
#    Apps Script → Editor inside the doc):
#    a. Click "Code.gs" in the FILES list on the left.
#    b. The function dropdown next to ▶ Run now populates. Pick `onOpen`.
#    c. Click ▶ Run. Google will prompt for authorisation:
#       Review permissions → choose your account →
#       "Google hasn't verified this app" → Advanced → Go to <name> (unsafe) →
#       Allow each of the three scopes (documents, container UI, external).
#    Note: if Files list shows only "Untitled.gs" or empty Code.gs, the push
#    didn't land — refresh the editor tab; if still empty, re-run `clasp push --force`.

# 6. Reload the bound Google Doc tab. A new top-level "Humanizer" menu
#    appears in the doc's menu bar.
```

**`clasp` v3 breaking changes** (you have v3.3.0 installed via bun):

| What you want | v2 command (now broken) | v3 command |
|---|---|---|
| Open the bound doc | `clasp open` | `clasp open-container` |
| Open the Apps Script IDE | `clasp open` | `clasp open-script` |
| Open API console | `clasp open --creds` | `clasp open-api-console` |
| Open a deployed web app | `clasp open --webapp` | `clasp open-web-app` |

`clasp create`, `clasp push`, `clasp pull`, `clasp login` still work as documented (they have v3 aliases for the renamed `create-script`, `clone-script`, `delete-script` underneath).

If `clasp create` complains your account doesn't have the Apps Script API enabled, follow the link it prints — flip the toggle at https://script.google.com/home/usersettings to **Google Apps Script API: ON**, then re-run.

### 5d. Configure the sidebar

1. In the doc: **Humanizer → Open Humanizer sidebar**. The sidebar loads on the right.
2. Click the **⚙ Settings cog** at the top of the sidebar.
3. Fill in:

   | Field | Value |
   |---|---|
   | Base URL | `https://localhost:9999` |
   | Bearer token | (paste the token from 5a) |
   | Profile | `ioannidis` (the dropdown auto-populates from `GET /v1/profiles` once URL+token are filled) |
   | Backend | `ollama` (or `anthropic` / `openai` / `gemini` if you did Phase 4) |
   | Model | leave blank to use the backend's default, or e.g. `claude-sonnet-4-6` |

4. Click **Save**. The sidebar reloads and shows the three action buttons.

---

## Phase 6 — Watch all three actions in Google Docs (5 min)

You're at the moment of truth.

1. **In your test Google Doc**, paste the AI-flavoured paragraph (same content as `/tmp/ai_sample.md`):

   > AI loves to delve into multifaceted, intricate, and nuanced topics — it really does. Furthermore, the navigated landscape of contemporary research presents a rich tapestry of insights. Moreover, leveraging holistic frameworks allows scholars to embark on robust, rigorous, and reproducible inquiries. In conclusion, the paradigm shift demands that we foster, nurture, and sustain a culture of intellectual humility.

2. **Select the entire paragraph.**

3. In the sidebar, click **Score**.
   - Expected: a coloured bar fills to ~0.745 in the **HIGH** red band, with a "why" expander listing `llm_vocab_density`, `punct_signature`, `triple_list_rate` as the top three contributors.

4. With the same selection still active, click **Rewrite**.
   - Expected: the selection is replaced inline with the rewritten paragraph (em-dashes gone, "delve" → "examine", "leverage" → "use", etc.). A second score bar appears showing the new score (~0.30 LOW). Total round-trip: ~50 ms (no LLM) or ~5–15 s (LLM on).
   - Tick the **Include LLM stage** checkbox first if you want a deeper rewrite via Ollama / Anthropic.

5. Paste the original paragraph again, select it, click **Suggest 3**.
   - Expected: three candidate cards appear in the sidebar, each with its own score and a "Use this" button. Pick one; the selection is replaced with that candidate.

---

## Phase 7 — A/B the three voice profiles inside the doc (3 min)

Now you can see why the three profiles matter.

1. In the sidebar Settings cog, change **Profile** to `greenhalgh`. Save.
2. Paste the AI paragraph again, select it, click **Rewrite (with LLM)**. Note the result.
3. Change **Profile** to `krieger`. Save. Repeat the same input + rewrite.
4. Change **Profile** to `ioannidis`. Save. Repeat.

Observe the differences:
- **Ioannidis** — short declaratives, frequent `however`, low parenthetical density.
- **Greenhalgh** — clinical-narrative, moderate length, more `which`-clauses.
- **Krieger** — long sentences, dense parentheticals, em-dashes preserved more often.

You're seeing one input → three distinct human voices, applied inside the document the user is actually writing in. **That's the v1.2 win.**

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Sidebar shows "Daemon unreachable" | cert not trusted, or daemon not running | redo Phase 5b (visit `https://localhost:9999/v1/health` in the SAME browser profile and accept the cert) |
| `Score` button returns "401 unauthorised" | wrong bearer token in Settings | `cat ~/.config/humanizer/serve/token` — paste that exact value |
| Sidebar shows "CORS blocked" in browser DevTools | daemon was started before the contract update | restart `humanize serve` (the CORS allowlist is set at startup) |
| `Rewrite` returns "502 backend_unavailable" | Ollama down or no API key for the configured backend | start Ollama (`ollama serve` in a new terminal) OR un-tick "Include LLM stage" to fall back to deterministic-only |
| `clasp push` complains about manifest scopes | your Google account hasn't authorised the Apps Script API | visit https://script.google.com/home/usersettings, flip API toggle ON, re-run `clasp push` |
| Sidebar selection-replace garbles paragraph structure | known v1.3 limitation (multi-element selections collapse) | for v1.2, work paragraph-by-paragraph; one paragraph selection at a time |
| TUI looks broken on a tiny terminal | < 80×24 minimum | resize terminal to at least 80×24 |
| `dist/humanize` (binary) missing the new subcommands | old v1.1 binary | rebuild via the recipe in `README.md` "Build a standalone binary" section |

---

## What you just demonstrated

If you ran every phase, you exercised:

- **Six humanize subcommands** (`doctor`, `profile list/show`, `check`, `transform`, `serve`)
- **Four LLM backends** (ollama by default; one of anthropic / openai / gemini if you did Phase 4)
- **The Textual TUI** (six screens, live progress, side-by-side diff)
- **The HTTPS bridge daemon** (TLS with self-signed cert, bearer-token auth, CORS allowlist for `docs.google.com`)
- **All five `/v1/*` routes** (`health`, `profiles`, `score`, `transform`, `suggest`)
- **The Google Docs sidebar** (three action buttons, settings dialog with `PropertiesService` per-user storage)
- **Three voice profiles** with materially different sentence-shape and punctuation signatures

That's the full v1.2 product.

---

## Where to look if you want more

- `README.md` — top-level user docs.
- `addons/google-docs/README.md` — add-in install reference.
- `plan/V1_2_ROADMAP.md` — full ownership matrix and decisions.
- `plan/BRIDGE_CONTRACT.md` — HTTP API contract (lock-step with the sidebar code).
- `plan/BACKEND_CONTRACT.md` — `Backend` protocol if you want to add a fifth provider.
- `plan/TUI_LAYOUT.md` — wireframes for every Textual screen.
- `STATE.md` — historical record: what every agent built, dated and signed.

If you want to extend v1.2 (a Word add-in, MCP connector, live-scoring sidebar, etc.), the plan files are the right place to start — they show how the existing scope was carved.
