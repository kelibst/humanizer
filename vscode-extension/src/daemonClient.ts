/**
 * daemonClient.ts — typed /v1/ API wrapper for the humanize serve daemon.
 *
 * Agent B depends on these exact exports. Do NOT change signatures without
 * updating plan/VS_CODE_EXTENSION_CONTRACT.md §1.
 *
 * Uses Node 18 native fetch (no npm HTTP dependencies).
 * Reads daemonUrl and token from VS Code settings on every call so changes
 * take effect immediately without reloading the extension.
 *
 * TLS note: the daemon uses a self-signed cert. TLS verification is disabled
 * globally at extension activation time via extension.ts::_patchTls().
 */

import * as vscode from "vscode";

// ---------------------------------------------------------------------------
// DaemonError
// ---------------------------------------------------------------------------

export class DaemonError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail: string
  ) {
    super(message);
    this.name = "DaemonError";
  }
}

// ---------------------------------------------------------------------------
// Result types (CONTRACT §1)
// ---------------------------------------------------------------------------

export interface ScoreResult {
  score: number;
  band: "low" | "medium" | "high";
  features: Array<{
    name: string;
    weight: number;
    value: number;
    contribution: number;
  }>;
}

export interface TransformResult {
  output: string;
  pre_score: number;
  post_score: number;
  llm_used: boolean;
  notes: string[];
}

export interface Candidate {
  text: string;
  score: number;
}

export interface ProfileSummary {
  name: string;
  path: string;
}

// ---------------------------------------------------------------------------
// v1.3 result types (CONTRACT §2)
// ---------------------------------------------------------------------------

export type LintCode =
  | "llm-vocab"
  | "long-sentence"
  | "topic-perfection"
  | "list-overuse"
  | "missing-citation"
  | "orphan-citation";

export interface LintSpan {
  start: number;
  end: number;
  code: LintCode;
  severity: "info" | "warning";
  message: string;
  token?: string;
  suggestions: string[];
}

export interface LintResult {
  spans: LintSpan[];
  elapsedMs: number;
}

export interface ChecklistComponent {
  name: string;
  present: boolean;
  evidence: string;
}

export interface ChecklistSection {
  heading: string;
  lineStart: number;
  lineEnd: number;
  type: string;
  components: ChecklistComponent[];
  score: string;
  wordCount: number;
}

export interface ChecklistResult {
  sections: ChecklistSection[];
}

export interface ReadabilityMetrics {
  wordCount: number;
  sentenceCount: number;
  meanSentenceWords: number;
  sentenceCv: number;
  fleschKincaidGrade: number;
  gunningFog: number;
}

export interface TargetCheck {
  target: number | null;
  actual: number | null;
  ok: boolean | null;
}

export interface ReadabilityResult {
  metrics: ReadabilityMetrics;
  targets: {
    wordsPerSection: TargetCheck;
    fkGradeMax: TargetCheck;
    sentenceCvMin: TargetCheck;
  };
}

export interface CitationFinding {
  start: number;
  end: number;
}

export interface CitationsResult {
  missing: (CitationFinding & { claim: string })[];
  orphans: (CitationFinding & { key: string })[];
  unused: { id: string; rawApa: string }[];
}

