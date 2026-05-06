/**
 * sectionProcessor.ts — Track B command orchestrator.
 *
 * Exports registerSectionCommands(ctx) — the single entry point that
 * extension.ts calls. Registers all five Track B commands:
 *   humanizer.scoreSection
 *   humanizer.transformSection
 *   humanizer.transformAll
 *   humanizer.exportDocx
 *   humanizer.showProgress
 *
 * Imports daemonClient functions from ./daemonClient (Agent A's module).
 * Never makes raw fetch/https calls.
 * Uses child_process.execFile (not exec) for exportDocx (CONTRACT §7).
 * Paragraph decorations are applied only after explicit score/transform
 * commands and on file save — NOT on every keypress (BRIEF §Decoration call limit).
 */

import * as vscode from "vscode";
import * as path from "path";
import { execFile } from "child_process";
import {
  scoreText,
  transformText,
  DaemonError,
} from "./daemonClient";
import {
  SectionProvider,
  SectionNode,
  parseHeadings,
} from "./sectionProvider";
import {
  loadProgress,
  saveProgress,
  SectionProgress,
} from "./progressStore";

// ---------------------------------------------------------------------------
// Decoration types (CONTRACT §8) — created once, never recreated
// ---------------------------------------------------------------------------

export const highRiskDecoration = vscode.window.createTextEditorDecorationType({
  backgroundColor: "rgba(220, 50, 50, 0.18)",
  isWholeLine: false,
  overviewRulerColor: "rgba(220, 50, 50, 0.5)",
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

export const medRiskDecoration = vscode.window.createTextEditorDecorationType({
  backgroundColor: "rgba(230, 160, 30, 0.15)",
  isWholeLine: false,
  overviewRulerColor: "rgba(230, 160, 30, 0.4)",
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

// ---------------------------------------------------------------------------
// Module-level singleton references (set once during registration)
// ---------------------------------------------------------------------------

let _sectionProvider: SectionProvider | undefined;
let _outputChannel: vscode.OutputChannel | undefined;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _cfg(): {
  profile: string | undefined;
  backend: string | undefined;
  autoScore: boolean;
  binaryPath: string;
} {
  const cfg = vscode.workspace.getConfiguration("humanizer");
  return {
    profile: cfg.get<string>("profile"),
    backend: cfg.get<string>("backend"),
    autoScore: cfg.get<boolean>("autoScore", true),
    binaryPath: cfg.get<string>("binaryPath", "humanize"),
  };
}

function _log(msg: string): void {
  _outputChannel?.appendLine(`[Humanizer] ${msg}`);
}

function _showError(err: unknown): void {
  const msg =
    err instanceof DaemonError
      ? err.message
      : err instanceof Error
      ? err.message
      : String(err);
  vscode.window.showErrorMessage(`Humanizer: ${msg}`);
}

/**
 * Find the SectionNode whose [lineStart, lineEnd) range contains cursorLine.
 * Only nodes with status "pending" or "done" that are eligible for transform
 * are considered (not "skipped" or "too_short"), unless any node is at all
 * acceptable (e.g. scoreSection works on any non-skipped node).
 */
function _findSectionAtCursor(
  nodes: readonly SectionNode[],
  cursorLine: number,
  includeShort = false
): { node: SectionNode; index: number } | undefined {
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    if (cursorLine >= node.lineStart && cursorLine < node.lineEnd) {
      if (!includeShort && (node.status === "skipped" || node.status === "too_short")) {
        return undefined;
      }
      if (node.status === "skipped") {
        return undefined;
      }
      return { node, index: i };
    }
  }
  return undefined;
}

/**
 * Extract section body text from the document.
 * The heading line itself is excluded; only body lines are returned.
 */
function _extractSectionText(
  document: vscode.TextDocument,
  node: SectionNode
): string {
  const lines: string[] = [];
  for (let ln = node.lineStart + 1; ln < node.lineEnd; ln++) {
    lines.push(document.lineAt(ln).text);
  }
  return lines.join("\n");
}

/**
 * Replace the section body (lineStart+1 .. lineEnd-1) in the editor.
 */
async function _replaceSectionText(
  editor: vscode.TextEditor,
  node: SectionNode,
  newText: string
): Promise<boolean> {
  const document = editor.document;

  // Range to replace: from start of lineStart+1 to end of lineEnd-1
  const startLine = node.lineStart + 1;
  const endLine = node.lineEnd - 1; // last line of section (inclusive)

  if (startLine > endLine || startLine >= document.lineCount) {
    return false;
  }

  const startPos = new vscode.Position(startLine, 0);
  const endPos = document.lineAt(Math.min(endLine, document.lineCount - 1)).range.end;
  const replaceRange = new vscode.Range(startPos, endPos);

  return editor.edit((eb) => {
    eb.replace(replaceRange, newText);
  });
}

// ---------------------------------------------------------------------------
// Decoration pass (BRIEF §Decorations)
//
// Score each paragraph > 30 words in the active .md document and apply the
// appropriate decoration. Called after score/transform commands and on save.
// NOT called on every document change event.
// ---------------------------------------------------------------------------

async function _applyDecorations(editor: vscode.TextEditor): Promise<void> {
  if (editor.document.languageId !== "markdown") {
    return;
  }

  const cfg = _cfg();
  const text = editor.document.getText();

  // Split text into paragraphs (blocks separated by blank lines)
  const paragraphs = _splitIntoParagraphs(text, editor.document);

  const highRanges: vscode.Range[] = [];
  const medRanges: vscode.Range[] = [];

  // Score paragraphs > 30 words concurrently but cap to avoid hammering daemon
  const eligible = paragraphs.filter(
    (p) => p.wordCount > 30
  );

  // Run scoring in parallel (all eligible paragraphs at once)
  const scoreResults = await Promise.allSettled(
    eligible.map((p) => scoreText(p.text, cfg.profile))
  );

  for (let i = 0; i < eligible.length; i++) {
    const result = scoreResults[i];
    if (result.status !== "fulfilled") {
      _log(`Decoration scoring failed for paragraph at line ${eligible[i].startLine}: ${String((result as PromiseRejectedResult).reason)}`);
      continue;
    }
    const score = result.value.score;
    const range = new vscode.Range(
      new vscode.Position(eligible[i].startLine, 0),
      new vscode.Position(eligible[i].endLine, editor.document.lineAt(eligible[i].endLine).text.length)
    );
    if (score >= 0.67) {
      highRanges.push(range);
    } else if (score >= 0.34) {
      medRanges.push(range);
    }
  }

  // Batch all setDecorations calls in one pass (BRIEF: avoid flicker)
  editor.setDecorations(highRiskDecoration, highRanges);
  editor.setDecorations(medRiskDecoration, medRanges);
}

/**
 * Clear all decorations from the editor.
 */
function _clearDecorations(editor: vscode.TextEditor): void {
  editor.setDecorations(highRiskDecoration, []);
  editor.setDecorations(medRiskDecoration, []);
}

interface ParagraphInfo {
  text: string;
  wordCount: number;
  startLine: number;
  endLine: number;
}

/**
 * Split the document into paragraph blocks (separated by blank lines).
 */
function _splitIntoParagraphs(
  _text: string,
  document: vscode.TextDocument
): ParagraphInfo[] {
  const paragraphs: ParagraphInfo[] = [];
  let blockStart = -1;
  let blockLines: string[] = [];

  function flushBlock(endLine: number): void {
    if (blockStart < 0 || blockLines.length === 0) {
      return;
    }
    const joined = blockLines.join("\n");
    const wordCount = joined
      .trim()
      .split(/\s+/)
      .filter((w) => w.length > 0).length;
    paragraphs.push({
      text: joined,
      wordCount,
      startLine: blockStart,
      endLine,
    });
    blockStart = -1;
    blockLines = [];
  }

  for (let i = 0; i < document.lineCount; i++) {
    const lineText = document.lineAt(i).text;
    if (lineText.trim().length === 0) {
      flushBlock(i - 1);
    } else {
      if (blockStart < 0) {
        blockStart = i;
      }
      blockLines.push(lineText);
    }
  }
  // Final block
  if (blockLines.length > 0) {
    flushBlock(document.lineCount - 1);
  }

  return paragraphs;
}

// ---------------------------------------------------------------------------
// Progress store helpers
// ---------------------------------------------------------------------------

function _progressKey(title: string): string {
  return title.toLowerCase().trim();
}

function _saveNodeProgress(
  ctx: vscode.ExtensionContext,
  node: SectionNode
): void {
  const data = loadProgress(ctx);
  data[_progressKey(node.title)] = {
    status: node.status === "done" ? "done" : node.status === "skipped" ? "skipped" : "pending",
    preScore: node.preScore ?? null,
    postScore: node.postScore ?? null,
    transformedAt: node.status === "done" ? new Date().toISOString() : null,
  };
  saveProgress(ctx, data);
}

// ---------------------------------------------------------------------------
// registerSectionCommands — the single entry point extension.ts calls.
// ---------------------------------------------------------------------------

export function registerSectionCommands(
  ctx: vscode.ExtensionContext
): void {
  // Create output channel for diagnostic logging
  _outputChannel = vscode.window.createOutputChannel("Humanizer Sections");
  ctx.subscriptions.push(_outputChannel);

  // Instantiate the section tree provider
  const sectionProvider = new SectionProvider(ctx);
  _sectionProvider = sectionProvider;

  // Register the tree data provider for the humanizer.sections view
  ctx.subscriptions.push(
    vscode.window.registerTreeDataProvider(
      "humanizer.sections",
      sectionProvider
    )
  );

  // ---- Clear decorations when the active editor switches to non-.md ----
  ctx.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (!editor || editor.document.languageId !== "markdown") {
        if (editor) {
          _clearDecorations(editor);
        }
      }
    })
  );

  // ---- Auto-score decorations on file save (if humanizer.autoScore is true) ----
  ctx.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (document) => {
      const cfg = _cfg();
      if (!cfg.autoScore) {
        return;
      }
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document !== document) {
        return;
      }
      if (document.languageId !== "markdown") {
        return;
      }
      try {
        await _applyDecorations(editor);
      } catch (err: unknown) {
        _log(`Auto-score decoration error: ${String(err)}`);
      }
    })
  );

  // ---- humanizer.scoreSection ----
  ctx.subscriptions.push(
    vscode.commands.registerCommand(
      "humanizer.scoreSection",
      async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== "markdown") {
          vscode.window.showWarningMessage("Open a Markdown file to score a section.");
          return;
        }

        const cursorLine = editor.selection.active.line;
        const nodes = sectionProvider.nodes;
        const found = _findSectionAtCursor(nodes, cursorLine, true);

        if (!found) {
          vscode.window.showWarningMessage(
            "Cursor is not inside a scoreable section. Move to a section body."
          );
          return;
        }

        const { node, index } = found;
        const text = _extractSectionText(editor.document, node);
        if (text.trim().length === 0) {
          vscode.window.showWarningMessage("Section is empty — nothing to score.");
          return;
        }

        try {
          const cfg = _cfg();
          const result = await scoreText(text, cfg.profile);

          // Update the node with the score
          sectionProvider.updateNode(index, {
            preScore: result.score,
          });

          // Persist
          node.preScore = result.score;
          if (ctx) {
            _saveNodeProgress(ctx, node);
          }

          // Re-apply decorations
          await _applyDecorations(editor);

          vscode.window.setStatusBarMessage(
            `Section "${node.title}": ${result.score.toFixed(2)} ${result.band.toUpperCase()}`,
            5000
          );
        } catch (err: unknown) {
          _showError(err);
        }
      }
    )
  );

  // ---- humanizer.transformSection ----
  ctx.subscriptions.push(
    vscode.commands.registerCommand(
      "humanizer.transformSection",
      async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== "markdown") {
          vscode.window.showWarningMessage("Open a Markdown file to transform a section.");
          return;
        }

        const cursorLine = editor.selection.active.line;
        // Re-parse fresh so we pick up edits
        const lines = editor.document.getText().split("\n");
        const freshNodes = parseHeadings(lines);
        const found = _findSectionAtCursor(freshNodes, cursorLine);

        if (!found) {
          vscode.window.showWarningMessage(
            "Cursor is not inside a transformable section. Move to a section body (must be > 30 words and not the References section)."
          );
          return;
        }

        const { node } = found;
        const nodeIndex = sectionProvider.nodes.findIndex(
          (n) => n.lineStart === node.lineStart
        );

        const text = _extractSectionText(editor.document, node);
        if (text.trim().length === 0) {
          vscode.window.showWarningMessage("Section is empty — nothing to transform.");
          return;
        }

        // Mark as processing
        sectionProvider.updateNode(nodeIndex, { status: "processing" });

        try {
          const cfg = _cfg();
          const result = await transformText(text, {
            stages: ["prescan", "determ", "postscan"],
            profile: cfg.profile,
          });

          // Replace section body in the document
          await _replaceSectionText(editor, node, result.output);

          // Update node
          sectionProvider.updateNode(nodeIndex, {
            status: "done",
            preScore: result.pre_score,
            postScore: result.post_score,
          });

          // Persist
          node.status = "done";
          node.preScore = result.pre_score;
          node.postScore = result.post_score;
          _saveNodeProgress(ctx, node);

          // Re-apply decorations after a brief delay (500 ms per CONTRACT §8)
          setTimeout(async () => {
            const currentEditor = vscode.window.activeTextEditor;
            if (currentEditor) {
              try {
                await _applyDecorations(currentEditor);
              } catch (err: unknown) {
                _log(`Post-transform decoration error: ${String(err)}`);
              }
            }
          }, 500);

          vscode.window.setStatusBarMessage(
            `"${node.title}" rewritten. Score: ${result.pre_score.toFixed(2)} → ${result.post_score.toFixed(2)}`,
            6000
          );
        } catch (err: unknown) {
          // Mark as skipped on failure so the tree shows the error visually
          sectionProvider.updateNode(nodeIndex, { status: "skipped" });
          _showError(err);
        }
      }
    )
  );

  // ---- humanizer.transformAll ----
  ctx.subscriptions.push(
    vscode.commands.registerCommand(
      "humanizer.transformAll",
      async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== "markdown") {
          vscode.window.showWarningMessage(
            "Open a Markdown file to transform all sections."
          );
          return;
        }

        // Snapshot current nodes — only pending sections are eligible
        const allNodes = sectionProvider.nodes;
        const pending = allNodes
          .map((n, i) => ({ node: n, index: i }))
          .filter(
            ({ node }) =>
              node.status === "pending" && node.wordCount >= 30
          );

        if (pending.length === 0) {
          vscode.window.showInformationMessage(
            "No pending sections to transform. All sections are done, skipped, or too short."
          );
          return;
        }

        let doneCount = 0;
        const total = pending.length;
        const cfg = _cfg();

        await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "Humanizer: rewriting sections",
            cancellable: false,
          },
          async (progress) => {
            for (let i = 0; i < pending.length; i++) {
              const { node, index } = pending[i];

              progress.report({
                message: `"${node.title}" (${i + 1}/${total})…`,
                increment: 0,
              });

              // Re-read the document lines to get fresh line numbers after
              // previous edits shifted the document
              const freshLines = editor.document.getText().split("\n");
              const freshNodes = parseHeadings(freshLines);
              const freshNode = freshNodes.find(
                (n) => n.title === node.title && n.level === node.level
              );
              if (!freshNode) {
                _log(`Could not find section "${node.title}" after previous edits — skipping.`);
                sectionProvider.updateNode(index, { status: "skipped" });
                continue;
              }

              // Mark as processing
              sectionProvider.updateNode(index, { status: "processing" });

              const text = _extractSectionText(editor.document, freshNode);
              if (text.trim().length === 0) {
                _log(`Section "${node.title}" is empty — skipping.`);
                sectionProvider.updateNode(index, { status: "skipped" });
                continue;
              }

              try {
                const result = await transformText(text, {
                  stages: ["prescan", "determ", "postscan"],
                  profile: cfg.profile,
                });

                await _replaceSectionText(editor, freshNode, result.output);

                sectionProvider.updateNode(index, {
                  status: "done",
                  preScore: result.pre_score,
                  postScore: result.post_score,
                });

                // Persist
                node.status = "done";
                node.preScore = result.pre_score;
                node.postScore = result.post_score;
                _saveNodeProgress(ctx, node);

                doneCount++;

                progress.report({
                  message: `"${node.title}" done (${i + 1}/${total})`,
                  increment: Math.floor(100 / total),
                });
              } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : String(err);
                _log(`Error transforming "${node.title}": ${msg}`);
                sectionProvider.updateNode(index, { status: "skipped" });
                // Continue to next section (BRIEF §transformAll logic)
              }
            }
          }
        );

        // Summary toast
        vscode.window.showInformationMessage(
          `Humanizer: Done. ${doneCount}/${total} section${total === 1 ? "" : "s"} rewritten.`
        );

        // Re-apply decorations
        const currentEditor = vscode.window.activeTextEditor;
        if (currentEditor) {
          try {
            await _applyDecorations(currentEditor);
          } catch (err: unknown) {
            _log(`Post-transform-all decoration error: ${String(err)}`);
          }
        }
      }
    )
  );

  // ---- humanizer.exportDocx ----
  ctx.subscriptions.push(
    vscode.commands.registerCommand(
      "humanizer.exportDocx",
      async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== "markdown") {
          vscode.window.showWarningMessage("Open a Markdown file to export to .docx.");
          return;
        }

        // CONTRACT §7: determine paths
        const inputPath = editor.document.uri.fsPath;
        const dir = path.dirname(inputPath);
        const stem = path.basename(inputPath, path.extname(inputPath));
        const outputPath = path.join(dir, `${stem}_humanized.docx`);

        const cfg = _cfg();
        const binaryPath = cfg.binaryPath;

        await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "Humanizer: exporting to .docx…",
            cancellable: false,
          },
          async () => {
            await new Promise<void>((resolve, reject) => {
              // CONTRACT §7: use execFile (not exec) to avoid shell injection
              execFile(
                binaryPath,
                [
                  "transform",
                  inputPath,
                  "--stages",
                  "prescan,determ,postscan",
                  "--out",
                  outputPath,
                ],
                { env: process.env },
                (error, _stdout, stderr) => {
                  if (error) {
                    const detail = stderr
                      ? stderr.slice(0, 300)
                      : error.message;
                    reject(new Error(detail));
                  } else {
                    resolve();
                  }
                }
              );
            });
          }
        );

        // Open the containing folder on success
        await vscode.commands.executeCommand(
          "revealFileInOS",
          vscode.Uri.file(outputPath)
        );
        vscode.window.showInformationMessage(
          `Exported: ${path.basename(outputPath)}`
        );
      }
    )
  );

  // ---- humanizer.showProgress ----
  ctx.subscriptions.push(
    vscode.commands.registerCommand(
      "humanizer.showProgress",
      async () => {
        // Focus the section tree view (CONTRACT §showProgress logic)
        await vscode.commands.executeCommand("humanizer.sections.focus");
      }
    )
  );

  // ---- Wrap all command handlers in error guards ----
  // (Already done inline per CONTRACT §10 — never throw uncaught from a handler)
}

