"use strict";
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
exports.buildOutline = buildOutline;
exports.revealHeading = revealHeading;
exports.handleOutlineMessage = handleOutlineMessage;
const vscode = __importStar(require("vscode"));
const sectionProvider_1 = require("../sectionProvider");
function _activeMarkdownEditor() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
        return undefined;
    }
    return editor;
}
function _toEntry(node) {
    return {
        title: node.title,
        level: node.level,
        lineStart: node.lineStart,
        wordCount: node.wordCount,
    };
}
function buildOutline() {
    const editor = _activeMarkdownEditor();
    if (!editor) {
        return [];
    }
    const lines = editor.document.getText().split("\n");
    return (0, sectionProvider_1.parseHeadings)(lines).map(_toEntry);
}
async function revealHeading(lineStart) {
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
async function handleOutlineMessage(msg, webview) {
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
//# sourceMappingURL=outlinePanel.js.map