export interface Reference {
  id: string;
  authors: string[];
  year: number;
  title: string;
  venue?: string;
  doi?: string;
  url?: string;
  type: "journal" | "book" | "chapter" | "web";
  rawApa: string;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Read daemon URL and token from the current VS Code workspace configuration.
 * Called fresh on every request so mid-session setting changes take effect.
 */
function _cfg(): { daemonUrl: string; token: string } {
  const cfg = vscode.workspace.getConfiguration("humanizer");
  return {
    daemonUrl: cfg.get<string>("daemonUrl", "https://localhost:9999").replace(/\/$/, ""),
    token: cfg.get<string>("token", ""),
  };
}

/**
 * Human-readable error message per CONTRACT §10.
 */
function _errorMessage(status: number, detail: string): string {
  if (status === 0) {
    return "Humanizer daemon is not running. Run 'Start Humanizer Daemon' first.";
  }
  if (status === 401) {
    return "Invalid token. Update humanizer.token in settings.";
  }
  if (status === 502) {
    return "LLM stage failed. Untick 'Include LLM' and try again, or check Ollama.";
  }
  return detail || `Daemon returned HTTP ${status}.`;
}

/**
 * Core POST wrapper. Sends JSON body, returns parsed JSON, throws DaemonError
 * on any non-2xx or network failure.
 *
 * The `fetch` global is available in Node 18+ (undici). TLS cert verification
 * is disabled globally at extension activation via `process.env.NODE_TLS_REJECT_UNAUTHORIZED`.
 */
async function _post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const { daemonUrl, token } = _cfg();
  const url = `${daemonUrl}${path}`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    // Node 18 exposes fetch as a global; older Node versions used node-fetch.
    // We cast through any to avoid TS complaining about the undici fetch type.
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new DaemonError(_errorMessage(0, msg), 0, msg);
  }

  if (!resp.ok) {
    let detail = "";
    try {
      const data = (await resp.json()) as { detail?: string; error?: string };
      detail = data.detail ?? data.error ?? "";
    } catch {
      // ignore JSON parse errors
    }
    throw new DaemonError(_errorMessage(resp.status as number, detail), resp.status as number, detail);
  }

  return resp.json() as Promise<T>;
}

async function _get<T>(path: string): Promise<T> {
  const { daemonUrl, token } = _cfg();
  const url = `${daemonUrl}${path}`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new DaemonError(_errorMessage(0, msg), 0, msg);
  }

  if (!resp.ok) {
    let detail = "";
    try {
      const data = (await resp.json()) as { detail?: string; error?: string };
      detail = data.detail ?? data.error ?? "";
    } catch {
      // ignore
    }
    throw new DaemonError(_errorMessage(resp.status as number, detail), resp.status as number, detail);
  }

  return resp.json() as Promise<T>;
}

async function _delete<T>(path: string): Promise<T> {
  const { daemonUrl, token } = _cfg();
  const url = `${daemonUrl}${path}`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new DaemonError(_errorMessage(0, msg), 0, msg);
  }

  if (!resp.ok) {
    let detail = "";
    try {
      const data = (await resp.json()) as { detail?: string; error?: string };
      detail = data.detail ?? data.error ?? "";
    } catch {
      // ignore
    }
    throw new DaemonError(
      _errorMessage(resp.status as number, detail),
      resp.status as number,
      detail
    );
  }

  return resp.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API (CONTRACT §1)
// ---------------------------------------------------------------------------

/**
 * GET /v1/health — confirm the daemon is up and list configured backends.
 */
export async function healthCheck(): Promise<{ ok: boolean; backends_configured: string[] }> {
  return _get<{ ok: boolean; backends_configured: string[] }>("/v1/health");
}

/**
 * POST /v1/score — score text for AI-risk.
 */
export async function scoreText(text: string, profile?: string): Promise<ScoreResult> {
  const body: Record<string, unknown> = { text };
  if (profile) {
    body.profile = profile;
  }
  return _post<ScoreResult>("/v1/score", body);
}

/**
 * POST /v1/transform — run the humanization pipeline on text.
 */
export async function transformText(
  text: string,
  opts: {
    profile?: string;
    stages?: string[];
    backend?: string;
    model?: string;
  }
): Promise<TransformResult> {
  const body: Record<string, unknown> = { text };
  if (opts.profile) {
    body.profile = opts.profile;
  }
  if (opts.stages && opts.stages.length > 0) {
    body.stages = opts.stages;
  }
  if (opts.backend && opts.backend !== "") {
    body.backend = opts.backend;
  }
  if (opts.model && opts.model !== "") {
    body.model = opts.model;
  }
  return _post<TransformResult>("/v1/transform", body);
}

/**
 * POST /v1/suggest — get N candidate rewrites.
 */
export async function suggestText(
  text: string,
  opts: { n?: number; profile?: string }
): Promise<Candidate[]> {
  const body: Record<string, unknown> = { text };
  if (opts.n !== undefined) {
    body.n = opts.n;
  }
  if (opts.profile) {
    body.profile = opts.profile;
  }
  const result = await _post<{ candidates: Candidate[] }>("/v1/suggest", body);
  return result.candidates;
}

