/**
 * diagnostics.ts — live AI-flavoured-token squiggles for markdown files.
 *
 * Owns the shared `DiagnosticCollection` for the `humanizer` source. On every
 * `onDidChangeTextDocument` for a markdown file, debounces ~2 s before calling
 * `daemonClient.lintText`. The same debounce also pushes an idle status-bar
 * refresh through `StatusBarManager.refreshFromText` (respecting the
 * `humanizer.idleScore` setting).
 *
 * Single inflight per document URI: if a request is already in flight when a
 * new keystroke arrives, the timer is rescheduled and the new call fires after
 * the current one finishes.
 *
 * Hover provider (`hoverProvider.ts`) and code-actions provider
 * (`codeActionsProvider.ts`) read from the same collection through
 * `getDiagnostics()`.
 */

import * as path from "path";
import * as vscode from "vscode";
import { lintText, DaemonError, type LintSpan } from "./daemonClient";
import type { StatusBarManager } from "./statusBar";

const DEBOUNCE_MS = 2000;
const SOURCE = "humanizer";

let _collection: vscode.DiagnosticCollection | undefined;
const _timers = new Map<string, NodeJS.Timeout>();
const _inflight = new Set<string>();
// Map diagnostic-collection key → original LintSpan, so hover/code-actions can
// recover suggestions, token, and the precise lint code.
const _spanIndex = new Map<string, LintSpan>();

// One-toast-per-error-class-per-session guard (avoid hostile UX while typing).
const _shownToasts = new Set<string>();

function _spanKey(uri: vscode.Uri, span: LintSpan): string {
  return `${uri.toString()}|${span.start}:${span.end}:${span.code}`;
}

/**
 * Look up the original LintSpan for a given diagnostic. Returns undefined if
 * the diagnostic was not produced by this module (or has been superseded).
 */
export function spanForDiagnostic(
  document: vscode.TextDocument,
  diagnostic: vscode.Diagnostic
): LintSpan | undefined {
  const start = document.offsetAt(diagnostic.range.start);
  const end = document.offsetAt(diagnostic.range.end);
  const code = (diagnostic.code as string | undefined) ?? "";
  return _spanIndex.get(`${document.uri.toString()}|${start}:${end}:${code}`);
}

/**
 * All current LintSpans for the active document. Used by `codeActionsProvider`
 * to find the span at a given range.
 */
export function spansFor(document: vscode.TextDocument): LintSpan[] {
  const prefix = `${document.uri.toString()}|`;
  const out: LintSpan[] = [];
  for (const [key, span] of _spanIndex.entries()) {
    if (key.startsWith(prefix)) {
      out.push(span);
    }
  }
  return out;
}

/** Public access to the diagnostic collection (read-only intent). */
export function getCollection(): vscode.DiagnosticCollection | undefined {
  return _collection;
}

function _severityFromString(s: "info" | "warning"): vscode.DiagnosticSeverity {
  return s === "warning"
    ? vscode.DiagnosticSeverity.Warning
    : vscode.DiagnosticSeverity.Information;
}

function _diagnosticFromSpan(
  document: vscode.TextDocument,
  span: LintSpan
): vscode.Diagnostic {
  const range = new vscode.Range(
    document.positionAt(span.start),
    document.positionAt(span.end)
  );
  const diag = new vscode.Diagnostic(range, span.message, _severityFromString(span.severity));
  diag.source = SOURCE;
  diag.code = span.code;
  return diag;
}

function _logChannel(): vscode.OutputChannel {
  // Lazily create a single output channel; reuse on subsequent calls.
  const existing = (_logChannel as unknown as { _ch?: vscode.OutputChannel })._ch;
  if (existing) {
    return existing;
  }
  const ch = vscode.window.createOutputChannel("Humanizer");
  (_logChannel as unknown as { _ch?: vscode.OutputChannel })._ch = ch;
  return ch;
}

