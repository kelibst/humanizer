/**
 * daemon/research.ts — lintText, checklist, readability, citations  (CONTRACT §2)
 *
 * Imports: ./transport, ./types
 */

import { _post } from "./transport";
import type {
  LintCode,
  LintSpan,
  LintResult,
  ChecklistComponent,
  ChecklistResult,
  ReadabilityResult,
  TargetCheck,
  CitationsResult,
} from "./types";

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
