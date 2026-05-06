"use strict";
/**
 * readabilityPanel.ts — sidebar Readability panel handler.
 *
 * Hits ``POST /v1/readability`` on demand and posts the metrics + target
 * checks back into the webview.
 *
 * Messages:
 *   incoming: { type: "readability.fetch" }
 *   outgoing: { type: "readability.data", metrics, targets }
 *             { type: "readability.error", message }
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
exports.handleReadabilityMessage = handleReadabilityMessage;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("../daemonClient");
function _activeMarkdown() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
        return undefined;
    }
    return editor;
}
async function handleReadabilityMessage(msg, webview) {
    if (msg.type !== "readability.fetch") {
        return;
    }
    const editor = _activeMarkdown();
    if (!editor) {
        webview.postMessage({
            type: "readability.error",
            message: "No active markdown file.",
        });
        return;
    }
    const text = editor.document.getText();
    const cfg = vscode.workspace.getConfiguration("humanizer");
    const profile = cfg.get("profile");
    try {
        const result = await (0, daemonClient_1.readability)(text, profile);
        webview.postMessage({
            type: "readability.data",
            metrics: result.metrics,
            targets: result.targets,
        });
    }
    catch (err) {
        const msg2 = err instanceof daemonClient_1.DaemonError
            ? err.message
            : err instanceof Error
                ? err.message
                : String(err);
        webview.postMessage({ type: "readability.error", message: msg2 });
    }
}
//# sourceMappingURL=readabilityPanel.js.map