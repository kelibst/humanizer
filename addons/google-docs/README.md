# Humanizer — Google Docs add-in

Apps Script sidebar that calls into the local `humanize serve` HTTPS daemon
(see `plan/BRIDGE_CONTRACT.md`). Three buttons: **Score**, **Rewrite**,
**Suggest 3** — same semantics as the CLI / TUI, just inside Google Docs.

## Layout (this folder)

```
addons/google-docs/
├── appsscript.json          OAuth scopes manifest
├── .clasp.json.example      template; copy to .clasp.json (gitignored)
├── .gitignore               keeps real .clasp.json out of git
├── Code.gs                  server-side: menu, getSelection, replaceSelection, get/setConfig
├── sidebar.html             main sidebar entry (templated; includes css + js inline)
├── sidebar.css              Material-ish styling, shared by sidebar + settings
├── sidebar.js               in-browser fetch() against the daemon
├── settings.html            modeless settings dialog
├── settings.js              writes config via google.script.run.setConfig
└── README.md                this file
```

## Why `fetch()` and not `UrlFetchApp`

Server-side `UrlFetchApp` runs on Google's servers, which cannot reach
`https://localhost:9999`. The sidebar therefore makes its HTTP requests
**from the browser** (the Apps Script iframe), and the daemon's CORS
allowlist (`https://docs.google.com`, `https://script.google.com`) lets
that request through. See `plan/BRIDGE_CONTRACT.md` Appendix A.

## One-time install (developer)

```bash
# 1. Install Google's clasp CLI (once per machine)
npm install -g @google/clasp
clasp login

# 2. Push this folder up as a brand-new bound script
cd addons/google-docs
clasp create --type docs --title "Humanizer (dev)"
clasp push
```

`clasp create` writes a real `.clasp.json` (gitignored) containing the
script ID. Future pushes are just `clasp push` from this directory.

For a personal Google Workspace, `clasp` will create a standalone Apps
Script project; you bind it to a doc by opening the script editor from
**Extensions → Apps Script** in any doc, then pasting the project ID, or
by deploying it as an editor add-in (out of scope for v1).

## Manual test recipe (test-of-record)

This is the verification gate for v1.2 round 2 — see
`plan/AGENT_A_BRIEF_V1_2_ROUND2.md` §"Manual test recipe".

1. **Start the daemon** in a terminal:
   ```bash
   humanize serve --port 9999
   ```
   Copy the bearer token printed to stderr.

2. **Push the add-in** (first time only):
   ```bash
   cd addons/google-docs
   clasp create --type docs --title "Humanizer (dev)"
   clasp push
   ```
   On subsequent edits just run `clasp push`.

3. **Authorise scopes.** In a Google Doc, open
   **Extensions → Apps Script → Editor**, then **Run → `onOpen`** once.
   Accept the OAuth prompts (Documents, container UI, external requests).
   Reload the doc — the **Humanizer** menu now appears in the menu bar.

4. **Configure the bridge.** Click **Humanizer → Open sidebar** then click
   the cog icon. Paste:
   - **Bridge base URL:** `https://localhost:9999`
   - **Bearer token:** the token from step 1
   - Leave **Profile** as `default_ghanaian` (the dropdown auto-populates from `GET /v1/profiles` on blur).
   - **Backend:** `ollama` (or whichever you have configured).
   Click **Save**. The dialog closes; the sidebar status bar should turn green and read `Daemon v1.2.0 — ollama`.

5. **Trust the self-signed cert.** Visit `https://localhost:9999/v1/health`
   directly in the browser once and accept the security warning. (If your
   browser refuses to display a JSON page after accepting, run the OS-trust
   one-liner the daemon banner printed.)

6. **Score test.** Paste the contents of `/tmp/ai_sample.md` (the
   deliberate AI-flavoured sample shipped with the project) into a doc,
   select all of it, click **Score**.
   - **Expect:** ~0.81 (HIGH), red gauge, top-3 contributors visible under "why".

7. **Rewrite test.** With the same selection still active, click
   **Rewrite** (LLM checkbox left **off** — pure deterministic).
   - **Expect:** the selection is replaced in-place; gauge re-renders below 0.40 (LOW); status bar shows the elapsed time and pre→post score delta.

8. **Suggest test.** Re-select the original AI-flavoured text, click
   **Suggest 3**.
   - **Expect:** three candidate cards each with their own score and band; clicking one then **Apply selected** replaces the selection with that candidate's text.

## Troubleshooting

- **"Daemon unreachable"** with no 401: the browser hasn't trusted the
  self-signed cert. Visit `${baseUrl}/v1/health` once and accept.
- **"401 from /v1/health"**: token mismatch. Re-copy from the daemon
  banner; the token persists at `~/.config/humanizer/serve/token` so a
  daemon restart keeps the same token unless you pass `--rotate-token`.
- **"Backend unavailable" (HTTP 502) on Rewrite with LLM**: the chosen
  backend (default Ollama) is down or no API key is configured. Untick
  the **LLM** checkbox to fall back to the deterministic-only path.
- **"Cannot replace this kind of selection."**: the user selected an
  image, table cell, or other non-text element. Select inline text and
  retry.
- **Multi-paragraph rewrite collapses to a single paragraph**: known
  v1 limitation — see `STATE.md` "Open questions" under round 2.
  Single-paragraph selections preserve all formatting; cross-paragraph
  selections lose paragraph structure inside the replacement.

## Dev workflow

After editing any file in this folder:

```bash
clasp push        # uploads to the bound script project
```

Then reload the Google Doc to pick up the change. There is no automatic
hot-reload — Google's iframe re-fetches the HTML/JS on each
`showSidebar` call, so closing and reopening the sidebar is enough for
HTML / JS / CSS changes. `Code.gs` changes additionally need `clasp push`
to take effect.

## Scope decisions

- The add-in **does not** offer a live-score-as-you-type mode. v2 client
  side feature (deferred per `plan/V1_2_ROADMAP.md` Decision 5).
- The add-in **does not** ship its own grammar pass; if you need
  LanguageTool / Vale / proselint output, run `humanize grammar` from
  the CLI. v1.3 may surface a "Grammar" tab in the sidebar.
- Word / Office 365 add-in is **deferred to v1.3** and will reuse this
  same `BRIDGE_CONTRACT.md` API verbatim.