/**
 * GET /v1/profiles — list available voice profiles.
 */
export async function listProfiles(): Promise<ProfileSummary[]> {
  const result = await _get<{ profiles: ProfileSummary[] }>("/v1/profiles");
  return result.profiles;
}

// ---------------------------------------------------------------------------
// v1.3 public API (CONTRACT §2)
// ---------------------------------------------------------------------------

/**
 * POST /v1/lint — flagged spans for editor diagnostics.
 *
 * v1.3 Round-2: the daemon ships `/v1/lint` natively (Agent B). The Round-1
 * `/v1/score` fallback was removed; non-2xx responses surface as `DaemonError`
 * per the v1.2 client convention.
 */
export async function lintText(
  text: string,
  profile?: string,
  include?: LintCode[]
): Promise<LintResult> {
  const body: Record<string, unknown> = { text };
  if (profile) {
    body.profile = profile;
  }
  if (include && include.length > 0) {
    body.include = include;
  }

  const started = Date.now();
  const raw = await _post<{
    spans: LintSpan[];
    elapsed_ms?: number;
    elapsedMs?: number;
  }>("/v1/lint", body);

  return {
    spans: raw.spans ?? [],
    elapsedMs: raw.elapsed_ms ?? raw.elapsedMs ?? Date.now() - started,
  };
}

/**
 * POST /v1/checklist — section completeness per archetype.
 */
export async function checklist(
  text: string,
  profile?: string
): Promise<ChecklistResult> {
  const body: Record<string, unknown> = { text };
  if (profile) {
    body.profile = profile;
  }
  const raw = await _post<{
    sections: Array<{
      heading: string;
      line_start: number;
      line_end: number;
      type: string;
      components: ChecklistComponent[];
      score: string;
      word_count: number;
    }>;
  }>("/v1/checklist", body);
  return {
    sections: (raw.sections ?? []).map((s) => ({
      heading: s.heading,
      lineStart: s.line_start,
      lineEnd: s.line_end,
      type: s.type,
      components: s.components,
      score: s.score,
      wordCount: s.word_count,
    })),
  };
}

/**
 * POST /v1/readability — readability metrics + profile-target compliance.
 */
export async function readability(
  text: string,
  profile?: string
): Promise<ReadabilityResult> {
  const body: Record<string, unknown> = { text };
  if (profile) {
    body.profile = profile;
  }
  const raw = await _post<{
    metrics: {
      word_count: number;
      sentence_count: number;
      mean_sentence_words: number;
      sentence_cv: number;
      flesch_kincaid_grade: number;
      gunning_fog: number;
    };
    targets: {
      words_per_section: TargetCheck;
      fk_grade_max: TargetCheck;
      sentence_cv_min: TargetCheck;
    };
  }>("/v1/readability", body);

  return {
    metrics: {
      wordCount: raw.metrics.word_count,
      sentenceCount: raw.metrics.sentence_count,
      meanSentenceWords: raw.metrics.mean_sentence_words,
      sentenceCv: raw.metrics.sentence_cv,
      fleschKincaidGrade: raw.metrics.flesch_kincaid_grade,
      gunningFog: raw.metrics.gunning_fog,
    },
    targets: {
      wordsPerSection: raw.targets.words_per_section,
      fkGradeMax: raw.targets.fk_grade_max,
      sentenceCvMin: raw.targets.sentence_cv_min,
    },
  };
}

/**
 * POST /v1/citations — citation hygiene against the workspace references.json.
 */
export async function citations(
  text: string,
  workspaceRoot: string,
  profile?: string
): Promise<CitationsResult> {
  const body: Record<string, unknown> = { text, workspace_root: workspaceRoot };
  if (profile) {
    body.profile = profile;
  }
  const raw = await _post<{
    missing: Array<{ start: number; end: number; claim: string }>;
    orphans: Array<{ start: number; end: number; key: string }>;
    unused: Array<{ id: string; raw_apa: string }>;
  }>("/v1/citations", body);
  return {
    missing: raw.missing ?? [],
    orphans: raw.orphans ?? [],
    unused: (raw.unused ?? []).map((u) => ({ id: u.id, rawApa: u.raw_apa })),
  };
}

