/**
 * sectionProvider.ts — TreeDataProvider<SectionNode> for the Section Progress view.
 *
 * CONTRACT §2: defines SectionNode shape.
 * BRIEF §sectionProvider.ts: parses ATX headings from the active .md document,
 * assigns status, word count, and score badges, and refreshes on document change
 * (300 ms debounce).
 *
 * Re-parses on vscode.workspace.onDidChangeTextDocument for the active file.
 * Does NOT score paragraphs on every keypress — scoring is triggered externally
 * by score/transform commands (BRIEF §Decoration call limit).
 */

import * as vscode from "vscode";
import { getLastMarkdownEditor } from "./activeEditorTracker";

// ---------------------------------------------------------------------------
// Types (CONTRACT §2)
// ---------------------------------------------------------------------------

export interface SectionNode {
  title: string; // heading text without leading #
  level: number; // 1 | 2 | 3
  lineStart: number; // 0-based line of the heading
  lineEnd: number; // 0-based line of last section line (exclusive)
  wordCount: number;
  status: "pending" | "processing" | "done" | "skipped" | "too_short";
  preScore?: number;
  postScore?: number;
  /**
   * v1.3 — research-aid checklist badge data. Optional so older code paths
   * keep working unchanged. ``checklistScore`` is the canonical "N/M" string
   * from /v1/checklist; ``checklistType`` is the resolved archetype name
   * (introduction / methods / etc).
   */
  checklistScore?: string;
  checklistType?: string;
}

// ---------------------------------------------------------------------------
// Known research-proposal sections (ROADMAP §Research proposal section names)
// ---------------------------------------------------------------------------

const KNOWN_SECTIONS = new Set([
  "abstract",
  "introduction",
  "background",
  "literature review",
  "research questions",
  "objectives",
  "methodology",
  "methods",
  "results",
  "discussion",
  "conclusion",
  "references",
]);

// ---------------------------------------------------------------------------
// SectionTreeItem
// ---------------------------------------------------------------------------

class SectionTreeItem extends vscode.TreeItem {
  constructor(node: SectionNode) {
    super(node.title, vscode.TreeItemCollapsibleState.None);

    // Description = score badge (CONTRACT §2 format)
    this.description = _buildDescription(node);

    // v1.4: themed codicon per section archetype with a risk-tinted colour.
    // Status-driven icons (sync~spin / pass-filled) still win for in-flight
    // and finished states — the themed icon is only used while the section
    // is "pending".
    this.iconPath = _iconForNode(node);

    // Tooltip: full details
    this.tooltip = _buildTooltip(node);

    // Context value for possible future when-clauses
    this.contextValue = `humanizer.section.${node.status}`;
  }
}

function _buildDescription(node: SectionNode): string {
  // v1.3: format target is "Intro · 3/5 · 0.21 LOW · 612 w" when we have
  // checklist data. Older statuses (too short / skipped) still win when the
  // section can't be scored at all.
  const parts: string[] = [];
  if (node.checklistScore) {
    parts.push(node.checklistScore);
  }
  if (node.status === "done" && node.postScore !== undefined) {
    parts.push(`${node.postScore.toFixed(2)} ${_band(node.postScore).toUpperCase()}`);
  } else if (node.preScore !== undefined) {
    parts.push(`${node.preScore.toFixed(2)} ${_band(node.preScore).toUpperCase()}`);
  }
  if (node.checklistScore) {
    // include word count when checklist data is present
    parts.push(`${node.wordCount} w`);
  }

  if (parts.length > 0) {
    return parts.join(" · ");
  }
  if (node.status === "too_short") {
    return "(too short)";
  }
  if (node.status === "skipped") {
    return "(skipped)";
  }
  return "";
}

function _iconForStatus(
  status: SectionNode["status"]
): string {
  switch (status) {
    case "pending":
      return "circle-outline";
    case "processing":
      return "sync~spin";
    case "done":
      return "pass-filled";
    case "skipped":
    case "too_short":
      return "circle-slash";
  }
}

// v1.4 — themed codicon map keyed by checklistType (preferred) or the
// lowercased heading title as a fallback. Returns the codicon id only.
function _codiconForType(typeOrTitle: string): string {
  const k = typeOrTitle.toLowerCase().trim();
  if (k === "introduction" || k === "background" || k === "abstract") {
    return "book";
  }
  if (k === "methods" || k === "methodology") {
    return "beaker";
  }
  if (k === "results" || k === "findings") {
    return "graph";
  }
  if (k === "discussion") {
    return "comment-discussion";
  }
  if (k === "references") {
    return "references";
  }
  if (k === "conclusion") {
    return "mortar-board";
  }
  if (k === "literature_review" || k === "literature review") {
    return "symbol-string";
  }
  return "symbol-string";
}

