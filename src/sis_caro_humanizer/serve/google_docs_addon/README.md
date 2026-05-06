# Humanizer Citation Checker — Google Docs Add-In

A stub Apps Script add-in that connects your Google Doc to the local
humanizer daemon and highlights orphan citations in red while showing a
sidebar summary of missing, orphan, and unused references.

---

## Prerequisites

1. The humanizer daemon must be running on your machine (or a machine
   reachable from your browser):

   ```bash
   humanize serve --port 9999
   ```

2. You need a bearer token.  Find yours at:

   ```
   ~/.config/humanizer/serve/token
   ```

---

## Installation

1. Open your Google Doc in a browser.
2. Click **Extensions → Apps Script**.
3. Delete any existing code in the editor.
4. Copy the entire contents of `Code.gs` and paste it into the editor.
5. Click **Save** (the floppy-disk icon or Ctrl+S).
6. Close the Apps Script tab and reload your Google Doc.

You should now see a **Humanizer** menu in the Google Docs menu bar.

---

## Configuring Script Properties

The add-in reads `HUMANIZER_URL` and `HUMANIZER_TOKEN` from the script's
properties so you never have to hard-code secrets in the source file.

1. In the Apps Script editor, click **Project Settings** (the gear icon).
2. Scroll to **Script Properties** and click **Add script property**.
3. Add the following two properties:

   | Property name      | Example value                          |
   |--------------------|----------------------------------------|
   | `HUMANIZER_URL`    | `http://localhost:9999`                |
   | `HUMANIZER_TOKEN`  | (paste the token from `~/.config/...`) |

4. Click **Save script properties**.

---

## Usage

1. Open the Google Doc that contains the text you want to check.
2. Click **Humanizer → Check Citations** in the menu bar.
3. The add-in will:
   - Send all paragraph texts to the daemon's `/v1/citations/google-docs`
     endpoint.
   - Highlight any orphan citations (citations with no matching reference
     entry) in **red** directly in the document.
   - Open a sidebar listing:
     - **Orphans** — citations present in the text but absent from
       `references.json`, with their paragraph index.
     - **Missing** — claims or hedge phrases that should have a citation
       but do not, with the claim text and paragraph index.
     - **Unused refs** — entries in `references.json` that are never
       cited in the document.

---

## What the endpoint does

`POST /v1/citations/google-docs` accepts a JSON body:

```json
{
  "paragraphs": ["First paragraph text.", "Second paragraph text.", ...],
  "workspace_root": "/path/to/project",   // optional
  "profile": "akua"                        // optional
}
```

It joins the paragraph list with `\n\n`, runs the full citation analysis
(orphan detection, missing-citation detection, unused-reference detection),
and returns flat character offsets **plus** paragraph-level coordinates
(`paragraph_idx`, `char_in_paragraph`) so the Apps Script add-in can
highlight text using `paragraph.editAsText().setForegroundColor()` without
needing to call `positionAt()`.

---

## Notes

- This is a **stub**, not a full Google Workspace Marketplace add-in.  The
  user pastes `Code.gs` manually.  Full Marketplace deployment is out of
  scope for v1.6.
- The daemon must be reachable from the machine running the browser.  If
  you are working remotely, set up an SSH tunnel or use a reverse proxy.
- Google Apps Script enforces CORS and UrlFetch policies.  The daemon
  already sets `Access-Control-Allow-Origin: https://script.google.com`
  so requests from Apps Script are accepted.
