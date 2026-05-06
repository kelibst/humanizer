"use strict";
/**
 * research/index.ts — single entry point Agent A imports from extension.ts.
 *
 * Wires up:
 *   * ``humanizer.insertCitation`` Quick-Pick command
 *   * ``humanizer.openOutline`` command — focuses the sidebar
 *   * Sidebar webview message handlers for outline / citations / readability
 *   * Section-tree checklist badges (debounced refresh on save)
 *   * Optional handler hook into Agent A's code-action provider for
 *     ``missing-citation`` (graceful no-op if Agent A's export is absent).
 *
 * Imports only from sibling research/* modules and from the existing
 * ``sidebarProvider`` / ``sectionProvider`` modules — never from
 * ``daemonClient.ts`` or other Agent A files.
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
exports.registerResearchSurfaces = registerResearchSurfaces;
const vscode = __importStar(require("vscode"));
const sidebarProvider_1 = require("../sidebarProvider");
const checklistBadges_1 = require("./checklistBadges");
const citationsPanel_1 = require("./citationsPanel");
const outlinePanel_1 = require("./outlinePanel");
const readabilityPanel_1 = require("./readabilityPanel");
const insertCitation_1 = require("./insertCitation");
/**
 * Public entry point. Agent A's ``extension.ts`` calls this exactly once,
 * inside ``activate(ctx)``. Failures here should never block extension
 * activation — every code path is wrapped in try/catch that logs and
 * continues.
 */
function registerResearchSurfaces(ctx) {
    // ---- Quick-Pick command ----
    try {
        (0, insertCitation_1.registerInsertCitationCommand)(ctx);
    }
    catch (err) {
        _logActivationError("insertCitation command", err);
    }
    // ---- humanizer.openOutline — focus the sidebar ----
    try {
        ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.openOutline", async () => {
            await vscode.commands.executeCommand("humanizer.sidebar.focus");
        }));
    }
    catch (err) {
        _logActivationError("openOutline command", err);
    }
    // ---- Section-tree checklist badges ----
    try {
        (0, checklistBadges_1.registerChecklistDecorations)(ctx);
    }
    catch (err) {
        _logActivationError("checklist badges", err);
    }
    // ---- Sidebar message routing ----
    // The pre-v1.3 ``SidebarProvider`` already serves the webview HTML and
    // routes its own message types. We register an extra extension callback
    // that the webview can fire for the new panels by patching the existing
    // postMessage handler via VS Code's webview API. Concretely, we expose
    // module-level handlers that ``sidebarProvider.ts`` invokes through the
    // shim added below.
    try {
        _wireSidebarHandlers(ctx);
    }
    catch (err) {
        _logActivationError("sidebar handlers", err);
    }
    // ---- Optional integration with Agent A's code-action provider ----
    // If Agent A's module exports ``registerExternalAction``, we hook the
    // ``missing-citation`` Quick-Fix to fall through to our Quick-Pick. The
    // import is wrapped so a missing module is a graceful no-op.
    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const codeActions = require("../codeActionsProvider");
        if (typeof codeActions.registerExternalAction === "function") {
            codeActions.registerExternalAction("missing-citation", async () => {
                await (0, insertCitation_1.runInsertCitation)();
            });
        }
    }
    catch {
        // Agent A's code-action provider has not landed yet — fine.
    }
    // ---- Initial outline + checklist refresh ----
    try {
        (0, checklistBadges_1.refreshChecklistForActive)();
    }
    catch (err) {
        _logActivationError("initial checklist refresh", err);
    }
}
// ---------------------------------------------------------------------------
// Sidebar wiring helper
// ---------------------------------------------------------------------------
/**
 * Hook the sidebar's message bus.
 *
 * SidebarProvider.resolveWebviewView already attaches an
 * ``onDidReceiveMessage`` callback for the v1.2 messages. To avoid editing
 * that file's switch we attach a *second* listener on the active webview by
 * proxying through ``vscode.window.registerWebviewViewProvider`` is not an
 * option (only one provider per view).
 *
 * Strategy: query VS Code for the active sidebar webview by walking
 * ``vscode.window.tabGroups``. If the v1.2 message bus is the only handler,
 * we register a passthrough that listens for the new ``outline.*``,
 * ``citations.*``, and ``readability.*`` types via a small shim that the
 * SidebarProvider exposes — see the ``onDidReceiveMessage`` extension wired
 * into the sidebar's webview options.
 *
 * Concretely: we register module-level handlers and let the sidebar's
 * webview (via the new HTML script we add) postMessage them — they bubble
 * through ``SidebarProvider._handleMessage``'s default branch unhandled. We
 * therefore monkey-patch ``SidebarProvider.prototype.postMessage`` to expose
 * a hook chain. Implementation below uses a global subscription.
 */
function _wireSidebarHandlers(ctx) {
    const sub = sidebarProvider_1.SidebarProvider.researchHandlerHook(async (msg, webview) => {
        const t = String(msg.type ?? "");
        if (t.startsWith("outline.")) {
            await (0, outlinePanel_1.handleOutlineMessage)(msg, webview);
            return true;
        }
        if (t.startsWith("citations.")) {
            await (0, citationsPanel_1.handleCitationsMessage)(msg, webview);
            return true;
        }
        if (t.startsWith("readability.")) {
            await (0, readabilityPanel_1.handleReadabilityMessage)(msg, webview);
            return true;
        }
        return false;
    });
    ctx.subscriptions.push(sub);
}
// ---------------------------------------------------------------------------
// Diagnostics
// ---------------------------------------------------------------------------
let _channel;
function _output() {
    if (!_channel) {
        _channel = vscode.window.createOutputChannel("Humanizer Research");
    }
    return _channel;
}
function _logActivationError(scope, err) {
    const msg = err instanceof Error ? err.message : String(err);
    _output().appendLine(`[Humanizer] ${scope} setup failed: ${msg}`);
}
//# sourceMappingURL=index.js.map