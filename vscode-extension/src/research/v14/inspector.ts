/**
 * inspector.ts — handles the per-section inspector.
 *
 * Webview message protocol:
 *   incoming { type: "inspector:run" }
 *   outgoing { type: "inspector:result", findings, sectionTitle, sectionType }
 *            { type: "inspector:error",  message }
 *
 * Section detection reuses the v1.2 ``parseHeadings`` export from
 * sectionProvider.ts, finding the section that contains the cursor.
 */

import * as vscode from "vscode";
import { inspect, DaemonError } from "../../daemonClient";
import { parseHeadings, SectionNode } from "../../sectionProvider";
import { getLastMarkdownEditor } from "../../activeEditorTracker";

const TYPE_BY_TITLE: Array<[RegExp, string]> = [
  [/^introduction$/i, "introduction"],
  [/^background$/i, "introduction"],
  [/^literature\s+review$/i, "literature_review"],
  [/^method(s|ology)?$/i, "methods"],
  [/^results?$/i, "results"],
  [/^findings$/i, "results"],
  [/^discussion$/i, "discussion"],
  [/^conclusion$/i, "conclusion"],
  [/^references$/i, "references"],
];

function _inferType(title: string): string {
  for (const [re, type] of TYPE_BY_TITLE) {
    if (re.test(title.trim())) {
      return type;
    }
  }
  return "unknown";
}

function _findSectionAtCursor(
  editor: vscode.TextEditor
): { node: SectionNode; text: string } | undefined {
  const lines = editor.document.getText().split("\n");
  const nodes = parseHeadings(lines);
  if (nodes.length === 0) {
    return undefined;
  }
  const cursorLine = editor.selection.active.line;
  // Find the deepest section enclosing the cursor.
  let match: SectionNode | undefined;
  for (const node of nodes) {
    if (cursorLine >= node.lineStart && cursorLine < node.lineEnd) {
      if (!match || node.level >= match.level) {
        match = node;
      }
    }
  }
  if (!match) {
    return undefined;
  }
  // Body excludes the heading line itself.
  const bodyLines = lines.slice(match.lineStart + 1, match.lineEnd);
  return { node: match, text: bodyLines.join("\n") };
}

export async function handleInspector(
  _msg: Record<string, unknown>,
  webview: vscode.Webview
): Promise<void> {
  const editor = getLastMarkdownEditor() ?? vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    webview.postMessage({
      type: "inspector:error",
      message: "Open a Markdown file and put your cursor inside a section first.",
    });
    return;
  }

  const located = _findSectionAtCursor(editor);
  if (!located || !located.text.trim()) {
    webview.postMessage({
      type: "inspector:error",
      message:
        "No section found at the cursor — place the cursor inside a section body.",
    });
    return;
  }

  const sectionType = _inferType(located.node.title);

  try {
    const result = await inspect(located.text, sectionType);
    webview.postMessage({
      type: "inspector:result",
      sectionTitle: located.node.title,
      sectionType,
      findings: result.findings,
    });
  } catch (err: unknown) {
    webview.postMessage({
      type: "inspector:error",
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
      return "Inspector route not ready — update the daemon.";
    }
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}
