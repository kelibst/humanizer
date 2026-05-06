/**
 * checklistBadges.ts — fetch /v1/checklist for the active markdown file and
 * push the per-section results into the Section Progress tree as badges.
 *
 * Runs:
 *   * On extension activation (initial pass for the active editor).
 *   * On editor switch (active text editor changes).
 *   * On document save (debounced 600 ms).
 *
 * Failures are silent — checklist badges are cosmetic. We never block other
 * surfaces if /v1/checklist returns 4xx/5xx. Errors land in the
 * "Humanizer Research" output channel.
 */

import * as vscode from "vscode";
import { checklist as fetchChecklist, DaemonError } from "../daemonClient";

let _channel: vscode.OutputChannel | undefined;

function _output(): vscode.OutputChannel {
  if (!_channel) {
    _channel = vscode.window.createOutputChannel("Humanizer Research");
  }
  return _channel;
}

interface SectionProviderShape {
  applyChecklist?: (
    sections: { heading: string; type: string; score: string }[]
  ) => void;
}

/**
 * Try to grab Agent A's section provider singleton. If
 * ``sectionProcessor.ts`` is missing (Round 1 minimal build, or PM running
 * Track A in a different round), this no-ops gracefully.
 */
function _sectionProvider(): SectionProviderShape | undefined {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require("../sectionProcessor") as {
      getSectionProvider?: () => SectionProviderShape | undefined;
    };
    if (typeof mod.getSectionProvider === "function") {
      return mod.getSectionProvider();
    }
  } catch {
    // sectionProcessor not built — fine, we just skip.
  }
  return undefined;
}

export async function refreshChecklistForActive(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    return;
  }
  const provider = _sectionProvider();
  if (!provider || typeof provider.applyChecklist !== "function") {
    return;
  }
  const cfg = vscode.workspace.getConfiguration("humanizer");
  const profile = cfg.get<string>("profile");
  try {
    const result = await fetchChecklist(editor.document.getText(), profile);
    provider.applyChecklist(
      result.sections.map((s) => ({
        heading: s.heading,
        type: s.type,
        score: s.score,
      }))
    );
  } catch (err: unknown) {
    const msg =
      err instanceof DaemonError
        ? err.message
        : err instanceof Error
        ? err.message
        : String(err);
    _output().appendLine(`[Humanizer] checklist refresh failed: ${msg}`);
  }
}

export function registerChecklistDecorations(
  ctx: vscode.ExtensionContext
): void {
  let saveTimer: ReturnType<typeof setTimeout> | undefined;

  ctx.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(() => {
      void refreshChecklistForActive();
    })
  );

  ctx.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document !== doc) {
        return;
      }
      if (doc.languageId !== "markdown") {
        return;
      }
      if (saveTimer !== undefined) {
        clearTimeout(saveTimer);
      }
      saveTimer = setTimeout(() => {
        void refreshChecklistForActive();
      }, 600);
    })
  );
}
