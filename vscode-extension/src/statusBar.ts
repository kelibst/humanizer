/**
 * statusBar.ts — AI-risk score status bar item.
 *
 * Shows "AI: 0.81 HIGH" (with colour-coded icon) in the right side of the
 * VS Code status bar. Updates on explicit score or when autoScore is enabled
 * and the user saves a .md file.
 */

import * as path from "path";
import * as vscode from "vscode";
import { scoreText, DaemonError } from "./daemonClient";

// ---------------------------------------------------------------------------
// Band colours
// ---------------------------------------------------------------------------

const BAND_ICONS: Record<string, string> = {
  high: "$(circle-large-filled)",
  medium: "$(circle-large-filled)",
  low: "$(circle-large-filled)",
};

const BAND_COLORS: Record<string, vscode.ThemeColor> = {
  high: new vscode.ThemeColor("statusBarItem.errorBackground"),
  medium: new vscode.ThemeColor("statusBarItem.warningBackground"),
  low: new vscode.ThemeColor("statusBarItem.prominentBackground"),
};

// ---------------------------------------------------------------------------
// StatusBarManager
// ---------------------------------------------------------------------------

export class StatusBarManager implements vscode.Disposable {
  private readonly _item: vscode.StatusBarItem;
  private _saveListener: vscode.Disposable | undefined;
  private _inflight = false;
  private _disposables: vscode.Disposable[] = [];
  private _currentFile: string | undefined;

  constructor() {
    this._item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this._item.command = "humanizer.scoreFile";
    this._item.tooltip = "AI-risk score — click to refresh";
    this._showIdle();
    this._item.show();
    this._disposables.push(this._item);

    // Wire auto-score on save if the setting is enabled.
    this._wireAutoScore();

    // Re-wire when settings change.
    const cfgWatcher = vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("humanizer.autoScore")) {
        this._wireAutoScore();
      }
    });
    this._disposables.push(cfgWatcher);
  }

  // -------------------------------------------------------------------------
  // Public methods
  // -------------------------------------------------------------------------

  /** Score the given document and update the status bar. */
  async scoreDocument(document: vscode.TextDocument): Promise<void> {
    if (this._inflight) {
      return; // rate-limit: one inflight request at a time
    }
    if (document.languageId !== "markdown") {
      return;
    }

    this._currentFile = path.basename(document.uri.fsPath);
    this._showBusy();
    this._inflight = true;
    try {
      const cfg = vscode.workspace.getConfiguration("humanizer");
      const profile = cfg.get<string>("profile");
      const result = await scoreText(document.getText(), profile);
      this._showScore(result.score, result.band);
    } catch (err: unknown) {
      // Daemon unreachable — show idle placeholder, do not throw.
      this._showIdle();
      if (err instanceof DaemonError && err.status === 0) {
        // Silently show idle (daemon not started yet)
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.setStatusBarMessage(`Humanizer: ${msg}`, 5000);
      }
    } finally {
      this._inflight = false;
    }
  }

  /** Update the status bar directly from a known score (e.g. after transform). */
  updateScore(score: number, band: "low" | "medium" | "high", fileName?: string): void {
    if (fileName) {
      this._currentFile = fileName;
    }
    this._showScore(score, band);
  }

  /**
   * Idle-path refresh used by the v1.3 diagnostics debounce: score the given
   * text without requiring a save. Respects `humanizer.idleScore` (default
   * `true`) and the same single-inflight rule as `scoreDocument`.
   */
  async refreshFromText(text: string, fileName?: string): Promise<void> {
    const cfg = vscode.workspace.getConfiguration("humanizer");
    if (!cfg.get<boolean>("idleScore", true)) {
      return;
    }
    if (this._inflight) {
      return;
    }
    if (fileName) {
      this._currentFile = fileName;
    }
    this._inflight = true;
    this._showBusy();
    try {
      const profile = cfg.get<string>("profile");
      const result = await scoreText(text, profile);
      this._showScore(result.score, result.band);
    } catch (err: unknown) {
      // Never throw on idle refresh: keep the previous text visible.
      if (err instanceof DaemonError && err.status === 0) {
        this._showIdle();
      }
      // Other errors: silently leave the previous score; toast is hostile on every keystroke.
    } finally {
      this._inflight = false;
    }
  }

  /** Reset to idle (e.g. when no .md file is active). */
  reset(): void {
    this._currentFile = undefined;
    this._showIdle();
  }

  dispose(): void {
    for (const d of this._disposables) {
      d.dispose();
    }
    this._saveListener?.dispose();
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  private _wireAutoScore(): void {
    this._saveListener?.dispose();
    this._saveListener = undefined;

    const cfg = vscode.workspace.getConfiguration("humanizer");
    const autoScore = cfg.get<boolean>("autoScore", true);
    if (!autoScore) {
      return;
    }

    this._saveListener = vscode.workspace.onDidSaveTextDocument(async (doc) => {
      if (doc.languageId !== "markdown") {
        return;
      }
      // Only auto-score if this is the currently visible editor's document.
      const active = vscode.window.activeTextEditor;
      if (!active || active.document !== doc) {
        return;
      }
      await this.scoreDocument(doc);
    });
  }

  private _showIdle(): void {
    this._item.text = "AI: ---";
    this._item.tooltip = "AI-risk score — click to refresh";
    this._item.backgroundColor = undefined;
    this._item.color = undefined;
  }

  private _showBusy(): void {
    this._item.text = "$(sync~spin) AI: …";
    this._item.backgroundColor = undefined;
    this._item.color = undefined;
  }

  private _showScore(score: number, band: string): void {
    const scoreStr = score.toFixed(2);
    const bandUpper = band.toUpperCase();
    const icon = BAND_ICONS[band] ?? "$(circle-outline)";
    this._item.text = `${icon} AI: ${scoreStr} ${bandUpper}`;
    this._item.tooltip = this._currentFile
      ? `AI-risk score for ${this._currentFile} — click to refresh`
      : "AI-risk score — click to refresh";
    this._item.backgroundColor = BAND_COLORS[band];
    this._item.color = undefined;
  }
}
