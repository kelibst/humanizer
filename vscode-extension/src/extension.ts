/**
 * extension.ts — VS Code extension activation / deactivation.
 *
 * Wires all Track A commands, the sidebar, and the status bar.
 * Calls registerSectionCommands(ctx) from Agent B's sectionProcessor
 * inside a try/catch — the extension activates cleanly even if Agent B
 * has not yet been merged.
 */

import * as path from "path";
import * as vscode from "vscode";
import { SidebarProvider } from "./sidebarProvider";
import { StatusBarManager } from "./statusBar";
import {
  scoreText,
  transformText,
  suggestText,
  DaemonError,
} from "./daemonClient";
import { registerDiagnostics } from "./diagnostics";
import { registerHoverProvider } from "./hoverProvider";
import { registerCodeActionsProvider } from "./codeActionsProvider";
import { registerLauncher } from "./launcher";
import { registerWelcome } from "./welcome";
import { openDashboard } from "./dashboard";
import { registerV14ResearchSurfaces } from "./research/v14/index";
import {
  registerActiveEditorTracker,
  getLastMarkdownEditor,
} from "./activeEditorTracker";
import { registerCitationHoverProvider } from "./citationHoverProvider";

// ---------------------------------------------------------------------------
// Suppress self-signed cert errors for the local daemon.
//
// The daemon always uses a self-signed cert. We set the Node environment
// variable so that undici (Node 18 native fetch) skips cert chain verification
// for all outbound requests within this extension host process.
// This is acceptable for a local-only tool; a future version can pin the cert.
// ---------------------------------------------------------------------------
function _patchTls(): void {
  process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";
}

// ---------------------------------------------------------------------------
// activate
// ---------------------------------------------------------------------------

