"use strict";
/**
 * v14/index.ts — wires the v1.4 research-assistant sidebar panels.
 *
 * Uses the v1.3 ``SidebarProvider.researchHandlerHook`` chain so the existing
 * outline / citations / readability handlers keep working untouched. The v14
 * hook claims any message whose ``type`` starts with ``studyStarter:``,
 * ``inspector:``, ``templates:``, or ``reviewer:``.
 *
 * Also extends the ``config`` event by listening for the webview's ``ready``
 * message and posting an extended config payload that includes
 * ``backendConfigured: boolean`` so the panels can show or hide the
 * "Send to backend" button.
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
exports.registerV14ResearchSurfaces = registerV14ResearchSurfaces;
const vscode = __importStar(require("vscode"));
const sidebarProvider_1 = require("../../sidebarProvider");
const studyStarter_1 = require("./studyStarter");
const inspector_1 = require("./inspector");
const templateLibrary_1 = require("./templateLibrary");
const reviewer_1 = require("./reviewer");
/**
 * Public entry point — called once from extension.ts during activate().
 */
function registerV14ResearchSurfaces(ctx) {
    const sub = sidebarProvider_1.SidebarProvider.researchHandlerHook(async (msg, webview) => {
        const t = String(msg.type ?? "");
        if (t === "ready") {
            // Augment the config payload with backendConfigured. We do NOT claim
            // ``ready`` — the v1.2 handler still needs to send its own config.
            // Defer slightly so our extra config arrives just after the v1.2 one.
            setTimeout(() => {
                try {
                    webview.postMessage({
                        type: "config",
                        settings: {
                            backendConfigured: _backendConfigured(),
                        },
                    });
                }
                catch {
                    // ignore
                }
            }, 30);
            return false;
        }
        if (t.startsWith("studyStarter:")) {
            if (t === "studyStarter:run") {
                await (0, studyStarter_1.handleStudyStarter)(msg, webview);
            }
            return true;
        }
        if (t.startsWith("inspector:")) {
            if (t === "inspector:run") {
                await (0, inspector_1.handleInspector)(msg, webview);
            }
            return true;
        }
        if (t.startsWith("templates:")) {
            if (t === "templates:open") {
                await (0, templateLibrary_1.handleTemplates)(msg, webview);
            }
            return true;
        }
        if (t.startsWith("reviewer:")) {
            if (t === "reviewer:run") {
                await (0, reviewer_1.handleReviewer)(msg, webview);
            }
            return true;
        }
        return false;
    });
    ctx.subscriptions.push(sub);
}
/**
 * Heuristic: a backend is configured when the user has set a non-empty
 * key/token for the active backend (or selected ollama, which uses no key).
 * The settings live under ``humanizer.*`` and ``humanizerBackends.*`` (the
 * latter is added by Agent B in a future round but checked defensively).
 */
function _backendConfigured() {
    const cfg = vscode.workspace.getConfiguration("humanizer");
    const backend = cfg.get("backend", "ollama");
    if (backend === "ollama") {
        // Ollama is local-only; assume present. The daemon health check will
        // surface a real failure later.
        return true;
    }
    // For remote backends we look for an API key under common settings keys.
    // Agent B has not committed to a final key name yet; check both shapes
    // so we light up correctly when they ship.
    const keyCandidates = [
        `${backend}.apiKey`,
        `backends.${backend}.apiKey`,
        `${backend}ApiKey`,
    ];
    for (const k of keyCandidates) {
        const v = cfg.get(k);
        if (typeof v === "string" && v.trim()) {
            return true;
        }
    }
    return false;
}
//# sourceMappingURL=index.js.map