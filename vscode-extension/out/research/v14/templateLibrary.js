"use strict";
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
exports.handleTemplates = handleTemplates;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("../../daemonClient");
async function handleTemplates(_msg, webview) {
    let metas;
    try {
        const result = await (0, daemonClient_1.listTemplates)();
        metas = result.templates;
    }
    catch (err) {
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
    const items = metas.map((m) => ({
        meta: m,
        label: m.name,
        description: m.id,
        detail: m.description,
    }));
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
    const context = {};
    for (const field of meta.fields) {
        let prefill = "";
        // Convenience: pre-fill section_text / full_text / results_text from the
        // active markdown editor.
        if (field.name === "section_text" ||
            field.name === "full_text" ||
            field.name === "results_text" ||
            field.name === "methods_text" ||
            field.name === "results_bullets") {
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
        const out = await (0, daemonClient_1.renderPrompt)(meta.id, context);
        webview.postMessage({
            type: "templates:result",
            prompt: out.prompt,
            charCount: out.charCount,
            templateId: meta.id,
            templateName: meta.name,
        });
    }
    catch (err) {
        webview.postMessage({
            type: "templates:error",
            message: _friendlyError(err),
        });
    }
}
function _activeMarkdownText() {
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
function _friendlyError(err) {
    if (err instanceof daemonClient_1.DaemonError) {
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
//# sourceMappingURL=templateLibrary.js.map