/**
 * sidebarProvider.ts — WebviewViewProvider for the Humanizer sidebar.
 *
 * Serves webview/sidebar.html, routes messages from the webview to the
 * daemonClient, and posts results back.
 *
 * Message protocol is defined in plan/VS_CODE_ROADMAP.md §"Message protocol".
 */

import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import {
  scoreText,
  transformText,
  suggestText,
} from "./daemonClient";

// ---------------------------------------------------------------------------
// Types mirroring the webview message protocol
// ---------------------------------------------------------------------------

interface WebviewIncoming {
  // v1.2 message types are listed verbatim; v1.3 research surfaces extend
  // this with their own ``outline.*`` / ``citations.*`` / ``readability.*``
  // shapes. A permissive ``string`` type lets unknown messages flow through
  // ``SidebarProvider._researchHandler`` (registered by Agent B's
  // ``registerResearchSurfaces``) without breaking the v1.2 typed switch.
  type: string;
  includeLlm?: boolean;
  text?: string;
}

// ---------------------------------------------------------------------------
// SidebarProvider
// ---------------------------------------------------------------------------

/**
 * Optional handler used by Agent B's research surfaces to extend the message
 * bus without touching the v1.2 routing. Returns ``true`` to mark the message
 * as handled (so this class skips its default processing), or ``false`` to
 * let it fall through to the v1.2 switch.
 */
