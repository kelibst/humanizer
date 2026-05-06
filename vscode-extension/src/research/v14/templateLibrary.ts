/**
 * templateLibrary.ts — Template library Quick-Pick.
 *
 * Webview message protocol:
 *   incoming { type: "templates:open" }
 *   outgoing { type: "templates:result", prompt, charCount, templateId, templateName }
 *            { type: "templates:error",  message }
 *
 * Flow: list templates → user picks one → if it has fields, prompt for each
 * via showInputBox → render → post the rendered prompt to the webview.
 */

import * as vscode from "vscode";
import {
  listTemplates,
  renderPrompt,
  DaemonError,
  TemplateMeta,
} from "../../daemonClient";

export async function handleTemplates(
  _msg: Record<string, unknown>,
  webview: vscode.Webview
): Promise<void> {
  let metas: TemplateMeta[];
  try {
    const result = await listTemplates();
    metas = result.templates;
  } catch (err: unknown) {
    webview.postMessage({
      type: "templates:error",
      message: _friendlyError(err),
    });
    return;
  }

  if (metas.length === 0) {
    webview.postMessage({
      type: "templates:error",
      message: "No templates available from the daemon.",
    });
    return;
  }

  const items: (vscode.QuickPickItem & { meta: TemplateMeta })[] = metas.map(
    (m) => ({
      meta: m,
      label: m.name,
      description: m.id,
      detail: m.description,
    })
  );
  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: "Pick a research-prompt template",
    matchOnDescription: true,
    matchOnDetail: true,
  });
  if (!picked) {
    return;
  }
  const meta = picked.meta;

  // Gather field values via input boxes.
  const context: Record<string, string> = {};
  for (const field of meta.fields) {
    let prefill = "";
    // Convenience: pre-fill section_text / full_text / results_text from the
    // active markdown editor.
    if (
      field.name === "section_text" ||
      field.name === "full_text" ||
      field.name === "results_text" ||
      field.name === "methods_text" ||
      field.name === "results_bullets"
    ) {
      prefill = _activeMarkdownText() ?? "";
    }
    const value = await vscode.window.showInputBox({
      prompt: `${meta.name} — ${field.name}` + (field.required ? " (required)" : ""),
      value: prefill,
      ignoreFocusOut: true,
      validateInput: (input) => {
        if (field.required && !input.trim()) {
          return `${field.name} is required.`;
        }
        return null;
      },
    });
    if (value === undefined) {
      // User cancelled.
      return;
    }
    if (value.trim()) {
      context[field.name] = value;
    }
  }

  try {
    const out = await renderPrompt(meta.id, context);
    webview.postMessage({
      type: "templates:result",
      prompt: out.prompt,
      charCount: out.charCount,
      templateId: meta.id,
      templateName: meta.name,
    });
  } catch (err: unknown) {
    webview.postMessage({
      type: "templates:error",
      message: _friendlyError(err),
    });
  }
}

function _activeMarkdownText(): string | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    return undefined;
  }
  const sel = editor.selection;
  if (!sel.isEmpty) {
    return editor.document.getText(sel);
  }
  return editor.document.getText();
}

function _friendlyError(err: unknown): string {
  if (err instanceof DaemonError) {
    if (err.status === 0) {
      return "Start the Humanizer daemon to use research features.";
    }
    if (err.status === 404) {
      return "Templates route not ready — update the daemon.";
    }
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}
