/**
 * reviewer.ts — peer-reviewer simulator.
 *
 * Webview message protocol:
 *   incoming { type: "reviewer:run", persona: "r1" | "r2" }
 *   outgoing { type: "reviewer:result", prompt, persona }
 *            { type: "reviewer:error",  message }
 */

import * as vscode from "vscode";
import { reviewer as runReviewer, DaemonError } from "../../daemonClient";

export async function handleReviewer(
  msg: Record<string, unknown>,
  webview: vscode.Webview
): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    webview.postMessage({
      type: "reviewer:error",
      message: "Open a Markdown file to simulate a peer review.",
    });
    return;
  }

  const persona = msg.persona === "r2" ? "r2" : "r1";
  const fullText = editor.document.getText();
  if (!fullText.trim()) {
    webview.postMessage({
      type: "reviewer:error",
      message: "Active file is empty.",
    });
    return;
  }

  try {
    const result = await runReviewer(fullText, persona);
    webview.postMessage({
      type: "reviewer:result",
      prompt: result.prompt,
      persona,
    });
  } catch (err: unknown) {
    webview.postMessage({
      type: "reviewer:error",
      message: _friendlyError(err),
    });
  }
}

function _friendlyError(err: unknown): string {
  if (err instanceof DaemonError) {
    if (err.status === 0) {
      return "Start the Humanizer daemon to use research features.";
    }
    if (err.status === 404) {
      return "Reviewer route not ready — update the daemon.";
    }
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}
