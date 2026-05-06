/**
 * daemon/types.ts — all shared interfaces and the DaemonError class.
 *
 * No internal imports — this is the root of the daemon/ dependency graph.
 */

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
// v1.5 result types (CONTRACT §4)
// ---------------------------------------------------------------------------

export interface DoiLookupResult {
  authors: string[];
  year: number;
  title: string;
  venue?: string;
  doi: string;
  type: "journal" | "book" | "chapter" | "web";
  rawApa: string;
}

/**
 * SSE event union — one frame per event on the `/v1/transform/stream` SSE channel.
 */
export type StreamStageEvent =
  | { type: "stage_start"; stage: string }
  | { type: "stage_done"; stage: string; elapsed_s: number }
  | { type: "stage_skipped"; stage: string; reason: string }
  | { type: "determ_step"; step: string; count: number }
  | {
      type: "done";
      output: string;
      pre_score: number;
      post_score: number;
      notes: string[];
      llm_used: boolean;
    }
  | { type: "error"; message: string };

// ---------------------------------------------------------------------------
// v1.6 result types (CONTRACT §A2)
// ---------------------------------------------------------------------------

export interface DiffSection {
  original: string;
  revised: string;
  changed: boolean;
  paragraph_idx: number;
}

export interface WordComment {
  id: string;
  author: string;
  date: string;
  text: string;
  paragraph_idx: number;
}

export interface ReviewImportResult {
  accepted_text: string;
  diff_sections: DiffSection[];
  comments: WordComment[];
  post_score: { score: number; band: string };
}
