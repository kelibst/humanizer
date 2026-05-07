/**
 * dashboard.ts — Research Dashboard webview tab.
 *
 * Renders four sections using pure SVG (no Chart.js / D3):
 *   1. AI-risk sparkline per section, history from
 *      ``workspaceState["humanizer.scoreHistory"]`` (≤ 30 points per section).
 *   2. Word-target progress bars per section.
 *   3. Citation count rings (missing / orphans / unused).
 *   4. Section completeness ring chart.
 *
 * Refresh button calls daemonClient.checklist + readability + citations + scoreText
 * and persists score snapshots into the sparkline history.
 *
 * No new npm deps. Pure SVG by string concatenation.
 */

import * as vscode from "vscode";
import {
  checklist as fetchChecklist,
  readability as fetchReadability,
  citations as fetchCitations,
  scoreText,
  DaemonError,
  ChecklistResult,
  ReadabilityResult,
  CitationsResult,
} from "./daemonClient";
import { getLastMarkdownEditor } from "./activeEditorTracker";

const HISTORY_KEY = "humanizer.scoreHistory";
const HISTORY_CAP = 30;

let _panel: vscode.WebviewPanel | undefined;
let _ctx: vscode.ExtensionContext | undefined;

interface ScoreHistory {
  // section heading (case-insensitive trim) -> chronologically ordered scores
  [sectionKey: string]: number[];
}

/**
 * Open or reveal the dashboard. Called from the
 * ``humanizer.openDashboard`` command in extension.ts.
 */
export function openDashboard(ctx: vscode.ExtensionContext): void {
  _ctx = ctx;
  if (_panel) {
    _panel.reveal(vscode.ViewColumn.One, false);
    _kickRefresh();
    return;
  }

  _panel = vscode.window.createWebviewPanel(
    "humanizer.dashboard",
    "Research Dashboard",
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [ctx.extensionUri],
    }
  );

  _panel.webview.html = _buildHtml(_panel.webview);

  _panel.onDidDispose(() => {
    _panel = undefined;
  });

  _panel.webview.onDidReceiveMessage(async (msg: { type?: string }) => {
    if (!msg || typeof msg.type !== "string") {
      return;
    }
    if (msg.type === "ready" || msg.type === "refresh") {
      await _kickRefresh();
    }
  });
}

async function _kickRefresh(): Promise<void> {
  if (!_panel || !_ctx) {
    return;
  }
  const ctx = _ctx;
  const editor = getLastMarkdownEditor() ?? vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    _panel.webview.postMessage({
      type: "data",
      error: "Open a Markdown file to populate the dashboard.",
    });
    return;
  }
  const text = editor.document.getText();
  if (!text.trim()) {
    _panel.webview.postMessage({
      type: "data",
      error: "The active file is empty.",
    });
    return;
  }

  const cfg = vscode.workspace.getConfiguration("humanizer");
  const profile = cfg.get<string>("profile");
  const wsRoot = _workspaceRootFor(editor.document.uri);

  let checklist: ChecklistResult | undefined;
  let readabilityRes: ReadabilityResult | undefined;
  let citationsRes: CitationsResult | undefined;
  let documentScore: number | undefined;
  let documentBand: string | undefined;
  const errors: string[] = [];

  await Promise.all([
    (async () => {
      try {
        checklist = await fetchChecklist(text, profile);
      } catch (err: unknown) {
        errors.push(`checklist: ${_errMsg(err)}`);
      }
    })(),
    (async () => {
      try {
        readabilityRes = await fetchReadability(text, profile);
      } catch (err: unknown) {
        errors.push(`readability: ${_errMsg(err)}`);
      }
    })(),
    (async () => {
      try {
        if (wsRoot) {
          citationsRes = await fetchCitations(text, wsRoot, profile);
        }
      } catch (err: unknown) {
        errors.push(`citations: ${_errMsg(err)}`);
      }
    })(),
    (async () => {
      try {
        const r = await scoreText(text, profile);
        documentScore = r.score;
        documentBand = r.band;
      } catch (err: unknown) {
        errors.push(`score: ${_errMsg(err)}`);
      }
    })(),
  ]);

  // Persist per-section score snapshots so the sparkline accumulates.
  const history = ctx.workspaceState.get<ScoreHistory>(HISTORY_KEY, {});
  if (checklist && checklist.sections.length > 0 && documentScore !== undefined) {
    // We store the document-level score under each section heading as a
    // pragmatic v1.4 fallback — Agent B's section-scoped scores aren't
    // exposed by /v1/checklist. The series therefore reflects "document
    // score over time, anchored to the section list of the latest run."
    for (const sec of checklist.sections) {
      const key = sec.heading.toLowerCase().trim();
      if (!key) {
        continue;
      }
      const series = history[key] ?? [];
      series.push(documentScore);
      while (series.length > HISTORY_CAP) {
        series.shift();
      }
      history[key] = series;
    }
    await ctx.workspaceState.update(HISTORY_KEY, history);
  }

  const wordsPerSectionTarget =
    readabilityRes?.targets.wordsPerSection?.target ?? null;

  _panel.webview.postMessage({
    type: "data",
    error: errors.length > 0 ? errors.join("; ") : undefined,
    documentScore,
    documentBand,
    sections: (checklist?.sections ?? []).map((s) => ({
      heading: s.heading,
      type: s.type,
      score: s.score,
      wordCount: s.wordCount,
      historyKey: s.heading.toLowerCase().trim(),
      sparkline: history[s.heading.toLowerCase().trim()] ?? [],
    })),
    wordsPerSectionTarget,
    citations: citationsRes
      ? {
          missing: citationsRes.missing.length,
          orphans: citationsRes.orphans.length,
          unused: citationsRes.unused.length,
        }
      : undefined,
  });
}

