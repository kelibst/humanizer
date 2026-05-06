/**
 * readabilityPanel.ts — sidebar Readability panel handler.
 *
 * Hits ``POST /v1/readability`` on demand and posts the metrics + target
 * checks back into the webview.
 *
 * Messages:
 *   incoming: { type: "readability.fetch" }
 *   outgoing: { type: "readability.data", metrics, targets }
 *             { type: "readability.error", message }
 */

import * as vscode from "vscode";
import {
  DaemonError,
  readability as fetchReadability,
} from "../daemonClient";

function _activeMarkdown(): vscode.TextEditor | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    return undefined;
  }
  return editor;
}

export async function handleReadabilityMessage(
  msg: { type: string },
  webview: vscode.Webview
): Promise<void> {
  if (msg.type !== "readability.fetch") {
    return;
  }
  const editor = _activeMarkdown();
  if (!editor) {
    webview.postMessage({
      type: "readability.error",
      message: "No active markdown file.",
    });
    return;
  }
  const text = editor.document.getText();
  const cfg = vscode.workspace.getConfiguration("humanizer");
  const profile = cfg.get<string>("profile");
  try {
    const result = await fetchReadability(text, profile);
    webview.postMessage({
      type: "readability.data",
      metrics: result.metrics,
      targets: result.targets,
    });
  } catch (err: unknown) {
    const msg2 =
      err instanceof DaemonError
        ? err.message
        : err instanceof Error
        ? err.message
        : String(err);
    webview.postMessage({ type: "readability.error", message: msg2 });
  }
}
