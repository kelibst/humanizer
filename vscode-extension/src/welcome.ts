/**
 * welcome.ts — first-launch onboarding for the Humanizer extension.
 *
 * Posts a `welcome:show` message to the sidebar webview on the first
 * activation per VS Code profile. Gated by
 * ``globalState.get("humanizer.firstLaunchSeen") === true``; flips the flag
 * once the user dismisses (the webview posts ``welcome:dismissed``).
 *
 * Pure TypeScript — no Python dependency, no daemon dependency. The webview
 * renders 4 onboarding cards using existing CSS variables; this module is
 * just the activation/dismiss bookkeeping plus the explicit reopen command.
 */

import * as vscode from "vscode";
import { SidebarProvider } from "./sidebarProvider";

const FLAG_KEY = "humanizer.firstLaunchSeen";

/**
 * Module-level singleton so we can post the welcome message after the
 * sidebar has actually been resolved (the webview is created lazily). The
 * sidebar provider holds a reference; we get its instance via the optional
 * `sidebarRef` argument.
 */
let _sidebar: SidebarProvider | undefined;

/**
 * Register first-launch logic + ``humanizer.openWelcome`` command.
 *
 * Wiring (called from extension.ts::activate):
 *   1. ``registerWelcome(ctx, sidebar)`` — passes the SidebarProvider so we can
 *      target the webview.
 *   2. On first launch, schedules the ``welcome:show`` message after the
 *      sidebar has time to resolve. If the sidebar is not yet visible, the
 *      message is queued and replayed once the webview boots (the webview
 *      posts ``ready`` on load — see _replayOnReady).
 *   3. Listens for ``welcome:dismissed`` from the webview and flips the flag.
 *   4. Registers ``humanizer.openWelcome`` so the user can reopen onboarding.
 */
export function registerWelcome(
  ctx: vscode.ExtensionContext,
  sidebar: SidebarProvider
): void {
  _sidebar = sidebar;

  // Listen for the dismiss message via the research-handler hook chain. We
  // accept any message whose `type` starts with "welcome:" — the only one
  // we currently care about is "welcome:dismissed".
  const sub = SidebarProvider.researchHandlerHook(async (msg) => {
    const t = String((msg as { type?: unknown }).type ?? "");
    if (t === "welcome:dismissed") {
      await ctx.globalState.update(FLAG_KEY, true);
      return true;
    }
    if (t === "ready") {
      // Re-emit welcome on ready if first-launch is still pending — the
      // webview may have just (re-)booted and missed our earlier post.
      if (!ctx.globalState.get<boolean>(FLAG_KEY, false)) {
        // Defer slightly so the sidebar's own `ready` handler runs first
        // (it sends the `config` event the webview wires before showing
        // welcome cards).
        setTimeout(() => _postWelcome(false), 60);
      }
      // Don't claim — the v1.2 sidebar handler still needs to handle ready.
      return false;
    }
    return false;
  });
  ctx.subscriptions.push(sub);

  // First-launch trigger.
  const seen = ctx.globalState.get<boolean>(FLAG_KEY, false);
  if (!seen) {
    // The sidebar webview may not have been resolved yet; the `ready`
    // listener above will replay if so.
    setTimeout(() => _postWelcome(false), 200);
  }

  // ``humanizer.openWelcome`` — explicit reopen via Command Palette.
  ctx.subscriptions.push(
    vscode.commands.registerCommand("humanizer.openWelcome", async () => {
      // Focus the sidebar so the cards are visible.
      try {
        await vscode.commands.executeCommand("humanizer.sidebar.focus");
      } catch {
        // If the focus command isn't available, fall back to revealing
        // the activity-bar container.
        try {
          await vscode.commands.executeCommand(
            "workbench.view.extension.humanizer"
          );
        } catch {
          // ignore
        }
      }
      _postWelcome(true);
    })
  );
}

function _postWelcome(force: boolean): void {
  if (!_sidebar) {
    return;
  }
  _sidebar.postMessage({ type: "welcome:show", force });
}