export type ResearchMessageHandler = (
  msg: WebviewIncoming & Record<string, unknown>,
  webview: vscode.Webview
) => Promise<boolean> | boolean;

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly VIEW_ID = "humanizer.sidebar";

  // v1.3 research-surface hook (set via ``researchHandlerHook``). Static so
  // ``research/index.ts`` can register the chain before any webview view is
  // resolved without holding a reference to the provider instance.
  private static _researchHandler: ResearchMessageHandler | undefined;

  /**
   * Register a research-surface message handler. Returns a Disposable that
   * clears the hook on disposal — ``research/index.ts`` pushes it into the
   * extension subscriptions so VS Code clears the chain on deactivation.
   */
  public static researchHandlerHook(
    handler: ResearchMessageHandler
  ): vscode.Disposable {
    SidebarProvider._researchHandler = handler;
    return {
      dispose: () => {
        if (SidebarProvider._researchHandler === handler) {
          SidebarProvider._researchHandler = undefined;
        }
      },
    };
  }

  private _view: vscode.WebviewView | undefined;
  private readonly _extensionUri: vscode.Uri;

  constructor(extensionUri: vscode.Uri) {
    this._extensionUri = extensionUri;
  }

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri],
    };

    webviewView.webview.html = this._buildHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (msg: WebviewIncoming & Record<string, unknown>) => {
      // Give the v1.3 research handler first crack at the message. Anything
      // it claims (returns true) is suppressed from the default routing.
      const hook = SidebarProvider._researchHandler;
      if (hook) {
        try {
          const claimed = await hook(msg, webviewView.webview);
          if (claimed) {
            return;
          }
        } catch (err: unknown) {
          // Swallow — research surfaces must not break the sidebar.
          const detail = err instanceof Error ? err.message : String(err);
          webviewView.webview.postMessage({
            type: "error",
            message: `Research panel error: ${detail}`,
          });
          return;
        }
      }
      await this._handleMessage(msg, webviewView.webview);
    });
  }

  // -------------------------------------------------------------------------
  // Public: push any message from outside (e.g. from extension.ts commands)
  // -------------------------------------------------------------------------

  postMessage(msg: Record<string, unknown>): void {
    this._view?.webview.postMessage(msg);
  }

  /** Convenience wrapper for pushing a score update. */
  postScore(score: number, band: "low" | "medium" | "high", features: unknown[]): void {
    this._view?.webview.postMessage({ type: "score", score, band, features });
  }

  // -------------------------------------------------------------------------
  // Message routing
  // -------------------------------------------------------------------------

  private async _handleMessage(
    msg: WebviewIncoming & Record<string, unknown>,
    webview: vscode.Webview
  ): Promise<void> {
    switch (msg.type) {
      case "ready":
        await this._onReady(webview);
        break;

      case "score":
        await this._onScore(webview);
        break;

      case "transform":
        await this._onTransform(webview, msg.includeLlm ?? false);
        break;

      case "suggest":
        await this._onSuggest(webview);
        break;

      case "applyCandidate":
        await this._onApplyCandidate(msg.text ?? "");
        break;

      case "openSettings":
        vscode.commands.executeCommand("humanizer.openSettings");
        break;

      // v1.4 — convenience routings from the sidebar webview.
      case "exportDocx":
        vscode.commands.executeCommand("humanizer.exportDocx");
        break;

      case "openDashboard":
        vscode.commands.executeCommand("humanizer.openDashboard");
        break;

      case "openActions":
        vscode.commands.executeCommand("humanizer.actions");
        break;

      case "llm:run":
        await this._onLlmRun(webview, msg);
        break;

      default:
        break;
    }
  }

  // v1.4 — "Send to backend" relay. Only used by the prompt-output buttons in
  // the four research-assistant panels. We forward the prompt to /v1/llm/run
  // and post the result back so the activity log can echo it.
  private async _onLlmRun(
    webview: vscode.Webview,
    msg: WebviewIncoming & Record<string, unknown>
  ): Promise<void> {
    const prompt =
      typeof msg.prompt === "string" ? (msg.prompt as string) : "";
    if (!prompt.trim()) {
      webview.postMessage({
        type: "llm:run:error",
        message: "Empty prompt.",
      });
      return;
    }
    const cfg = vscode.workspace.getConfiguration("humanizer");
    const backend = cfg.get<string>("backend", "ollama");
    try {
      // Lazy require to avoid a circular import if daemonClient ever pulls
      // sidebar types in the future.
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const dc = require("./daemonClient") as {
        llmRun: (
          p: string,
          b: string,
          m?: string
        ) => Promise<{ output: string; elapsedSeconds: number }>;
      };
      const result = await dc.llmRun(prompt, backend);
      webview.postMessage({
        type: "llm:run:result",
        output: result.output,
        elapsedSeconds: result.elapsedSeconds,
      });
    } catch (err: unknown) {
      const msgText = err instanceof Error ? err.message : String(err);
      webview.postMessage({ type: "llm:run:error", message: msgText });
    }
  }

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  private async _onReady(webview: vscode.Webview): Promise<void> {
    const cfg = vscode.workspace.getConfiguration("humanizer");
    const backend = cfg.get<string>("backend", "ollama");
    webview.postMessage({
      type: "config",
      settings: {
        daemonUrl: cfg.get<string>("daemonUrl", "https://localhost:9999"),
        profile: cfg.get<string>("profile", "default_ghanaian"),
        backend,
        autoScore: cfg.get<boolean>("autoScore", true),
        includeLlm: cfg.get<boolean>("includeLlm", false),
        // ``backendConfigured`` is computed by the v1.4 research surfaces
        // hook, which posts a follow-up ``config`` message with the flag.
        // The webview uses it to show / hide the "Send to backend" buttons.
      },
    });
  }

  private async _onScore(webview: vscode.Webview): Promise<void> {
    const text = this._getActiveText();
    if (text === undefined) {
      webview.postMessage({ type: "error", message: "No active markdown file." });
      return;
    }

    webview.postMessage({ type: "progress", stage: "score", status: "running" });

    try {
      const cfg = vscode.workspace.getConfiguration("humanizer");
      const profile = cfg.get<string>("profile");
      const result = await scoreText(text, profile);
      webview.postMessage({
        type: "score",
        score: result.score,
        band: result.band,
        features: result.features,
      });
    } catch (err: unknown) {
      webview.postMessage({ type: "error", message: this._errMsg(err) });
    }
  }

  private async _onTransform(webview: vscode.Webview, includeLlm: boolean): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
      webview.postMessage({ type: "error", message: "No active markdown file." });
      return;
    }

    const selection = editor.selection;
    const text = selection.isEmpty
      ? editor.document.getText()
      : editor.document.getText(selection);

    if (!text.trim()) {
      webview.postMessage({ type: "error", message: "Nothing to transform." });
      return;
    }

    webview.postMessage({ type: "progress", stage: "transform", status: "running" });

    try {
      const cfg = vscode.workspace.getConfiguration("humanizer");
      const profile = cfg.get<string>("profile");
      const backend = cfg.get<string>("backend");

      const stages = includeLlm
        ? ["prescan", "llm", "determ", "grammar", "postscan"]
        : ["prescan", "determ", "postscan"];

      const result = await transformText(text, { profile, stages, backend });

      webview.postMessage({
        type: "result",
        output: result.output,
        postScore: result.post_score,
        notes: result.notes,
      });

      // Push a score update so the gauge shows the post-score immediately.
      const band = _scoreToBand(result.post_score);
      webview.postMessage({
        type: "score",
        score: result.post_score,
        band,
        features: [],
      });

      // Replace the editor content.
      await editor.edit((eb) => {
        if (selection.isEmpty) {
          const fullRange = new vscode.Range(
            editor.document.positionAt(0),
            editor.document.positionAt(editor.document.getText().length)
          );
          eb.replace(fullRange, result.output);
        } else {
          eb.replace(selection, result.output);
        }
      });
    } catch (err: unknown) {
      webview.postMessage({ type: "error", message: this._errMsg(err) });
    }
  }

  private async _onSuggest(webview: vscode.Webview): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
      webview.postMessage({ type: "error", message: "No active markdown file." });
      return;
    }

    const selection = editor.selection;
    const text = selection.isEmpty
      ? editor.document.getText()
      : editor.document.getText(selection);

    if (!text.trim()) {
      webview.postMessage({
        type: "error",
        message: "Select text to suggest alternatives for.",
      });
      return;
    }

    webview.postMessage({ type: "progress", stage: "suggest", status: "running" });

    try {
      const cfg = vscode.workspace.getConfiguration("humanizer");
      const profile = cfg.get<string>("profile");
      const candidates = await suggestText(text, { n: 3, profile });
      webview.postMessage({ type: "suggest", candidates });
    } catch (err: unknown) {
      webview.postMessage({ type: "error", message: this._errMsg(err) });
    }
  }

  private async _onApplyCandidate(text: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor || !text) {
      return;
    }
    const selection = editor.selection;
    await editor.edit((eb) => {
      if (selection.isEmpty) {
        const fullRange = new vscode.Range(
          editor.document.positionAt(0),
          editor.document.positionAt(editor.document.getText().length)
        );
        eb.replace(fullRange, text);
      } else {
        eb.replace(selection, text);
      }
    });
  }

  // -------------------------------------------------------------------------
  // HTML generation
  // -------------------------------------------------------------------------

  private _buildHtml(webview: vscode.Webview): string {
    // Read the static sidebar.html from the webview directory.
    const htmlPath = path.join(
      this._extensionUri.fsPath,
      "src",
      "webview",
      "sidebar.html"
    );

    // Build a proper webview URI for the CSS file so VS Code serves it securely.
    const cssUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "src", "webview", "sidebar.css")
    );

    let html = fs.readFileSync(htmlPath, "utf8");
    // Substitute the placeholders injected by the template.
    html = html.replace("{{CSS_URI}}", cssUri.toString());
    html = html.replace("{{CSP_SOURCE}}", webview.cspSource);
    return html;
  }

  // -------------------------------------------------------------------------
  // Utilities
  // -------------------------------------------------------------------------

  private _getActiveText(): string | undefined {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
      return undefined;
    }
    return editor.document.getText();
  }

  private _errMsg(err: unknown): string {
    return err instanceof Error ? err.message : String(err);
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _scoreToBand(score: number): "low" | "medium" | "high" {
  if (score >= 0.67) {
    return "high";
  }
  if (score >= 0.34) {
    return "medium";
  }
  return "low";
}
