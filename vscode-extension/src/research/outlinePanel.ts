/**
 * outlinePanel.ts — sidebar Outline panel handler.
 *
 * Reuses the existing ``parseHeadings`` export from ``sectionProvider.ts``
 * (Track A, v1.2) so the outline shares the same heading model as the
 * Section Progress tree — guaranteeing they stay in sync.
 *
 * Messages handled:
 *   incoming: { type: "outline.fetch" }                  → refresh outline
 *             { type: "outline.reveal", lineStart: n }   → reveal in editor
 *   outgoing: { type: "outline.data", headings: [...] }
 */

import * as vscode from "vscode";
import { parseHeadings, SectionNode } from "../sectionProvider";

export interface OutlineEntry {
  title: string;
  level: number;
  lineStart: number;
  wordCount: number;
}

function _activeMarkdownEditor(): vscode.TextEditor | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    return undefined;
  }
  return editor;
}

function _toEntry(node: SectionNode): OutlineEntry {
  return {
    title: node.title,
    level: node.level,
    lineStart: node.lineStart,
    wordCount: node.wordCount,
  };
}

export function buildOutline(): OutlineEntry[] {
  const editor = _activeMarkdownEditor();
  if (!editor) {
    return [];
  }
  const lines = editor.document.getText().split("\n");
  return parseHeadings(lines).map(_toEntry);
}

export async function revealHeading(lineStart: number): Promise<void> {
  const editor = _activeMarkdownEditor();
  if (!editor) {
    return;
  }
  const target = Math.max(0, Math.min(lineStart, editor.document.lineCount - 1));
  const range = editor.document.lineAt(target).range;
  editor.selection = new vscode.Selection(range.start, range.start);
  editor.revealRange(range, vscode.TextEditorRevealType.AtTop);
  await vscode.window.showTextDocument(editor.document, editor.viewColumn, false);
}

export async function handleOutlineMessage(
  msg: { type: string; lineStart?: number },
  webview: vscode.Webview
): Promise<void> {
  switch (msg.type) {
    case "outline.fetch":
      webview.postMessage({ type: "outline.data", headings: buildOutline() });
      break;
    case "outline.reveal":
      if (typeof msg.lineStart === "number") {
        await revealHeading(msg.lineStart);
      }
      break;
    default:
      break;
  }
}