// v1.4 — pick the themed icon + risk-tinted colour for a node. Status-driven
// behaviour (spin while processing, slash when skipped) still wins because
// those are the canonical visual cues for in-flight work.
function _iconForNode(node: SectionNode): vscode.ThemeIcon {
  if (
    node.status === "processing" ||
    node.status === "skipped" ||
    node.status === "too_short"
  ) {
    return new vscode.ThemeIcon(_iconForStatus(node.status));
  }
  // Themed codicon — prefer the resolved checklist archetype, fall back to
  // the heading text.
  const codicon = _codiconForType(node.checklistType ?? node.title);
  // Risk-tinted colour: use postScore when "done", otherwise preScore.
  const score =
    node.status === "done" && node.postScore !== undefined
      ? node.postScore
      : node.preScore;
  if (score === undefined) {
    return new vscode.ThemeIcon(codicon);
  }
  const colourId =
    score >= 0.67
      ? "charts.red"
      : score >= 0.34
        ? "charts.yellow"
        : "charts.green";
  return new vscode.ThemeIcon(codicon, new vscode.ThemeColor(colourId));
}

function _buildTooltip(node: SectionNode): string {
  const lines: string[] = [
    `${node.title}`,
    `Level: h${node.level}   Words: ${node.wordCount}`,
    `Status: ${node.status}`,
  ];
  if (node.preScore !== undefined) {
    lines.push(`Pre-score: ${node.preScore.toFixed(3)} (${_band(node.preScore)})`);
  }
  if (node.postScore !== undefined) {
    lines.push(`Post-score: ${node.postScore.toFixed(3)} (${_band(node.postScore)})`);
  }
  return lines.join("\n");
}

function _band(score: number): string {
  if (score >= 0.67) {
    return "high";
  }
  if (score >= 0.34) {
    return "medium";
  }
  return "low";
}

// ---------------------------------------------------------------------------
// ATX heading parser
// ---------------------------------------------------------------------------

const HEADING_RE = /^(#{1,3})\s+(.+)/;

/**
 * Parse all ATX headings (level 1-3) from the document lines.
 * Returns SectionNode list in document order with lineStart/lineEnd/wordCount
 * pre-populated. status starts as "pending" unless overridden by known rules.
 */
export function parseHeadings(
  lines: string[],
  savedProgress?: Record<string, { status: "pending" | "done" | "skipped"; preScore?: number; postScore?: number }>
): SectionNode[] {
  const nodes: SectionNode[] = [];

  for (let i = 0; i < lines.length; i++) {
    const m = HEADING_RE.exec(lines[i]);
    if (!m) {
      continue;
    }
    const level = m[1].length as 1 | 2 | 3;
    const title = m[2].trim();
    nodes.push({
      title,
      level,
      lineStart: i,
      lineEnd: lines.length, // filled in next pass
      wordCount: 0,
      status: "pending",
    });
  }

  // Second pass: assign lineEnd and wordCount
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    // lineEnd = line before next heading at same or shallower depth, or EOF
    let lineEnd = lines.length;
    for (let j = i + 1; j < nodes.length; j++) {
      if (nodes[j].level <= node.level) {
        lineEnd = nodes[j].lineStart;
        break;
      }
    }
    node.lineEnd = lineEnd;

    // Word count: tokens in lines between lineStart+1 and lineEnd (exclusive)
    let wordCount = 0;
    for (let ln = node.lineStart + 1; ln < lineEnd; ln++) {
      wordCount += lines[ln].trim().split(/\s+/).filter((w) => w.length > 0).length;
    }
    node.wordCount = wordCount;

    // Status rules (BRIEF §Section detection algorithm)
    const lowerTitle = title_lower(node.title);
    if (/^references$/i.test(node.title)) {
      node.status = "skipped";
    } else if (node.wordCount < 30) {
      node.status = "too_short";
    } else {
      // Restore persisted status if available
      const key = lowerTitle;
      if (savedProgress && savedProgress[key]) {
        const saved = savedProgress[key];
        node.status = saved.status === "done" ? "done" : "pending";
        if (saved.preScore !== undefined) {
          node.preScore = saved.preScore;
        }
        if (saved.postScore !== undefined) {
          node.postScore = saved.postScore;
        }
      }
    }

    // Known section icon annotation (informational — just validates KNOWN_SECTIONS)
    if (KNOWN_SECTIONS.has(lowerTitle)) {
      // In VS Code tree items the tooltip already shows the type;
      // no separate field needed — just confirming membership.
    }
  }

  return nodes;
}