interface _RawReference {
  id: string;
  authors: string[];
  year: number;
  title: string;
  venue?: string | null;
  doi?: string | null;
  url?: string | null;
  type: "journal" | "book" | "chapter" | "web";
  raw_apa: string;
}

function _refFromRaw(r: _RawReference): Reference {
  return {
    id: r.id,
    authors: r.authors,
    year: r.year,
    title: r.title,
    venue: r.venue ?? undefined,
    doi: r.doi ?? undefined,
    url: r.url ?? undefined,
    type: r.type,
    rawApa: r.raw_apa,
  };
}

function _refToRaw(r: Partial<Reference>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (r.id !== undefined) {
    out.id = r.id;
  }
  if (r.authors !== undefined) {
    out.authors = r.authors;
  }
  if (r.year !== undefined) {
    out.year = r.year;
  }
  if (r.title !== undefined) {
    out.title = r.title;
  }
  if (r.venue !== undefined) {
    out.venue = r.venue;
  }
  if (r.doi !== undefined) {
    out.doi = r.doi;
  }
  if (r.url !== undefined) {
    out.url = r.url;
  }
  if (r.type !== undefined) {
    out.type = r.type;
  }
  if (r.rawApa !== undefined) {
    out.raw_apa = r.rawApa;
  }
  return out;
}

/**
 * GET /v1/refs?workspace_root={absolute_path} — list references.
 */
export async function listRefs(workspaceRoot: string): Promise<Reference[]> {
  const qs = `?workspace_root=${encodeURIComponent(workspaceRoot)}`;
  const raw = await _get<{ refs: _RawReference[] }>(`/v1/refs${qs}`);
  return (raw.refs ?? []).map(_refFromRaw);
}

/**
 * POST /v1/refs — upsert a reference. Server fills in `id` on create.
 *
 * If `documentPath` is provided, the daemon may also rewrite the markdown
 * `## References` block in that file (per CONTRACT §1.6 side-effects).
 */
export async function upsertRef(
  workspaceRoot: string,
  ref: Partial<Reference>,
  documentPath?: string
): Promise<Reference> {
  const body: Record<string, unknown> = {
    ..._refToRaw(ref),
    workspace_root: workspaceRoot,
  };
  if (documentPath) {
    body.document_path = documentPath;
  }
  const raw = await _post<_RawReference>("/v1/refs", body);
  return _refFromRaw(raw);
}

/**
 * DELETE /v1/refs/{id}?workspace_root={absolute_path} — remove a reference.
 */
export async function deleteRef(
  workspaceRoot: string,
  id: string,
  documentPath?: string
): Promise<void> {
  const params = new URLSearchParams({ workspace_root: workspaceRoot });
  if (documentPath) {
    params.set("document_path", documentPath);
  }
  await _delete<{ deleted: boolean }>(
    `/v1/refs/${encodeURIComponent(id)}?${params.toString()}`
  );
}

// ---------------------------------------------------------------------------
// v1.4 result types (CONTRACT §5)
// ---------------------------------------------------------------------------

export interface TemplateField {
  name: string;
  type: string;
  required: boolean;
}

export interface TemplateMeta {
  id: string;
  name: string;
  description: string;
  fields: TemplateField[];
}

export interface ListTemplatesResult {
  templates: TemplateMeta[];
}

export interface PromptResult {
  prompt: string;
  charCount: number;
}

export interface InspectFinding {
  name: string;
  issue: string;
  suggestion: string;
  prompt: string;
}

export interface InspectResult {
  findings: InspectFinding[];
}

export interface ReviewerResult {
  prompt: string;
}

export interface LlmRunResult {
  output: string;
  elapsedSeconds: number;
}

export interface BenchmarkExternalRow {
  detector: string;
  score?: number;
  band?: string;
  confidence?: number | null;
  elapsedMs?: number;
  error?: string;
}

export interface BenchmarkResult {
  humanizer: { score: number; band: string };
  external: BenchmarkExternalRow[];
}

// ---------------------------------------------------------------------------
// v1.4 public API (CONTRACT §1 / §5)
// ---------------------------------------------------------------------------

/**
 * GET /v1/research/templates — list every prompt-template id, name and field set.
 */
