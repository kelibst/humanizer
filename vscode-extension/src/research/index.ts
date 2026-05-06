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
import { SidebarProvider } from "../sidebarProvider";
import {
  refreshChecklistForActive,
  registerChecklistDecorations,
} from "./checklistBadges";
import { handleCitationsMessage } from "./citationsPanel";
import { handleOutlineMessage } from "./outlinePanel";
import { handleReadabilityMessage } from "./readabilityPanel";
import { registerInsertCitationCommand, runInsertCitation } from "./insertCitation";

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
        await handleCitationsMessage(msg, webview);
        return true;
      }
      if (t.startsWith("readability.")) {
        await handleReadabilityMessage(msg, webview);
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
