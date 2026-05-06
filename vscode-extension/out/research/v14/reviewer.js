"use strict";
/**
 * reviewer.ts — peer-reviewer simulator.
 *
 * Webview message protocol:
 *   incoming { type: "reviewer:run", persona: "r1" | "r2" }
 *   outgoing { type: "reviewer:result", prompt, persona }
 *            { type: "reviewer:error",  message }
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
exports.handleReviewer = handleReviewer;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("../../daemonClient");
async function handleReviewer(msg, webview) {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
        webview.postMessage({
            type: "reviewer:error",
            message: "Open a Markdown file to simulate a peer review.",
        });
        return;
    }
    const persona = msg.persona === "r2" ? "r2" : "r1";
    const fullText = editor.document.getText();
    if (!fullText.trim()) {
        webview.postMessage({
            type: "reviewer:error",
            message: "Active file is empty.",
        });
        return;
    }
    try {
        const result = await (0, daemonClient_1.reviewer)(fullText, persona);
        webview.postMessage({
            type: "reviewer:result",
            prompt: result.prompt,
            persona,
        });
    }
    catch (err) {
        webview.postMessage({
            type: "reviewer:error",
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
            return "Reviewer route not ready — update the daemon.";
        }
        return err.message;
    }
    if (err instanceof Error) {
        return err.message;
    }
    return String(err);
}
//# sourceMappingURL=reviewer.js.map