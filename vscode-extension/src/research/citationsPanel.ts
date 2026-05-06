/**
 * citationsPanel.ts — sidebar Citations panel handler.
 *
 * Hits ``POST /v1/citations`` on demand and posts a ``citations.data``
 * message back into the webview. Workspace root is the first opened
 * folder; if no folder is open, returns ``citations.error``.
 *
 * Messages:
 *   incoming: { type: "citations.fetch" }
 *             { type: "citations.reveal", start, end }
 *   outgoing: { type: "citations.data", missing, orphans, unused }
 *             { type: "citations.error", message }
 */

import * as vscode from "vscode";
import { citations as fetchCitations, DaemonError } from "../daemonClient";

function _workspaceRoot(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    return undefined;
  }
  return folders[0].uri.fsPath;
}

function _activeMarkdown(): vscode.TextEditor | undefined {
  const editor = vscode.window.activeTextEditor;
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

export async function handleCitationsMessage(
  msg: { type: string; start?: number; end?: number },
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
    default:
      break;
  }
}
