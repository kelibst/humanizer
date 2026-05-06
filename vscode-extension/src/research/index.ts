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

import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { SidebarProvider } from "../sidebarProvider";
import {
  refreshChecklistForActive,
  registerChecklistDecorations,
} from "./checklistBadges";
import {
  handleCitationsMessage,
  resolveAllOrphans,
} from "./citationsPanel";
import { handleOutlineMessage } from "./outlinePanel";
import { handleReadabilityMessage } from "./readabilityPanel";
import { registerInsertCitationCommand, runInsertCitation } from "./insertCitation";
import { handleRefsMessage } from "./refsPanel";
import {
  importBibtex,
  exportBibtex,
  DaemonError,
} from "../daemonClient";

/**
 * Public entry point. Agent A's ``extension.ts`` calls this exactly once,
 * inside ``activate(ctx)``. Failures here should never block extension
 * activation — every code path is wrapped in try/catch that logs and
 * continues.
 */
export function registerResearchSurfaces(
  ctx: vscode.ExtensionContext
): void {
  // ---- Quick-Pick command ----
  try {
    registerInsertCitationCommand(ctx);
  } catch (err: unknown) {
    _logActivationError("insertCitation command", err);
  }

  // ---- humanizer.openOutline — focus the sidebar ----
  try {
    ctx.subscriptions.push(
      vscode.commands.registerCommand("humanizer.openOutline", async () => {
        await vscode.commands.executeCommand("humanizer.sidebar.focus");
      })
    );
  } catch (err: unknown) {
    _logActivationError("openOutline command", err);
  }

  // ---- v1.5 new commands ----

  // humanizer.importBibtex — open file picker, import .bib into references.json
  try {
    ctx.subscriptions.push(
      vscode.commands.registerCommand("humanizer.importBibtex", async () => {
        const folders = vscode.workspace.workspaceFolders;
        const root = folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
        if (!root) {
          vscode.window.showWarningMessage(
            "Open a workspace folder to import BibTeX references."
          );
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
        let bibtexContent: string;
        try {
          bibtexContent = fs.readFileSync(uris[0].fsPath, "utf8");
        } catch (e: unknown) {
          vscode.window.showErrorMessage(`Humanizer: could not read file — ${e instanceof Error ? e.message : String(e)}`);
          return;
        }
        const editor = vscode.window.activeTextEditor;
        const documentPath =
          editor && editor.document.languageId === "markdown"
            ? editor.document.uri.fsPath
            : undefined;
        try {
          const result = await vscode.window.withProgress(
            {
              location: vscode.ProgressLocation.Notification,
              title: "Humanizer: importing BibTeX…",
              cancellable: false,
            },
            () => importBibtex(bibtexContent, root, documentPath)
          );
          vscode.window.showInformationMessage(
            `Humanizer: imported ${result.imported} reference(s), ${result.skipped} skipped.`
          );
        } catch (e: unknown) {
          const msg = e instanceof DaemonError ? e.message : e instanceof Error ? e.message : String(e);
          vscode.window.showErrorMessage(`Humanizer: BibTeX import failed — ${msg}`);
        }
      })
    );
  } catch (err: unknown) {
    _logActivationError("importBibtex command", err);
  }

  // humanizer.exportBibtex — export workspace references to a .bib file
  try {
    ctx.subscriptions.push(
      vscode.commands.registerCommand("humanizer.exportBibtex", async () => {
        const folders = vscode.workspace.workspaceFolders;
        const root = folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
        if (!root) {
          vscode.window.showWarningMessage(
            "Open a workspace folder to export BibTeX references."
          );
          return;
        }
        let bibtexText: string;
        try {
          bibtexText = await exportBibtex(root);
        } catch (e: unknown) {
          const msg = e instanceof DaemonError ? e.message : e instanceof Error ? e.message : String(e);
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
        } catch (e: unknown) {
          vscode.window.showErrorMessage(`Humanizer: could not write file — ${e instanceof Error ? e.message : String(e)}`);
        }
      })
    );
  } catch (err: unknown) {
    _logActivationError("exportBibtex command", err);
  }

  // humanizer.resolveAllOrphans — batch-stub all orphan citations
  try {
    ctx.subscriptions.push(
      vscode.commands.registerCommand("humanizer.resolveAllOrphans", async () => {
        // We need a webview reference to post back; since this is a palette
        // command we use a no-op webview shim (status messages go to
        // showInformationMessage inside resolveAllOrphans already).
        const shimWebview = {
          postMessage: (_msg: unknown) => { /* no-op for palette invocation */ },
        } as unknown as vscode.Webview;
        await resolveAllOrphans(shimWebview);
      })
    );
  } catch (err: unknown) {
    _logActivationError("resolveAllOrphans command", err);
  }

  // ---- Section-tree checklist badges ----
  try {
    registerChecklistDecorations(ctx);
  } catch (err: unknown) {
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
  } catch (err: unknown) {
    _logActivationError("sidebar handlers", err);
  }

  // ---- Optional integration with Agent A's code-action provider ----
  // If Agent A's module exports ``registerExternalAction``, we hook the
  // ``missing-citation`` Quick-Fix to fall through to our Quick-Pick. The
  // import is wrapped so a missing module is a graceful no-op.
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const codeActions = require("../codeActionsProvider") as {
      registerExternalAction?: (
        code: string,
        handler: () => Promise<void> | void
      ) => void;
    };
    if (typeof codeActions.registerExternalAction === "function") {
      codeActions.registerExternalAction("missing-citation", async () => {
        await runInsertCitation();
      });
    }
  } catch {
    // Agent A's code-action provider has not landed yet — fine.
  }

  // ---- Initial outline + checklist refresh ----
  try {
    refreshChecklistForActive();
  } catch (err: unknown) {
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
function _wireSidebarHandlers(ctx: vscode.ExtensionContext): void {
  const sub = SidebarProvider.researchHandlerHook(
    async (msg, webview) => {
      const t = String((msg as { type?: unknown }).type ?? "");
      if (t.startsWith("outline.")) {
        await handleOutlineMessage(msg, webview);
        return true;
      }
      if (t.startsWith("citations.")) {
        await handleCitationsMessage(
          msg as { type: string; start?: number; end?: number; key?: string },
          webview
        );
        return true;
      }
      if (t.startsWith("readability.")) {
        await handleReadabilityMessage(msg, webview);
        return true;
      }
      // v1.5 — reference library messages
      if (t.startsWith("refs.")) {
        await handleRefsMessage(msg, webview);
        return true;
      }
      return false;
    }
  );
  ctx.subscriptions.push(sub);
}

// ---------------------------------------------------------------------------
// Diagnostics
// ---------------------------------------------------------------------------

let _channel: vscode.OutputChannel | undefined;
function _output(): vscode.OutputChannel {
  if (!_channel) {
    _channel = vscode.window.createOutputChannel("Humanizer Research");
  }
  return _channel;
}

function _logActivationError(scope: string, err: unknown): void {
  const msg = err instanceof Error ? err.message : String(err);
  _output().appendLine(`[Humanizer] ${scope} setup failed: ${msg}`);
}
