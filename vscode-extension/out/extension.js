"use strict";
/**
 * extension.ts — VS Code extension activation / deactivation.
 *
 * Wires all Track A commands, the sidebar, and the status bar.
 * Calls registerSectionCommands(ctx) from Agent B's sectionProcessor
 * inside a try/catch — the extension activates cleanly even if Agent B
 * has not yet been merged.
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
exports.activate = activate;
exports.deactivate = deactivate;
const path = __importStar(require("path"));
const vscode = __importStar(require("vscode"));
const sidebarProvider_1 = require("./sidebarProvider");
const statusBar_1 = require("./statusBar");
const daemonClient_1 = require("./daemonClient");
const diagnostics_1 = require("./diagnostics");
const hoverProvider_1 = require("./hoverProvider");
const codeActionsProvider_1 = require("./codeActionsProvider");
const launcher_1 = require("./launcher");
const welcome_1 = require("./welcome");
const dashboard_1 = require("./dashboard");
const index_1 = require("./research/v14/index");
const activeEditorTracker_1 = require("./activeEditorTracker");
const citationHoverProvider_1 = require("./citationHoverProvider");
// ---------------------------------------------------------------------------
// Suppress self-signed cert errors for the local daemon.
//
// The daemon always uses a self-signed cert. We set the Node environment
// variable so that undici (Node 18 native fetch) skips cert chain verification
// for all outbound requests within this extension host process.
// This is acceptable for a local-only tool; a future version can pin the cert.
// ---------------------------------------------------------------------------
function _patchTls() {
    process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";
}
// ---------------------------------------------------------------------------
// activate
// ---------------------------------------------------------------------------
function activate(ctx) {
    _patchTls();
    // ---- Active editor tracker (v1.5) ----
    // Register before anything else so _last is seeded from the start.
    try {
        (0, activeEditorTracker_1.registerActiveEditorTracker)(ctx);
    }
    catch (err) {
        _logSetupError("activeEditorTracker", err);
    }
    // ---- Sidebar ----
    const sidebarProvider = new sidebarProvider_1.SidebarProvider(ctx.extensionUri);
    ctx.subscriptions.push(vscode.window.registerWebviewViewProvider(sidebarProvider_1.SidebarProvider.VIEW_ID, sidebarProvider, { webviewOptions: { retainContextWhenHidden: true } }));
    // ---- Status bar ----
    const statusBar = new statusBar_1.StatusBarManager();
    ctx.subscriptions.push(statusBar);
    // ---- Live feedback (v1.3 Track A) ----
    // Diagnostics own the 2 s debounce; hover + code-actions read from the same
    // collection. The status bar is passed in so the same debounce drives the
    // idle-score refresh (CONTRACT V1_3 §5).
    (0, diagnostics_1.registerDiagnostics)(ctx, statusBar);
    (0, hoverProvider_1.registerHoverProvider)(ctx);
    (0, codeActionsProvider_1.registerCodeActionsProvider)(ctx);
    // ---- Citation hover provider (v1.5) ----
    try {
        (0, citationHoverProvider_1.registerCitationHoverProvider)(ctx);
    }
    catch (err) {
        _logSetupError("citationHoverProvider", err);
    }
    // ---- Track A commands ----
    // humanizer.startDaemon — run `humanize serve` in an integrated terminal.
    ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.startDaemon", async () => {
        // Guard: if the daemon is already reachable (e.g. started by another
        // VS Code instance), do not spawn a second process on the same port.
        try {
            await (0, daemonClient_1.healthCheck)();
            vscode.window.showInformationMessage("Humanizer daemon is already running. No new process started.");
            vscode.window.terminals.find((t) => t.name === "Humanizer Daemon")?.show();
            return;
        }
        catch {
            // Not reachable — proceed to start.
        }
        const cfg = vscode.workspace.getConfiguration("humanizer");
        const binaryPath = cfg.get("binaryPath", "humanize");
        // Reuse an existing terminal if one is already open.
        const existingTerminal = vscode.window.terminals.find((t) => t.name === "Humanizer Daemon");
        const terminal = existingTerminal ??
            vscode.window.createTerminal({ name: "Humanizer Daemon" });
        terminal.show();
        if (!existingTerminal) {
            terminal.sendText(`${binaryPath} serve`);
        }
    }));
    // humanizer.scoreFile — score the active .md file and update the status bar.
    ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.scoreFile", async () => {
        const editor = (0, activeEditorTracker_1.getLastMarkdownEditor)() ?? vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== "markdown") {
            vscode.window.showWarningMessage("Open a Markdown file to score.");
            return;
        }
        try {
            const cfg = vscode.workspace.getConfiguration("humanizer");
            const profile = cfg.get("profile");
            const result = await (0, daemonClient_1.scoreText)(editor.document.getText(), profile);
            statusBar.updateScore(result.score, result.band, path.basename(editor.document.uri.fsPath));
            sidebarProvider.postScore(result.score, result.band, result.features);
        }
        catch (err) {
            _showError(err);
        }
    }));
    // humanizer.transformSelection — transform selected text and replace in editor.
    ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.transformSelection", async () => {
        const editor = (0, activeEditorTracker_1.getLastMarkdownEditor)() ?? vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== "markdown") {
            vscode.window.showWarningMessage("Open a Markdown file to transform.");
            return;
        }
        const selection = editor.selection;
        if (selection.isEmpty) {
            vscode.window.showWarningMessage("Select text to rewrite.");
            return;
        }
        const text = editor.document.getText(selection);
        try {
            const cfg = vscode.workspace.getConfiguration("humanizer");
            const profile = cfg.get("profile");
            const backend = cfg.get("backend");
            const includeLlm = cfg.get("includeLlm", false);
            const stages = includeLlm
                ? ["prescan", "llm", "determ", "grammar", "postscan"]
                : ["prescan", "determ", "postscan"];
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: "Humanizer: rewriting selection…",
                cancellable: false,
            }, async () => {
                const result = await (0, daemonClient_1.transformText)(text, { profile, stages, backend });
                await editor.edit((eb) => {
                    eb.replace(selection, result.output);
                });
                statusBar.updateScore(result.post_score, _scoreToBand(result.post_score), path.basename(editor.document.uri.fsPath));
                if (result.notes.length > 0) {
                    vscode.window.setStatusBarMessage(`Humanizer: ${result.notes[0]}`, 4000);
                }
            });
        }
        catch (err) {
            _showError(err);
        }
    }));
    // humanizer.suggestSelection — open sidebar with 3 suggestions for selection.
    ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.suggestSelection", async () => {
        const editor = (0, activeEditorTracker_1.getLastMarkdownEditor)() ?? vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== "markdown") {
            vscode.window.showWarningMessage("Open a Markdown file to get suggestions.");
            return;
        }
        const selection = editor.selection;
        if (selection.isEmpty) {
            vscode.window.showWarningMessage("Select text to get suggestions for.");
            return;
        }
        const text = editor.document.getText(selection);
        try {
            const cfg = vscode.workspace.getConfiguration("humanizer");
            const profile = cfg.get("profile");
            const candidates = await (0, daemonClient_1.suggestText)(text, { n: 3, profile });
            // Focus the sidebar so the user sees the suggestions.
            await vscode.commands.executeCommand("humanizer.sidebar.focus");
            // Push the candidates into the sidebar webview.
            sidebarProvider.postMessage({ type: "suggest", candidates });
        }
        catch (err) {
            _showError(err);
        }
    }));
    // humanizer.openSettings — open VS Code settings filtered to humanizer.*
    ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.openSettings", () => {
        vscode.commands.executeCommand("workbench.action.openSettings", "humanizer");
    }));
    // ---- Active editor watcher — auto-score when the user switches to a .md file ----
    const editorWatcher = vscode.window.onDidChangeActiveTextEditor(async (editor) => {
        if (!editor || editor.document.languageId !== "markdown") {
            statusBar.reset();
            return;
        }
        const cfg = vscode.workspace.getConfiguration("humanizer");
        if (cfg.get("autoScore", true)) {
            await statusBar.scoreDocument(editor.document);
        }
    });
    ctx.subscriptions.push(editorWatcher);
    // ---- Track B integration (Agent B's registerSectionCommands) ----
    //
    // Wrapped in try/catch — Agent B's sectionProcessor.ts does not exist until
    // round 2. The extension activates cleanly without it; Track B commands remain
    // registered in package.json but will show "command not found" until Agent B
    // ships.
    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const sectionModule = require("./sectionProcessor");
        if (typeof sectionModule.registerSectionCommands === "function") {
            sectionModule.registerSectionCommands(ctx);
        }
    }
    catch {
        // Agent B's module is not present yet — this is expected in round 1.
        // The warning is intentionally low-noise (no console.warn here because
        // VS Code's output channel is the correct mechanism for extension logging,
        // and this is an expected "not yet" state, not an error).
    }
    // ---- Research surfaces (v1.3 Agent B export) ----
    //
    // Same pattern as above: load if present, silently skip otherwise. Agent B
    // ships `vscode-extension/src/research/index.ts` exporting
    // `registerResearchSurfaces(ctx)` — sidebar panels, the
    // `humanizer.insertCitation` Quick-Pick, and section-tree badges.
    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const researchModule = require("./research/index");
        if (typeof researchModule.registerResearchSurfaces === "function") {
            researchModule.registerResearchSurfaces(ctx);
        }
    }
    catch {
        // Agent B's v1.3 export is not present yet — expected during Round 1.
    }
    // ---- v1.4 surfaces ----
    //
    // Launcher, dashboard, welcome, and the four research-assistant panels.
    // Each registration is independent so a failure in one does not block the
    // others.
    try {
        (0, launcher_1.registerLauncher)(ctx);
    }
    catch (err) {
        _logSetupError("launcher", err);
    }
    try {
        (0, welcome_1.registerWelcome)(ctx, sidebarProvider);
    }
    catch (err) {
        _logSetupError("welcome", err);
    }
    try {
        ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.openDashboard", () => {
            (0, dashboard_1.openDashboard)(ctx);
        }));
    }
    catch (err) {
        _logSetupError("dashboard command", err);
    }
    try {
        (0, index_1.registerV14ResearchSurfaces)(ctx);
    }
    catch (err) {
        _logSetupError("v1.4 research surfaces", err);
    }
}
// ---------------------------------------------------------------------------
// deactivate
// ---------------------------------------------------------------------------
function deactivate() {
    // VS Code handles disposables registered via ctx.subscriptions automatically.
}
// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function _showError(err) {
    const message = err instanceof daemonClient_1.DaemonError
        ? err.message
        : err instanceof Error
            ? err.message
            : String(err);
    vscode.window.showErrorMessage(`Humanizer: ${message}`);
}
function _scoreToBand(score) {
    if (score >= 0.67) {
        return "high";
    }
    if (score >= 0.34) {
        return "medium";
    }
    return "low";
}
let _setupChannel;
function _logSetupError(scope, err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (!_setupChannel) {
        _setupChannel = vscode.window.createOutputChannel("Humanizer");
    }
    _setupChannel.appendLine(`[Humanizer] ${scope} setup failed: ${msg}`);
}
//# sourceMappingURL=extension.js.map