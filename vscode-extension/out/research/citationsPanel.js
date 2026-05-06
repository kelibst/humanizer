"use strict";
/**
 * citationsPanel.ts — sidebar Citations panel handler.
 *
 * Hits ``POST /v1/citations`` on demand and posts a ``citations.data``
 * message back into the webview. Workspace root is the first opened
 * folder; if no folder is open, returns ``citations.error``.
 *
 * Messages:
 *   incoming: { type: "citations.fetch" }
 *             { type: "citations.reveal", start, end }
 *   outgoing: { type: "citations.data", missing, orphans, unused }
 *             { type: "citations.error", message }
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
exports.fetchCitationsForActive = fetchCitationsForActive;
exports.revealOffset = revealOffset;
exports.handleCitationsMessage = handleCitationsMessage;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("../daemonClient");
function _workspaceRoot() {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        return undefined;
    }
    return folders[0].uri.fsPath;
}
function _activeMarkdown() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
        return undefined;
    }
    return editor;
}
async function fetchCitationsForActive() {
    const editor = _activeMarkdown();
    if (!editor) {
        return { ok: false, message: "No active markdown file." };
    }
    const root = _workspaceRoot();
    if (!root) {
        return { ok: false, message: "Open a workspace folder to scan citations." };
    }
    const text = editor.document.getText();
    const cfg = vscode.workspace.getConfiguration("humanizer");
    const profile = cfg.get("profile");
    try {
        const data = await (0, daemonClient_1.citations)(text, root, profile);
        return { ok: true, data };
    }
    catch (err) {
        const msg = err instanceof daemonClient_1.DaemonError
            ? err.message
            : err instanceof Error
                ? err.message
                : String(err);
        return { ok: false, message: msg };
    }
}
async function revealOffset(start, end) {
    const editor = _activeMarkdown();
    if (!editor) {
        return;
    }
    const startPos = editor.document.positionAt(Math.max(0, start));
    const endPos = editor.document.positionAt(Math.max(start, Math.min(end, editor.document.getText().length)));
    editor.selection = new vscode.Selection(startPos, endPos);
    editor.revealRange(new vscode.Range(startPos, endPos), vscode.TextEditorRevealType.InCenter);
}
async function handleCitationsMessage(msg, webview) {
    switch (msg.type) {
        case "citations.fetch": {
            const result = await fetchCitationsForActive();
            if (result.ok) {
                webview.postMessage({
                    type: "citations.data",
                    missing: result.data.missing,
                    orphans: result.data.orphans,
                    unused: result.data.unused,
                });
            }
            else {
                webview.postMessage({
                    type: "citations.error",
                    message: result.message,
                });
            }
            break;
        }
        case "citations.reveal":
            if (typeof msg.start === "number" && typeof msg.end === "number") {
                await revealOffset(msg.start, msg.end);
            }
            break;
        default:
            break;
    }
}
//# sourceMappingURL=citationsPanel.js.map