"use strict";
/**
 * inspector.ts — handles the per-section inspector.
 *
 * Webview message protocol:
 *   incoming { type: "inspector:run" }
 *   outgoing { type: "inspector:result", findings, sectionTitle, sectionType }
 *            { type: "inspector:error",  message }
 *
 * Section detection reuses the v1.2 ``parseHeadings`` export from
 * sectionProvider.ts, finding the section that contains the cursor.
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
exports.handleInspector = handleInspector;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("../../daemonClient");
const sectionProvider_1 = require("../../sectionProvider");
const TYPE_BY_TITLE = [
    [/^introduction$/i, "introduction"],
    [/^background$/i, "introduction"],
    [/^literature\s+review$/i, "literature_review"],
    [/^method(s|ology)?$/i, "methods"],
    [/^results?$/i, "results"],
    [/^findings$/i, "results"],
    [/^discussion$/i, "discussion"],
    [/^conclusion$/i, "conclusion"],
    [/^references$/i, "references"],
];
function _inferType(title) {
    for (const [re, type] of TYPE_BY_TITLE) {
        if (re.test(title.trim())) {
            return type;
        }
    }
    return "unknown";
}
function _findSectionAtCursor(editor) {
    const lines = editor.document.getText().split("\n");
    const nodes = (0, sectionProvider_1.parseHeadings)(lines);
    if (nodes.length === 0) {
        return undefined;
    }
    const cursorLine = editor.selection.active.line;
    // Find the deepest section enclosing the cursor.
    let match;
    for (const node of nodes) {
        if (cursorLine >= node.lineStart && cursorLine < node.lineEnd) {
            if (!match || node.level >= match.level) {
                match = node;
            }
        }
    }
    if (!match) {
        return undefined;
    }
    // Body excludes the heading line itself.
    const bodyLines = lines.slice(match.lineStart + 1, match.lineEnd);
    return { node: match, text: bodyLines.join("\n") };
}
async function handleInspector(_msg, webview) {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
        webview.postMessage({
            type: "inspector:error",
            message: "Open a Markdown file and put your cursor inside a section first.",
        });
        return;
    }
    const located = _findSectionAtCursor(editor);
    if (!located || !located.text.trim()) {
        webview.postMessage({
            type: "inspector:error",
            message: "No section found at the cursor — place the cursor inside a section body.",
        });
        return;
    }
    const sectionType = _inferType(located.node.title);
    try {
        const result = await (0, daemonClient_1.inspect)(located.text, sectionType);
        webview.postMessage({
            type: "inspector:result",
            sectionTitle: located.node.title,
            sectionType,
            findings: result.findings,
        });
    }
    catch (err) {
        webview.postMessage({
            type: "inspector:error",
            message: _friendlyError(err),
        });
    }
}
function _friendlyError(err) {
    if (err instanceof daemonClient_1.DaemonError) {
        if (err.status === 0) {
            return "Start the Humanizer daemon to use research features.";
        }
        if (err.status === 404) {
            return "Inspector route not ready — update the daemon.";
        }
        return err.message;
    }
    if (err instanceof Error) {
        return err.message;
    }
    return String(err);
}
//# sourceMappingURL=inspector.js.map