function _workspaceRootFor(uri: vscode.Uri): string | undefined {
  const folder = vscode.workspace.getWorkspaceFolder(uri);
  if (folder) {
    return folder.uri.fsPath;
  }
  // Fall back to the file's directory.
  const fsPath = uri.fsPath;
  const sep = fsPath.lastIndexOf("/");
  if (sep === -1) {
    return undefined;
  }
  return fsPath.slice(0, sep);
}

function _errMsg(err: unknown): string {
  if (err instanceof DaemonError) {
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}

// ---------------------------------------------------------------------------
// HTML / inline JS — pure SVG renderers
// ---------------------------------------------------------------------------

function _buildHtml(webview: vscode.Webview): string {
  const csp = `default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'unsafe-inline';`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="${csp}">
  <title>Research Dashboard</title>
  <style>
    :root {
      --hz-bg: var(--vscode-editor-background, #ffffff);
      --hz-fg: var(--vscode-foreground, #202124);
      --hz-muted: var(--vscode-descriptionForeground, #5f6368);
      --hz-line: var(--vscode-widget-border, #e0e0e0);
      --hz-accent: var(--vscode-button-background, #1a73e8);
      --hz-low: #1e8e3e;
      --hz-med: #f9ab00;
      --hz-high: #d93025;
    }
    body {
      margin: 0;
      padding: 16px;
      font-family: var(--vscode-font-family, sans-serif);
      font-size: 13px;
      color: var(--hz-fg);
      background: var(--hz-bg);
    }
    h1 { font-size: 18px; margin: 0 0 4px 0; }
    .hz-sub { color: var(--hz-muted); font-size: 12px; margin-bottom: 16px; }
    .hz-row { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
    button {
      appearance: none;
      background: var(--hz-accent);
      color: var(--vscode-button-foreground, #fff);
      border: 1px solid var(--hz-accent);
      border-radius: 4px;
      padding: 6px 14px;
      font-size: 12px;
      cursor: pointer;
    }
    button:hover { opacity: 0.85; }
    .hz-card {
      border: 1px solid var(--hz-line);
      border-radius: 6px;
      padding: 12px 14px;
      margin-bottom: 14px;
      background: var(--vscode-editorWidget-background, transparent);
    }
    .hz-card-title {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--hz-muted);
      margin-bottom: 10px;
    }
    .hz-section-row {
      display: grid;
      grid-template-columns: 180px 1fr 90px;
      align-items: center;
      gap: 10px;
      padding: 6px 0;
      border-bottom: 1px dashed var(--hz-line);
    }
    .hz-section-row:last-child { border-bottom: 0; }
    .hz-section-name { font-weight: 500; }
    .hz-section-meta { color: var(--hz-muted); font-size: 11px; }
    .hz-words-bar-bg {
      width: 100%; height: 8px; background: var(--vscode-editorWidget-background, #f1f3f4);
      border-radius: 999px; overflow: hidden;
    }
    .hz-words-bar-fill {
      height: 100%; border-radius: 999px;
      transition: width 220ms ease-out;
    }
    .hz-rings { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
    .hz-ring-item { text-align: center; }
    .hz-ring-label { font-size: 11px; color: var(--hz-muted); margin-top: 4px; }
    .hz-error {
      color: var(--hz-high);
      background: rgba(217, 48, 37, 0.12);
      border: 1px solid var(--hz-high);
      border-radius: 4px;
      padding: 8px 10px;
      margin-bottom: 12px;
      font-size: 11px;
    }
    .hz-empty { color: var(--hz-muted); font-style: italic; }
    .hz-doc-score {
      font-variant-numeric: tabular-nums;
      font-size: 16px; font-weight: 600;
    }
    .hz-band-pill {
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      font-size: 10px; font-weight: 600; letter-spacing: 0.4px; margin-left: 6px;
    }
    .hz-band-pill--low  { background: #e6f4ea; color: var(--hz-low); }
    .hz-band-pill--medium { background: #fef7e0; color: #b06000; }
    .hz-band-pill--high { background: #fce8e6; color: var(--hz-high); }
  </style>
</head>
<body>
  <h1>Research Dashboard</h1>
  <div class="hz-sub" id="hz-sub">Refresh to populate from the active markdown file.</div>

  <div class="hz-row">
    <button id="hz-refresh">Refresh</button>
    <span id="hz-doc-score-wrap"></span>
  </div>

  <div id="hz-error-wrap"></div>

  <div class="hz-card">
    <div class="hz-card-title">AI-risk sparkline (per section)</div>
    <div id="hz-sparklines"><div class="hz-empty">No data yet — click Refresh.</div></div>
  </div>

  <div class="hz-card">
    <div class="hz-card-title">Word-target progress</div>
    <div id="hz-word-bars"><div class="hz-empty">No data yet.</div></div>
  </div>

  <div class="hz-card">
    <div class="hz-card-title">Citation hygiene</div>
    <div id="hz-citation-rings"><div class="hz-empty">No data yet.</div></div>
  </div>

  <div class="hz-card">
    <div class="hz-card-title">Section completeness</div>
    <div id="hz-completeness-rings"><div class="hz-empty">No data yet.</div></div>
  </div>

<script>
  const vscode = acquireVsCodeApi();

  document.getElementById('hz-refresh').addEventListener('click', () => {
    vscode.postMessage({ type: 'refresh' });
  });

  function escHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function bandClass(score) {
    if (score >= 0.67) return 'high';
    if (score >= 0.34) return 'medium';
    return 'low';
  }

  function bandColor(score) {
    if (score >= 0.67) return '#d93025';
    if (score >= 0.34) return '#f9ab00';
    return '#1e8e3e';
  }

  function renderSparkline(values) {
    if (!values || values.length < 2) {
      return '<span style="color: var(--hz-muted); font-size: 11px;">' +
        (values && values.length === 1 ? values[0].toFixed(2) + ' (single sample)' : 'no history yet') +
        '</span>';
    }
    const w = 180;
    const h = 28;
    const pad = 2;
    const min = 0;
    const max = 1;
    const stepX = (w - pad * 2) / (values.length - 1);
    let d = '';
    for (let i = 0; i < values.length; i++) {
      const v = Math.max(min, Math.min(max, values[i]));
      const x = pad + i * stepX;
      const y = h - pad - (v - min) / (max - min) * (h - pad * 2);
      d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1) + ' ';
    }
    const last = values[values.length - 1];
    const lastX = pad + (values.length - 1) * stepX;
    const lastY = h - pad - last / (max - min) * (h - pad * 2);
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" aria-label="sparkline">' +
      '<path d="' + d + '" fill="none" stroke="' + bandColor(last) + '" stroke-width="1.5"/>' +
      '<circle cx="' + lastX.toFixed(1) + '" cy="' + lastY.toFixed(1) + '" r="2.2" fill="' + bandColor(last) + '"/>' +
      '</svg>';
  }

  function renderRing(value, total, color, label) {
    const r = 22;
    const c = 50;
    const circumference = 2 * Math.PI * r;
    const pct = total === 0 ? 0 : Math.max(0, Math.min(1, value / total));
    const dash = (circumference * pct).toFixed(1);
    const rest = (circumference - parseFloat(dash)).toFixed(1);
    return '<div class="hz-ring-item">' +
      '<svg width="56" height="56" viewBox="0 0 ' + (c * 2) + ' ' + (c * 2) + '" aria-label="' + escHtml(label) + '">' +
      '<circle cx="' + c + '" cy="' + c + '" r="' + r + '" fill="none" stroke="var(--hz-line)" stroke-width="6"/>' +
      '<circle cx="' + c + '" cy="' + c + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="6"' +
      ' stroke-dasharray="' + dash + ' ' + rest + '" stroke-dashoffset="' + (circumference / 4).toFixed(1) + '"' +
      ' transform="rotate(-90 ' + c + ' ' + c + ')" stroke-linecap="round"/>' +
      '<text x="' + c + '" y="' + (c + 5) + '" text-anchor="middle" font-size="14" fill="currentColor" font-weight="600">' +
      escHtml(String(value)) + '</text>' +
      '</svg>' +
      '<div class="hz-ring-label">' + escHtml(label) + '</div>' +
      '</div>';
  }

  function renderCompletenessRing(score) {
    // score is "N/M" string from /v1/checklist.
    const m = /^(\\d+)\\s*\\/\\s*(\\d+)$/.exec(score || '');
    const n = m ? parseInt(m[1], 10) : 0;
    const total = m ? parseInt(m[2], 10) : 0;
    const pct = total === 0 ? 0 : n / total;
    const color = pct >= 0.8 ? '#1e8e3e' : (pct >= 0.5 ? '#f9ab00' : '#d93025');
    return renderRing(n, total === 0 ? 1 : total, color, score || '0/0');
  }

  function renderWordBar(actual, target) {
    if (!target || target <= 0) {
      return '<span style="color: var(--hz-muted); font-size: 11px;">no target</span>';
    }
    const pct = Math.max(0, Math.min(1.4, actual / target));
    const widthPct = Math.min(100, pct * 100);
    let color = '#1e8e3e';
    if (pct < 0.5) { color = '#f9ab00'; }
    if (pct > 1.2) { color = '#d93025'; }
    return '<div class="hz-words-bar-bg">' +
      '<div class="hz-words-bar-fill" style="width:' + widthPct.toFixed(0) + '%; background:' + color + ';"></div>' +
      '</div>';
  }

  window.addEventListener('message', (event) => {
    const msg = event.data || {};
    if (msg.type !== 'data') { return; }
    document.getElementById('hz-sub').textContent =
      'Last refreshed ' + new Date().toLocaleTimeString();

    const errWrap = document.getElementById('hz-error-wrap');
    errWrap.innerHTML = msg.error
      ? '<div class="hz-error">' + escHtml(msg.error) + '</div>' : '';

    // Document score banner
    const dsWrap = document.getElementById('hz-doc-score-wrap');
    if (typeof msg.documentScore === 'number') {
      const band = msg.documentBand || bandClass(msg.documentScore);
      dsWrap.innerHTML =
        '<span class="hz-doc-score">' + msg.documentScore.toFixed(3) + '</span>' +
        '<span class="hz-band-pill hz-band-pill--' + band + '">' + band.toUpperCase() + '</span>';
    } else {
      dsWrap.textContent = '';
    }

    const sections = msg.sections || [];

    // Sparklines
    const sl = document.getElementById('hz-sparklines');
    if (sections.length === 0) {
      sl.innerHTML = '<div class="hz-empty">No sections detected.</div>';
    } else {
      sl.innerHTML = sections.map((s) => {
        return '<div class="hz-section-row">' +
          '<div><div class="hz-section-name">' + escHtml(s.heading) + '</div>' +
          '<div class="hz-section-meta">' + escHtml(s.type || 'unknown') + '</div></div>' +
          '<div>' + renderSparkline(s.sparkline) + '</div>' +
          '<div class="hz-section-meta" style="text-align:right;">' +
          (s.sparkline.length > 0 ? s.sparkline[s.sparkline.length - 1].toFixed(3) : '—') +
          '</div></div>';
      }).join('');
    }

    // Word bars
    const wb = document.getElementById('hz-word-bars');
    if (sections.length === 0) {
      wb.innerHTML = '<div class="hz-empty">No sections detected.</div>';
    } else {
      wb.innerHTML = sections.map((s) => {
        return '<div class="hz-section-row">' +
          '<div><div class="hz-section-name">' + escHtml(s.heading) + '</div></div>' +
          '<div>' + renderWordBar(s.wordCount, msg.wordsPerSectionTarget) + '</div>' +
          '<div class="hz-section-meta" style="text-align:right;">' + s.wordCount + ' w</div>' +
          '</div>';
      }).join('');
    }

    // Citation rings
    const cr = document.getElementById('hz-citation-rings');
    if (msg.citations) {
      const c = msg.citations;
      const total = Math.max(1, c.missing + c.orphans + c.unused);
      cr.innerHTML = '<div class="hz-rings">' +
        renderRing(c.missing, total, '#d93025', 'Missing') +
        renderRing(c.orphans, total, '#f9ab00', 'Orphans') +
        renderRing(c.unused,  total, '#5f6368', 'Unused') +
        '</div>';
    } else {
      cr.innerHTML = '<div class="hz-empty">Citation data unavailable (open a workspace folder).</div>';
    }

    // Completeness rings
    const er = document.getElementById('hz-completeness-rings');
    if (sections.length === 0) {
      er.innerHTML = '<div class="hz-empty">No checklist data.</div>';
    } else {
      er.innerHTML = '<div class="hz-rings">' +
        sections.map((s) => {
          return '<div style="text-align:center;">' +
            renderCompletenessRing(s.score) +
            '<div class="hz-ring-label" style="font-weight:500;">' + escHtml(s.heading) + '</div>' +
            '</div>';
        }).join('') +
        '</div>';
    }
  });

  vscode.postMessage({ type: 'ready' });
</script>
</body>
</html>`;
}
