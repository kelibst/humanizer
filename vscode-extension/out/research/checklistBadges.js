"use strict";
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
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.refreshChecklistForActive = refreshChecklistForActive;
exports.registerChecklistDecorations = registerChecklistDecorations;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("../daemonClient");
let _channel;
function _output() {
    if (!_channel) {
        _channel = vscode.window.createOutputChannel("Humanizer Research");
    }
    return _channel;
}
/**
 * Try to grab Agent A's section provider singleton. If
 * ``sectionProcessor.ts`` is missing (Round 1 minimal build, or PM running
 * Track A in a different round), this no-ops gracefully.
 */
function _sectionProvider() {
    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const mod = require("../sectionProcessor");
        if (typeof mod.getSectionProvider === "function") {
            return mod.getSectionProvider();
        }
    }
    catch {
        // sectionProcessor not built — fine, we just skip.
    }
    return undefined;
}
async function refreshChecklistForActive() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
        return;
    }
    const provider = _sectionProvider();
    if (!provider || typeof provider.applyChecklist !== "function") {
        return;
    }
    const cfg = vscode.workspace.getConfiguration("humanizer");
    const profile = cfg.get("profile");
    try {
        const result = await (0, daemonClient_1.checklist)(editor.document.getText(), profile);
        provider.applyChecklist(result.sections.map((s) => ({
            heading: s.heading,
            type: s.type,
            score: s.score,
        })));
    }
    catch (err) {
        const msg = err instanceof daemonClient_1.DaemonError
            ? err.message
            : err instanceof Error
                ? err.message
                : String(err);
        _output().appendLine(`[Humanizer] checklist refresh failed: ${msg}`);
    }
}
function registerChecklistDecorations(ctx) {
    let saveTimer;
    ctx.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(() => {
        void refreshChecklistForActive();
    }));
    ctx.subscriptions.push(vscode.workspace.onDidSaveTextDocument((doc) => {
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
    }));
}
//# sourceMappingURL=checklistBadges.js.map