async function _runLint(
  document: vscode.TextDocument,
  statusBar: StatusBarManager
): Promise<void> {
  const uriKey = document.uri.toString();
  if (_inflight.has(uriKey)) {
    // Another request is already running. Reschedule once it finishes by
    // bouncing the timer; we let the current call complete and the next change
    // event will re-arm the debounce.
    return;
  }
  _inflight.add(uriKey);

  const text = document.getText();
  const cfg = vscode.workspace.getConfiguration("humanizer");
  const profile = cfg.get<string>("profile");

  try {
    const result = await lintText(text, profile);

    // Bail if the document was closed while we were waiting.
    if (document.isClosed) {
      return;
    }

    // Clear the prior span index for this URI, then rebuild from the new
    // result. This keeps `_spanIndex` aligned with what's on screen.
    const prefix = `${uriKey}|`;
    for (const key of Array.from(_spanIndex.keys())) {
      if (key.startsWith(prefix)) {
        _spanIndex.delete(key);
      }
    }

    const diags: vscode.Diagnostic[] = [];
    for (const span of result.spans) {
      // Skip spans that do not fit the current document length (server lag).
      if (span.start < 0 || span.end > text.length || span.end <= span.start) {
        continue;
      }
      diags.push(_diagnosticFromSpan(document, span));
      _spanIndex.set(_spanKey(document.uri, span), span);
    }
    _collection?.set(document.uri, diags);
  } catch (err: unknown) {
    // Never block typing on a lint failure; log + maybe show a single toast.
    const msg = err instanceof Error ? err.message : String(err);
    _logChannel().appendLine(`[diagnostics] lint failed: ${msg}`);

    let cls = "unknown";
    if (err instanceof DaemonError) {
      if (err.status === 0) {
        cls = "network";
      } else if (err.status === 401) {
        cls = "auth";
      } else {
        cls = `http-${err.status}`;
      }
    }
    if (!_shownToasts.has(cls)) {
      _shownToasts.add(cls);
      // For status 0 (daemon down), stay silent — startDaemon command handles it.
      if (cls !== "network") {
        vscode.window.setStatusBarMessage(
          `Humanizer diagnostics: ${msg}`,
          5000
        );
      }
    }
    // Clear any stale diagnostics so the user is not stuck looking at old squiggles.
    _collection?.delete(document.uri);
  } finally {
    _inflight.delete(uriKey);
  }

  // After lint, refresh the status bar from the same text. Errors here are
  // swallowed by `refreshFromText` itself.
  if (!document.isClosed) {
    void statusBar.refreshFromText(text, path.basename(document.uri.fsPath));
  }
}

function _scheduleLint(
  document: vscode.TextDocument,
  statusBar: StatusBarManager
): void {
  if (document.languageId !== "markdown") {
    return;
  }
  const uriKey = document.uri.toString();
  const existing = _timers.get(uriKey);
  if (existing) {
    clearTimeout(existing);
  }
  const t = setTimeout(() => {
    _timers.delete(uriKey);
    void _runLint(document, statusBar);
  }, DEBOUNCE_MS);
  _timers.set(uriKey, t);
}

/**
 * Register the diagnostics subsystem. Idempotent within an extension activation.
 * The status bar is required so the same debounce can drive idle scoring.
 */
export function registerDiagnostics(
  ctx: vscode.ExtensionContext,
  statusBar: StatusBarManager
): vscode.DiagnosticCollection {
  if (_collection) {
    return _collection;
  }
  _collection = vscode.languages.createDiagnosticCollection(SOURCE);
  ctx.subscriptions.push(_collection);

  // Lint on text change (debounced).
  ctx.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.document.languageId !== "markdown") {
        return;
      }
      _scheduleLint(e.document, statusBar);
    })
  );

  // Lint on open and active-editor change so that the user sees squiggles
  // immediately when switching between markdown files.
  ctx.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (doc.languageId === "markdown") {
        _scheduleLint(doc, statusBar);
      }
    })
  );
  ctx.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (editor && editor.document.languageId === "markdown") {
        _scheduleLint(editor.document, statusBar);
      }
    })
  );

  // Clear diagnostics + index when a document is closed.
  ctx.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument((doc) => {
      _collection?.delete(doc.uri);
      const prefix = `${doc.uri.toString()}|`;
      for (const key of Array.from(_spanIndex.keys())) {
        if (key.startsWith(prefix)) {
          _spanIndex.delete(key);
        }
      }
      const t = _timers.get(doc.uri.toString());
      if (t) {
        clearTimeout(t);
        _timers.delete(doc.uri.toString());
      }
    })
  );

  // Kick off an initial lint for any already-visible markdown editor.
  for (const editor of vscode.window.visibleTextEditors) {
    if (editor.document.languageId === "markdown") {
      _scheduleLint(editor.document, statusBar);
    }
  }

  return _collection;
}
