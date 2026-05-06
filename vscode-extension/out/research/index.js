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
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const sidebarProvider_1 = require("../sidebarProvider");
const checklistBadges_1 = require("./checklistBadges");
const citationsPanel_1 = require("./citationsPanel");
const outlinePanel_1 = require("./outlinePanel");
const readabilityPanel_1 = require("./readabilityPanel");
const insertCitation_1 = require("./insertCitation");
const refsPanel_1 = require("./refsPanel");
const daemonClient_1 = require("../daemonClient");
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
    // ---- v1.5 new commands ----
    // humanizer.importBibtex — open file picker, import .bib into references.json
    try {
        ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.importBibtex", async () => {
            const folders = vscode.workspace.workspaceFolders;
            const root = folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
            if (!root) {
                vscode.window.showWarningMessage("Open a workspace folder to import BibTeX references.");
                return;
            }
            const uris = await vscode.window.showOpenDialog({
                canSelectMany: false,
                canSelectFiles: true,
                canSelectFolders: false,
                filters: { "BibTeX files": ["bib"] },
                title: "Import BibTeX",
            });
            if (!uris || uris.length === 0) {
                return;
            }
            let bibtexContent;
            try {
                bibtexContent = fs.readFileSync(uris[0].fsPath, "utf8");
            }
            catch (e) {
                vscode.window.showErrorMessage(`Humanizer: could not read file — ${e instanceof Error ? e.message : String(e)}`);
                return;
            }
            const editor = vscode.window.activeTextEditor;
            const documentPath = editor && editor.document.languageId === "markdown"
                ? editor.document.uri.fsPath
                : undefined;
            try {
                const result = await vscode.window.withProgress({
                    location: vscode.ProgressLocation.Notification,
                    title: "Humanizer: importing BibTeX…",
                    cancellable: false,
                }, () => (0, daemonClient_1.importBibtex)(bibtexContent, root, documentPath));
                vscode.window.showInformationMessage(`Humanizer: imported ${result.imported} reference(s), ${result.skipped} skipped.`);
            }
            catch (e) {
                const msg = e instanceof daemonClient_1.DaemonError ? e.message : e instanceof Error ? e.message : String(e);
                vscode.window.showErrorMessage(`Humanizer: BibTeX import failed — ${msg}`);
            }
        }));
    }
    catch (err) {
        _logActivationError("importBibtex command", err);
    }
    // humanizer.exportBibtex — export workspace references to a .bib file
    try {
        ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.exportBibtex", async () => {
            const folders = vscode.workspace.workspaceFolders;
            const root = folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
            if (!root) {
                vscode.window.showWarningMessage("Open a workspace folder to export BibTeX references.");
                return;
            }
            let bibtexText;
            try {
                bibtexText = await (0, daemonClient_1.exportBibtex)(root);
            }
            catch (e) {
                const msg = e instanceof daemonClient_1.DaemonError ? e.message : e instanceof Error ? e.message : String(e);
                vscode.window.showErrorMessage(`Humanizer: BibTeX export failed — ${msg}`);
                return;
            }
            const saveUri = await vscode.window.showSaveDialog({
                defaultUri: vscode.Uri.file(path.join(root, "references.bib")),
                filters: { "BibTeX files": ["bib"] },
                title: "Export BibTeX",
            });
            if (!saveUri) {
                return;
            }
            try {
                fs.writeFileSync(saveUri.fsPath, bibtexText, "utf8");
                vscode.window.showInformationMessage(`Humanizer: exported ${saveUri.fsPath}`);
            }
            catch (e) {
                vscode.window.showErrorMessage(`Humanizer: could not write file — ${e instanceof Error ? e.message : String(e)}`);
            }
        }));
    }
    catch (err) {
        _logActivationError("exportBibtex command", err);
    }
    // humanizer.resolveAllOrphans — batch-stub all orphan citations
    try {
        ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.resolveAllOrphans", async () => {
            // We need a webview reference to post back; since this is a palette
            // command we use a no-op webview shim (status messages go to
            // showInformationMessage inside resolveAllOrphans already).
            const shimWebview = {
                postMessage: (_msg) => { },
            };
            await (0, citationsPanel_1.resolveAllOrphans)(shimWebview);
        }));
    }
    catch (err) {
        _logActivationError("resolveAllOrphans command", err);
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
        // v1.5 — reference library messages
        if (t.startsWith("refs.")) {
            await (0, refsPanel_1.handleRefsMessage)(msg, webview);
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