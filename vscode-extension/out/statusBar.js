"use strict";
/**
 * statusBar.ts — AI-risk score status bar item.
 *
 * Shows "AI: 0.81 HIGH" (with colour-coded icon) in the right side of the
 * VS Code status bar. Updates on explicit score or when autoScore is enabled
 * and the user saves a .md file.
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
exports.StatusBarManager = void 0;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("./daemonClient");
// ---------------------------------------------------------------------------
// Band colours
// ---------------------------------------------------------------------------
const BAND_ICONS = {
    high: "$(circle-large-filled)",
    medium: "$(circle-large-filled)",
    low: "$(circle-large-filled)",
};
const BAND_COLORS = {
    high: new vscode.ThemeColor("statusBarItem.errorBackground"),
    medium: new vscode.ThemeColor("statusBarItem.warningBackground"),
    low: new vscode.ThemeColor("statusBarItem.prominentBackground"),
};
// ---------------------------------------------------------------------------
// StatusBarManager
// ---------------------------------------------------------------------------
class StatusBarManager {
    constructor() {
        this._inflight = false;
        this._disposables = [];
        this._item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
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
    async scoreDocument(document) {
        if (this._inflight) {
            return; // rate-limit: one inflight request at a time
        }
        if (document.languageId !== "markdown") {
            return;
        }
        this._showBusy();
        this._inflight = true;
        try {
            const cfg = vscode.workspace.getConfiguration("humanizer");
            const profile = cfg.get("profile");
            const result = await (0, daemonClient_1.scoreText)(document.getText(), profile);
            this._showScore(result.score, result.band);
        }
        catch (err) {
            // Daemon unreachable — show idle placeholder, do not throw.
            this._showIdle();
            if (err instanceof daemonClient_1.DaemonError && err.status === 0) {
                // Silently show idle (daemon not started yet)
            }
            else {
                const msg = err instanceof Error ? err.message : String(err);
                vscode.window.setStatusBarMessage(`Humanizer: ${msg}`, 5000);
            }
        }
        finally {
            this._inflight = false;
        }
    }
    /** Update the status bar directly from a known score (e.g. after transform). */
    updateScore(score, band) {
        this._showScore(score, band);
    }
    /**
     * Idle-path refresh used by the v1.3 diagnostics debounce: score the given
     * text without requiring a save. Respects `humanizer.idleScore` (default
     * `true`) and the same single-inflight rule as `scoreDocument`.
     */
    async refreshFromText(text) {
        const cfg = vscode.workspace.getConfiguration("humanizer");
        if (!cfg.get("idleScore", true)) {
            return;
        }
        if (this._inflight) {
            return;
        }
        this._inflight = true;
        this._showBusy();
        try {
            const profile = cfg.get("profile");
            const result = await (0, daemonClient_1.scoreText)(text, profile);
            this._showScore(result.score, result.band);
        }
        catch (err) {
            // Never throw on idle refresh: keep the previous text visible.
            if (err instanceof daemonClient_1.DaemonError && err.status === 0) {
                this._showIdle();
            }
            // Other errors: silently leave the previous score; toast is hostile on every keystroke.
        }
        finally {
            this._inflight = false;
        }
    }
    /** Reset to idle (e.g. when no .md file is active). */
    reset() {
        this._showIdle();
    }
    dispose() {
        for (const d of this._disposables) {
            d.dispose();
        }
        this._saveListener?.dispose();
    }
    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------
    _wireAutoScore() {
        this._saveListener?.dispose();
        this._saveListener = undefined;
        const cfg = vscode.workspace.getConfiguration("humanizer");
        const autoScore = cfg.get("autoScore", true);
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
    _showIdle() {
        this._item.text = "AI: ---";
        this._item.backgroundColor = undefined;
        this._item.color = undefined;
    }
    _showBusy() {
        this._item.text = "$(sync~spin) AI: …";
        this._item.backgroundColor = undefined;
        this._item.color = undefined;
    }
    _showScore(score, band) {
        const scoreStr = score.toFixed(2);
        const bandUpper = band.toUpperCase();
        const icon = BAND_ICONS[band] ?? "$(circle-outline)";
        this._item.text = `${icon} AI: ${scoreStr} ${bandUpper}`;
        this._item.backgroundColor = BAND_COLORS[band];
        // Reset any explicit foreground colour — the background colour sets the theme.
        this._item.color = undefined;
    }
}
exports.StatusBarManager = StatusBarManager;
//# sourceMappingURL=statusBar.js.map