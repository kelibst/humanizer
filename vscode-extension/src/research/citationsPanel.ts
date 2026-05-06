/**
 * citationsPanel.ts — sidebar Citations panel handler.
 *
 * Hits ``POST /v1/citations`` on demand and posts a ``citations.data``
 * message back into the webview. Workspace root is the first opened
 * folder; if no folder is open, returns ``citations.error``.
 *
 * v1.5 additions (CONTRACT §A3):
 *   resolveOrphan()     — stub-create one orphan key
 *   resolveAllOrphans() — stub-create all current orphans
 *
 * Messages:
 *   incoming: { type: "citations.fetch" }
 *             { type: "citations.reveal", start, end }
 *             { type: "citations.resolveOrphan", key }    (v1.5)
 *             { type: "citations.resolveAll" }            (v1.5)
 *   outgoing: { type: "citations.data", missing, orphans, unused }
 *             { type: "citations.error", message }
 */

import * as vscode from "vscode";
import {
  citations as fetchCitations,
  batchStubOrphans,
  DaemonError,
} from "../daemonClient";
import { getLastMarkdownEditor } from "../activeEditorTracker";

function _workspaceRoot(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    return undefined;
  }
  return folders[0].uri.fsPath;
}

function _activeMarkdown(): vscode.TextEditor | undefined {
  const editor = getLastMarkdownEditor() ?? vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    return undefined;
  }
  return editor;
}

export async function fetchCitationsForActive(): Promise<
  { ok: true; data: Awaited<ReturnType<typeof fetchCitations>> }
  | { ok: false; message: string }
> {
  const editor = _activeMarkdown();
  if (!editor) {
    return { ok: false, message: "No active markdown file." };
  }
  const root = _workspaceRoot();
  if (!root) {
    return { ok: false, message: "Open a workspace folder to scan citations." };
  }
  const text = editor.document.getText();
  const cfg = vscode.workspace.getConfiguration("humanizer");
  const profile = cfg.get<string>("profile");
  try {
    const data = await fetchCitations(text, root, profile);
    return { ok: true, data };
  } catch (err: unknown) {
    const msg =
      err instanceof DaemonError
        ? err.message
        : err instanceof Error
        ? err.message
        : String(err);
    return { ok: false, message: msg };
  }
}

export async function revealOffset(start: number, end: number): Promise<void> {
  const editor = _activeMarkdown();
  if (!editor) {
    return;
  }
  const startPos = editor.document.positionAt(Math.max(0, start));
  const endPos = editor.document.positionAt(
    Math.max(start, Math.min(end, editor.document.getText().length))
  );
  editor.selection = new vscode.Selection(startPos, endPos);
  editor.revealRange(
    new vscode.Range(startPos, endPos),
    vscode.TextEditorRevealType.InCenter
  );
}

// ---------------------------------------------------------------------------
// v1.5 — orphan resolution helpers (CONTRACT §A3)
// ---------------------------------------------------------------------------

/**
 * Create a stub reference for a single orphan citation key.
 * On success, re-fetches the full citations list and posts ``citations.data``.
 */
export async function resolveOrphan(
  key: string,
  webview: vscode.Webview
): Promise<void> {
  const root = _workspaceRoot();
  if (!root) {
    webview.postMessage({
      type: "citations.error",
      message: "Open a workspace folder to resolve orphan citations.",
    });
    return;
  }
  try {
    await batchStubOrphans([key], root);
    // Re-fetch so the panel reflects the new stub.
    const result = await fetchCitationsForActive();
    if (result.ok) {
      webview.postMessage({
        type: "citations.data",
        missing: result.data.missing,
        orphans: result.data.orphans,
        unused: result.data.unused,
      });
    }
    vscode.window.setStatusBarMessage(`Humanizer: created stub for "${key}"`, 4000);
  } catch (err: unknown) {
    const msg =
      err instanceof DaemonError
        ? err.message
        : err instanceof Error
        ? err.message
        : String(err);
    webview.postMessage({ type: "citations.error", message: msg });
  }
}

/**
 * Create stub references for ALL current orphan keys.
 * Calls ``POST /v1/citations`` to get the current orphan list, then
 * calls ``POST /v1/refs/batch-stub`` with all keys at once.
 */
export async function resolveAllOrphans(webview: vscode.Webview): Promise<void> {
  const root = _workspaceRoot();
  if (!root) {
    webview.postMessage({
      type: "citations.error",
      message: "Open a workspace folder to resolve orphan citations.",
    });
    return;
  }
  const result = await fetchCitationsForActive();
  if (!result.ok) {
    webview.postMessage({ type: "citations.error", message: result.message });
    return;
  }
  const orphanKeys = result.data.orphans.map((o) => o.key);
  if (orphanKeys.length === 0) {
    vscode.window.showInformationMessage("Humanizer: No orphan citations to resolve.");
    return;
  }
  try {
    const stubResult = await batchStubOrphans(orphanKeys, root);
    // Re-fetch so the panel reflects the new stubs.
    const refreshed = await fetchCitationsForActive();
    if (refreshed.ok) {
      webview.postMessage({
        type: "citations.data",
        missing: refreshed.data.missing,
        orphans: refreshed.data.orphans,
        unused: refreshed.data.unused,
      });
    }
    vscode.window.showInformationMessage(
      `Humanizer: Created ${stubResult.created} stub(s) for orphan citations ` +
        `(${stubResult.skipped} already existed).`
    );
  } catch (err: unknown) {
    const msg =
      err instanceof DaemonError
        ? err.message
        : err instanceof Error
        ? err.message
        : String(err);
    webview.postMessage({ type: "citations.error", message: msg });
  }
}

// ---------------------------------------------------------------------------
// Message router
// ---------------------------------------------------------------------------

export async function handleCitationsMessage(
  msg: { type: string; start?: number; end?: number; key?: string },
  webview: vscode.Webview
): Promise<void> {
  switch (msg.type) {
    case "citations.fetch": {
      const result = await fetchCitationsForActive();
      if (result.ok) {
        webview.postMessage({
          type: "citations.data",
          missing: result.data.missing,
          orphans: result.data.orphans,
          unused: result.data.unused,
        });
      } else {
        webview.postMessage({
          type: "citations.error",
          message: result.message,
        });
      }
      break;
    }
    case "citations.reveal":
      if (typeof msg.start === "number" && typeof msg.end === "number") {
        await revealOffset(msg.start, msg.end);
      }
      break;
    // v1.5 — resolve a single orphan
    case "citations.resolveOrphan":
      if (typeof msg.key === "string" && msg.key) {
        await resolveOrphan(msg.key, webview);
      }
      break;
    // v1.5 — resolve all orphans
    case "citations.resolveAll":
      await resolveAllOrphans(webview);
      break;
    default:
      break;
  }
}
