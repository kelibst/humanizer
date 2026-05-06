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

import * as vscode from "vscode";
import { SidebarProvider } from "../../sidebarProvider";
import { handleStudyStarter } from "./studyStarter";
import { handleInspector } from "./inspector";
import { handleTemplates } from "./templateLibrary";
import { handleReviewer } from "./reviewer";

/**
 * Public entry point — called once from extension.ts during activate().
 */
export function registerV14ResearchSurfaces(
  ctx: vscode.ExtensionContext
): void {
  const sub = SidebarProvider.researchHandlerHook(async (msg, webview) => {
    const t = String((msg as { type?: unknown }).type ?? "");

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
        } catch {
          // ignore
        }
      }, 30);
      return false;
    }

    if (t.startsWith("studyStarter:")) {
      if (t === "studyStarter:run") {
        await handleStudyStarter(msg, webview);
      }
      return true;
    }
    if (t.startsWith("inspector:")) {
      if (t === "inspector:run") {
        await handleInspector(msg, webview);
      }
      return true;
    }
    if (t.startsWith("templates:")) {
      if (t === "templates:open") {
        await handleTemplates(msg, webview);
      }
      return true;
    }
    if (t.startsWith("reviewer:")) {
      if (t === "reviewer:run") {
        await handleReviewer(msg, webview);
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
function _backendConfigured(): boolean {
  const cfg = vscode.workspace.getConfiguration("humanizer");
  const backend = cfg.get<string>("backend", "ollama");
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
    const v = cfg.get<string>(k);
    if (typeof v === "string" && v.trim()) {
      return true;
    }
  }
  return false;
}
