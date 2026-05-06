"use strict";
/**
 * activeEditorTracker.ts — tracks the last markdown editor that was active.
 *
 * CONTRACT §9 invariant:
 *   _last is ONLY updated when a markdown editor becomes active.
 *   _last is NEVER cleared by focus shifts to webviews, output channels, or
 *   terminals. _last becomes undefined only when VS Code closes or the tracked
 *   document is explicitly closed (optional guard via onDidCloseTextDocument).
 *
 * Exports:
 *   registerActiveEditorTracker(ctx)  — call once in activate()
 *   getLastMarkdownEditor()           — safe accessor; checks isClosed; scans
 *                                       visibleTextEditors as fallback
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
exports.registerActiveEditorTracker = registerActiveEditorTracker;
exports.getLastMarkdownEditor = getLastMarkdownEditor;
const vscode = __importStar(require("vscode"));
// Module-level last known markdown editor.
let _last;
/**
 * Register the active-editor tracker. Must be called once from activate().
 * Pushes all disposables onto ctx.subscriptions.
 */
function registerActiveEditorTracker(ctx) {
    // Seed _last from the current active editor (in case a .md file is already
    // open when the extension activates).
    const initial = vscode.window.activeTextEditor;
    if (initial && initial.document.languageId === "markdown") {
        _last = initial;
    }
    // Update _last whenever a markdown editor becomes active.
    ctx.subscriptions.push(vscode.window.onDidChangeActiveTextEditor((editor) => {
        if (editor && editor.document.languageId === "markdown") {
            _last = editor;
        }
        // Intentionally no `else` — focus shifts to webviews / terminals / output
        // channels must NOT clear _last (CONTRACT §9 invariant).
    }));
    // Optional guard: clear _last when its document is closed to avoid holding a
    // stale reference to a removed file.
    ctx.subscriptions.push(vscode.workspace.onDidCloseTextDocument((doc) => {
        if (_last && _last.document === doc) {
            _last = undefined;
        }
    }));
}
/**
 * Return the last markdown editor that was active, or find one from the
 * currently visible editors if the cached reference is stale/closed.
 *
 * Callers must NOT cache the returned reference; call this function on every
 * use so you always get the freshest valid editor.
 *
 * Returns undefined if no markdown editor is open anywhere.
 */
function getLastMarkdownEditor() {
    // Primary: the tracked last-active markdown editor (if still open).
    if (_last && !_last.document.isClosed) {
        return _last;
    }
    // Fallback: scan currently visible editors for any markdown one.
    return vscode.window.visibleTextEditors.find((e) => e.document.languageId === "markdown");
}
//# sourceMappingURL=activeEditorTracker.js.map