export function activate(ctx: vscode.ExtensionContext): void {
  _patchTls();

  // ---- Active editor tracker (v1.5) ----
  // Register before anything else so _last is seeded from the start.
  try {
    registerActiveEditorTracker(ctx);
  } catch (err) {
    _logSetupError("activeEditorTracker", err);
  }

  // ---- Sidebar ----
  const sidebarProvider = new SidebarProvider(ctx.extensionUri);
  ctx.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      SidebarProvider.VIEW_ID,
      sidebarProvider,
      { webviewOptions: { retainContextWhenHidden: true } }
    )
  );

  // ---- Status bar ----
  const statusBar = new StatusBarManager();
  ctx.subscriptions.push(statusBar);

  // ---- Live feedback (v1.3 Track A) ----
  // Diagnostics own the 2 s debounce; hover + code-actions read from the same
  // collection. The status bar is passed in so the same debounce drives the
  // idle-score refresh (CONTRACT V1_3 §5).
  registerDiagnostics(ctx, statusBar);
  registerHoverProvider(ctx);
  registerCodeActionsProvider(ctx);

  // ---- Citation hover provider (v1.5) ----
  try {
    registerCitationHoverProvider(ctx);
  } catch (err) {
    _logSetupError("citationHoverProvider", err);
  }

  // ---- Track A commands ----

  // humanizer.startDaemon — run `humanize serve` in an integrated terminal.
  ctx.subscriptions.push(
    vscode.commands.registerCommand("humanizer.startDaemon", () => {
      const cfg = vscode.workspace.getConfiguration("humanizer");
      const binaryPath = cfg.get<string>("binaryPath", "humanize");

      // Reuse an existing terminal if one is already open.
      const existingTerminal = vscode.window.terminals.find(
        (t) => t.name === "Humanizer Daemon"
      );
      const terminal =
        existingTerminal ??
        vscode.window.createTerminal({ name: "Humanizer Daemon" });

      terminal.show();
      if (!existingTerminal) {
        terminal.sendText(`${binaryPath} serve`);
      }
    })
  );

  // humanizer.scoreFile — score the active .md file and update the status bar.
  ctx.subscriptions.push(
    vscode.commands.registerCommand("humanizer.scoreFile", async () => {
      const editor = getLastMarkdownEditor() ?? vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== "markdown") {
        vscode.window.showWarningMessage("Open a Markdown file to score.");
        return;
      }

      try {
        const cfg = vscode.workspace.getConfiguration("humanizer");
        const profile = cfg.get<string>("profile");
        const result = await scoreText(editor.document.getText(), profile);
        statusBar.updateScore(result.score, result.band, path.basename(editor.document.uri.fsPath));
        sidebarProvider.postScore(result.score, result.band, result.features);
      } catch (err: unknown) {
        _showError(err);
      }
    })
  );

  // humanizer.transformSelection — transform selected text and replace in editor.
  ctx.subscriptions.push(
    vscode.commands.registerCommand("humanizer.transformSelection", async () => {
      const editor = getLastMarkdownEditor() ?? vscode.window.activeTextEditor;
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
        const profile = cfg.get<string>("profile");
        const backend = cfg.get<string>("backend");
        const includeLlm = cfg.get<boolean>("includeLlm", false);

        const stages = includeLlm
          ? ["prescan", "llm", "determ", "grammar", "postscan"]
          : ["prescan", "determ", "postscan"];

        await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "Humanizer: rewriting selection…",
            cancellable: false,
          },
          async () => {
            const result = await transformText(text, { profile, stages, backend });
            await editor.edit((eb) => {
              eb.replace(selection, result.output);
            });
            statusBar.updateScore(result.post_score, _scoreToBand(result.post_score), path.basename(editor.document.uri.fsPath));
            if (result.notes.length > 0) {
              vscode.window.setStatusBarMessage(`Humanizer: ${result.notes[0]}`, 4000);
            }
          }
        );
      } catch (err: unknown) {
        _showError(err);
      }
    })
  );

  // humanizer.suggestSelection — open sidebar with 3 suggestions for selection.
  ctx.subscriptions.push(
    vscode.commands.registerCommand("humanizer.suggestSelection", async () => {
      const editor = getLastMarkdownEditor() ?? vscode.window.activeTextEditor;
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
        const profile = cfg.get<string>("profile");
        const candidates = await suggestText(text, { n: 3, profile });

        // Focus the sidebar so the user sees the suggestions.
        await vscode.commands.executeCommand("humanizer.sidebar.focus");

        // Push the candidates into the sidebar webview.
        sidebarProvider.postMessage({ type: "suggest", candidates });
      } catch (err: unknown) {
        _showError(err);
      }
    })
  );

  // humanizer.openSettings — open VS Code settings filtered to humanizer.*
  ctx.subscriptions.push(
    vscode.commands.registerCommand("humanizer.openSettings", () => {
      vscode.commands.executeCommand("workbench.action.openSettings", "humanizer");
    })
  );

  // ---- Active editor watcher — auto-score when the user switches to a .md file ----
  const editorWatcher = vscode.window.onDidChangeActiveTextEditor(async (editor) => {
    if (!editor || editor.document.languageId !== "markdown") {
      statusBar.reset();
      return;
    }
    const cfg = vscode.workspace.getConfiguration("humanizer");
    if (cfg.get<boolean>("autoScore", true)) {
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
    const sectionModule = require("./sectionProcessor") as {
      registerSectionCommands?: (ctx: vscode.ExtensionContext) => void;
    };
    if (typeof sectionModule.registerSectionCommands === "function") {
      sectionModule.registerSectionCommands(ctx);
    }
  } catch {
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
    const researchModule = require("./research/index") as {
      registerResearchSurfaces?: (ctx: vscode.ExtensionContext) => void;
    };
    if (typeof researchModule.registerResearchSurfaces === "function") {
      researchModule.registerResearchSurfaces(ctx);
    }
  } catch {
    // Agent B's v1.3 export is not present yet — expected during Round 1.
  }

  // ---- v1.4 surfaces ----
  //
  // Launcher, dashboard, welcome, and the four research-assistant panels.
  // Each registration is independent so a failure in one does not block the
  // others.
  try {
    registerLauncher(ctx);
  } catch (err) {
    _logSetupError("launcher", err);
  }

  try {
    registerWelcome(ctx, sidebarProvider);
  } catch (err) {
    _logSetupError("welcome", err);
  }

  try {
    ctx.subscriptions.push(
      vscode.commands.registerCommand("humanizer.openDashboard", () => {
        openDashboard(ctx);
      })
    );
  } catch (err) {
    _logSetupError("dashboard command", err);
  }

  try {
    registerV14ResearchSurfaces(ctx);
  } catch (err) {
    _logSetupError("v1.4 research surfaces", err);
  }
}

// ---------------------------------------------------------------------------
// deactivate
// ---------------------------------------------------------------------------

export function deactivate(): void {
  // VS Code handles disposables registered via ctx.subscriptions automatically.
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _showError(err: unknown): void {
  const message =
    err instanceof DaemonError
      ? err.message
      : err instanceof Error
      ? err.message
      : String(err);
  vscode.window.showErrorMessage(`Humanizer: ${message}`);
}

function _scoreToBand(score: number): "low" | "medium" | "high" {
  if (score >= 0.67) {
    return "high";
  }
  if (score >= 0.34) {
    return "medium";
  }
  return "low";
}

let _setupChannel: vscode.OutputChannel | undefined;
function _logSetupError(scope: string, err: unknown): void {
  const msg = err instanceof Error ? err.message : String(err);
  if (!_setupChannel) {
    _setupChannel = vscode.window.createOutputChannel("Humanizer");
  }
  _setupChannel.appendLine(`[Humanizer] ${scope} setup failed: ${msg}`);
}