function title_lower(title: string): string {
  return title.toLowerCase().trim();
}

// ---------------------------------------------------------------------------
// SectionProvider (TreeDataProvider)
// ---------------------------------------------------------------------------

export class SectionProvider
  implements vscode.TreeDataProvider<SectionNode>
{
  private _nodes: SectionNode[] = [];
  private _debounceTimer: ReturnType<typeof setTimeout> | undefined;

  private readonly _onDidChangeTreeData = new vscode.EventEmitter<
    SectionNode | undefined | null | void
  >();
  readonly onDidChangeTreeData: vscode.Event<
    SectionNode | undefined | null | void
  > = this._onDidChangeTreeData.event;

  constructor(ctx: vscode.ExtensionContext) {
    // Initial parse
    this._parseActive();

    // Re-parse when the active editor changes
    ctx.subscriptions.push(
      vscode.window.onDidChangeActiveTextEditor(() => {
        this._parseActive();
      })
    );

    // Re-parse on document change (debounced 300 ms — BRIEF §Section detection algorithm)
    ctx.subscriptions.push(
      vscode.workspace.onDidChangeTextDocument((event) => {
        const editor = vscode.window.activeTextEditor;
        if (!editor || event.document !== editor.document) {
          return;
        }
        if (this._debounceTimer !== undefined) {
          clearTimeout(this._debounceTimer);
        }
        this._debounceTimer = setTimeout(() => {
          this._parseActive();
        }, 300);
      })
    );
  }

  // ---- TreeDataProvider ----

  getTreeItem(node: SectionNode): vscode.TreeItem {
    return new SectionTreeItem(node);
  }

  getChildren(node?: SectionNode): SectionNode[] {
    if (node !== undefined) {
      // Flat list; no children per node in the current design
      return [];
    }
    return this._nodes;
  }

  // ---- Public API ----

  /** Current snapshot of parsed section nodes. */
  get nodes(): readonly SectionNode[] {
    return this._nodes;
  }

  /**
   * Force a tree refresh — called by sectionProcessor after transforms or scores.
   * Optionally accepts an updated node list; if omitted, re-parses the document.
   */
  refresh(updatedNodes?: SectionNode[]): void {
    if (updatedNodes !== undefined) {
      this._nodes = updatedNodes;
    } else {
      this._parseActive();
    }
    this._onDidChangeTreeData.fire();
  }

  /**
   * Update a single node's fields (status, scores) in-place and fire a
   * targeted refresh so VS Code only re-renders the affected item.
   */
  updateNode(
    index: number,
    patch: Partial<
      Pick<
        SectionNode,
        "status"
        | "preScore"
        | "postScore"
        | "checklistScore"
        | "checklistType"
      >
    >
  ): void {
    if (index < 0 || index >= this._nodes.length) {
      return;
    }
    Object.assign(this._nodes[index], patch);
    this._onDidChangeTreeData.fire(this._nodes[index]);
  }

  /**
   * v1.3 — apply checklist results to matching nodes. Matching is done by
   * the heading title (case-insensitive, trimmed). Sections with no match
   * are left alone so this method can be called after a partial fetch.
   */
  applyChecklist(
    sections: { heading: string; type: string; score: string }[]
  ): void {
    const byTitle = new Map<string, { type: string; score: string }>();
    for (const s of sections) {
      byTitle.set(s.heading.toLowerCase().trim(), {
        type: s.type,
        score: s.score,
      });
    }
    let dirty = false;
    for (const node of this._nodes) {
      const match = byTitle.get(node.title.toLowerCase().trim());
      if (!match) {
        continue;
      }
      const oldScore = node.checklistScore;
      const oldType = node.checklistType;
      node.checklistScore = match.score;
      node.checklistType = match.type;
      if (oldScore !== match.score || oldType !== match.type) {
        dirty = true;
      }
    }
    if (dirty) {
      this._onDidChangeTreeData.fire();
    }
  }

  // ---- Private ----

  private _parseActive(): void {
    const editor = getLastMarkdownEditor() ?? vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
      this._nodes = [];
      this._onDidChangeTreeData.fire();
      return;
    }
    const text = editor.document.getText();
    const lines = text.split("\n");
    this._nodes = parseHeadings(lines);
    this._onDidChangeTreeData.fire();
  }
}
