/**
 * progressStore.ts — workspace-state persistence for section transform progress.
 *
 * CONTRACT §6: three exported functions; key "humanizer.progress"; one record per workspace.
 *
 * The progress map is keyed by section title (lowercase, trimmed) so it survives
 * minor capitalisation changes across sessions.
 */

import * as vscode from "vscode";

// ---------------------------------------------------------------------------
// Types (CONTRACT §6)
// ---------------------------------------------------------------------------

export interface SectionProgress {
  status: "pending" | "done" | "skipped";
  preScore: number | null;
  postScore: number | null;
  transformedAt: string | null; // ISO 8601
}

const STORAGE_KEY = "humanizer.progress";

// ---------------------------------------------------------------------------
// Public API (CONTRACT §6)
// ---------------------------------------------------------------------------

/**
 * Load the progress map from workspaceState.
 * Returns an empty object if nothing is stored yet.
 */
export function loadProgress(
  ctx: vscode.ExtensionContext
): Record<string, SectionProgress> {
  return (
    ctx.workspaceState.get<Record<string, SectionProgress>>(STORAGE_KEY) ?? {}
  );
}

/**
 * Persist the progress map into workspaceState.
 */
export function saveProgress(
  ctx: vscode.ExtensionContext,
  data: Record<string, SectionProgress>
): void {
  ctx.workspaceState.update(STORAGE_KEY, data);
}

/**
 * Clear all progress for this workspace (called by the "Reset" button in the
 * Section Progress tree view).
 */
export function resetProgress(ctx: vscode.ExtensionContext): void {
  ctx.workspaceState.update(STORAGE_KEY, {});
}
