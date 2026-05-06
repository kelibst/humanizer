"use strict";
/**
 * progressStore.ts — workspace-state persistence for section transform progress.
 *
 * CONTRACT §6: three exported functions; key "humanizer.progress"; one record per workspace.
 *
 * The progress map is keyed by section title (lowercase, trimmed) so it survives
 * minor capitalisation changes across sessions.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.loadProgress = loadProgress;
exports.saveProgress = saveProgress;
exports.resetProgress = resetProgress;
const STORAGE_KEY = "humanizer.progress";
// ---------------------------------------------------------------------------
// Public API (CONTRACT §6)
// ---------------------------------------------------------------------------
/**
 * Load the progress map from workspaceState.
 * Returns an empty object if nothing is stored yet.
 */
function loadProgress(ctx) {
    return (ctx.workspaceState.get(STORAGE_KEY) ?? {});
}
/**
 * Persist the progress map into workspaceState.
 */
function saveProgress(ctx, data) {
    ctx.workspaceState.update(STORAGE_KEY, data);
}
/**
 * Clear all progress for this workspace (called by the "Reset" button in the
 * Section Progress tree view).
 */
function resetProgress(ctx) {
    ctx.workspaceState.update(STORAGE_KEY, {});
}
//# sourceMappingURL=progressStore.js.map