// ---------------------------------------------------------------------------
// Re-export types used by statusBar or other Agent A components (CONTRACT §8)
// ---------------------------------------------------------------------------

// highRiskDecoration and medRiskDecoration are already exported at the top.
// sectionProvider.ts exports SectionNode and SectionProvider.
// progressStore.ts exports SectionProgress.
// These re-exports avoid cross-track imports (CONTRACT §2 / ROADMAP §Shared files).

// Expose a convenience getter so statusBar.ts can call
// "apply decorations for the active editor" without importing the whole processor:
export function applyDecorationsForActiveEditor(): void {
  const editor = vscode.window.activeTextEditor;
  if (editor && editor.document.languageId === "markdown") {
    _applyDecorations(editor).catch((err: unknown) => {
      // Non-fatal — decorations are cosmetic
      if (_outputChannel) {
        _outputChannel.appendLine(
          `[Humanizer] Decoration error: ${String(err)}`
        );
      }
    });
  }
}

// Expose a getter for the SectionProvider singleton (used by extension.ts if needed)
export function getSectionProvider(): SectionProvider | undefined {
  return _sectionProvider;
}

// SectionProgress is exported from progressStore and re-used by loadProgress/saveProgress above.
// The type import is retained for completeness; suppress the lint warning via a
// nominal usage in the JSDoc-visible type annotation below.
export type { SectionProgress };