export async function listTemplates(): Promise<ListTemplatesResult> {
  const raw = await _get<{
    templates: Array<{
      id: string;
      name: string;
      description?: string;
      fields?: Array<{ name: string; type: string; required: boolean }>;
    }>;
  }>("/v1/research/templates");
  return {
    templates: (raw.templates ?? []).map((t) => ({
      id: t.id,
      name: t.name,
      description: t.description ?? "",
      fields: (t.fields ?? []).map((f) => ({
        name: f.name,
        type: f.type,
        required: f.required,
      })),
    })),
  };
}

/**
 * POST /v1/research/prompt — render a template with the supplied context.
 */
export async function renderPrompt(
  templateId: string,
  context: Record<string, string>
): Promise<PromptResult> {
  const raw = await _post<{ prompt: string; char_count?: number; charCount?: number }>(
    "/v1/research/prompt",
    { template_id: templateId, context }
  );
  return {
    prompt: raw.prompt ?? "",
    charCount: raw.char_count ?? raw.charCount ?? (raw.prompt ? raw.prompt.length : 0),
  };
}

/**
 * POST /v1/research/inspect — run deterministic checks on a section + drill-down prompts.
 */
export async function inspect(
  sectionText: string,
  sectionType: string
): Promise<InspectResult> {
  const raw = await _post<{
    findings: Array<{
      name: string;
      issue: string;
      suggestion: string;
      prompt: string;
    }>;
  }>("/v1/research/inspect", {
    section_text: sectionText,
    section_type: sectionType,
  });
  return { findings: raw.findings ?? [] };
}

/**
 * POST /v1/research/reviewer — render a peer-reviewer prompt for the document.
 */
export async function reviewer(
  fullText: string,
  persona: "r1" | "r2"
): Promise<ReviewerResult> {
  const raw = await _post<{ prompt: string }>("/v1/research/reviewer", {
    full_text: fullText,
    persona,
  });
  return { prompt: raw.prompt ?? "" };
}

/**
 * POST /v1/llm/run — thin wrapper around the configured backend.
 */
export async function llmRun(
  prompt: string,
  backend: string,
  model?: string
): Promise<LlmRunResult> {
  const body: Record<string, unknown> = { prompt, backend };
  if (model) {
    body.model = model;
  }
  const raw = await _post<{
    output: string;
    elapsed_seconds?: number;
    elapsedSeconds?: number;
  }>("/v1/llm/run", body);
  return {
    output: raw.output ?? "",
    elapsedSeconds: raw.elapsed_seconds ?? raw.elapsedSeconds ?? 0,
  };
}

/**
 * POST /v1/benchmark — local breakdown + optional external detectors.
 *
 * The server requires header ``X-External-Benchmark: yes`` when ``external``
 * is true; we send the header unconditionally when the caller asks for it.
 */
export async function benchmark(
  text: string,
  detectors: string[],
  external: boolean
): Promise<BenchmarkResult> {
  const body: Record<string, unknown> = { text, detectors };
  const { daemonUrl, token } = _cfg();
  const url = `${daemonUrl}/v1/benchmark`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (external) {
    headers["X-External-Benchmark"] = "yes";
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new DaemonError(_errorMessage(0, msg), 0, msg);
  }

  if (!resp.ok) {
    let detail = "";
    try {
      const data = (await resp.json()) as { detail?: string; error?: string };
      detail = data.detail ?? data.error ?? "";
    } catch {
      // ignore
    }
    throw new DaemonError(
      _errorMessage(resp.status as number, detail),
      resp.status as number,
      detail
    );
  }

  const raw = (await resp.json()) as {
    humanizer: { score: number; band: string };
    external: Array<{
      detector: string;
      score?: number;
      band?: string;
      confidence?: number | null;
      elapsed_ms?: number;
      elapsedMs?: number;
      error?: string;
    }>;
  };
  return {
    humanizer: raw.humanizer,
    external: (raw.external ?? []).map((row) => ({
      detector: row.detector,
      score: row.score,
      band: row.band,
      confidence: row.confidence,
      elapsedMs: row.elapsed_ms ?? row.elapsedMs,
      error: row.error,
    })),
  };
}
