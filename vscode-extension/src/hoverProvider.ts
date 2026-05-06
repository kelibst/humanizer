/**
 * hoverProvider.ts — explanatory hover for Humanizer diagnostics.
 *
 * Pulls the diagnostic at the hovered position from the shared
 * `humanizer` collection and renders a `MarkdownString` with:
 *  - the human-readable message (which lint rule triggered),
 *  - the lint code (e.g. `llm-vocab`) so the user can suppress / search,
 *  - up to 3 academic alternatives (when present in the LintSpan).
 *
 * Hover content is non-interactive (`isTrusted = false`) — Quick-Fix is the
 * action surface; this is just an explainer.
 */

import * as vscode from "vscode";
import { spanForDiagnostic, getCollection } from "./diagnostics";

const MAX_ALTERNATIVES = 3;

function _humanCode(code: string): string {
  switch (code) {
    case "llm-vocab":
      return "AI-flavoured vocabulary";
    case "long-sentence":
      return "Sentence too long for profile target";
    case "topic-perfection":
      return "Textbook-clean topic sentence (AI tic)";
    case "list-overuse":
      return "Three-item list (AI rule of three)";
    case "missing-citation":
      return "Quantitative claim without citation";
    case "orphan-citation":
      return "Citation has no entry in references.json";
    default:
      return code;
  }
}

function _renderHover(
  document: vscode.TextDocument,
  diagnostics: vscode.Diagnostic[]
): vscode.Hover | undefined {
  if (diagnostics.length === 0) {
    return undefined;
  }
  // Stable-sort: most specific first (warning before info).
  const sorted = diagnostics.slice().sort((a, b) => a.severity - b.severity);

  const md = new vscode.MarkdownString();
  md.isTrusted = false;
  md.supportHtml = false;

  for (let i = 0; i < sorted.length; i += 1) {
    if (i > 0) {
      md.appendMarkdown("\n\n---\n\n");
    }
    const diag = sorted[i];
    const codeStr = (diag.code as string | undefined) ?? "humanizer";
    md.appendMarkdown(`**Humanizer — ${_humanCode(codeStr)}**`);
    md.appendMarkdown(`\n\n${diag.message}`);

    const span = spanForDiagnostic(document, diag);
    if (span && span.suggestions.length > 0) {
      const alts = span.suggestions.slice(0, MAX_ALTERNATIVES);
      md.appendMarkdown("\n\n**Try:** ");
      md.appendMarkdown(alts.map((a) => `\`${a}\``).join(", "));
    }
    md.appendMarkdown(`\n\n_Code: \`${codeStr}\`_`);
  }

  return new vscode.Hover(md);
}

class HumanizerHoverProvider implements vscode.HoverProvider {
  provideHover(
    document: vscode.TextDocument,
    position: vscode.Position
  ): vscode.ProviderResult<vscode.Hover> {
    const collection = getCollection();
    if (!collection) {
      return undefined;
    }
    const all = collection.get(document.uri);
    if (!all || all.length === 0) {
      return undefined;
    }
    const here = all.filter((d) => d.range.contains(position));
    return _renderHover(document, here);
  }
}

export function registerHoverProvider(
  ctx: vscode.ExtensionContext
): vscode.Disposable {
  const provider = vscode.languages.registerHoverProvider(
    { language: "markdown" },
    new HumanizerHoverProvider()
  );
  ctx.subscriptions.push(provider);
  return provider;
}
