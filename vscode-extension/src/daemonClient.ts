/**
 * daemonClient.ts — barrel re-export. Do not add logic here.
 *
 * All implementation lives in ./daemon/. This file exists so every existing
 * caller (extension.ts, sectionProcessor.ts, research/index.ts, etc.) compiles
 * without any import-path changes.
 *
 * Agent B depends on these exact exports. Do NOT change signatures without
 * updating plan/VS_CODE_EXTENSION_CONTRACT.md §1.
 */

export { DaemonError } from "./daemon/types";
export type {
  ScoreResult,
  TransformResult,
  Candidate,
  ProfileSummary,
  LintCode,
  LintSpan,
  LintResult,
  ChecklistComponent,
  ChecklistSection,
  ChecklistResult,
  ReadabilityMetrics,
  TargetCheck,
  ReadabilityResult,
  CitationFinding,
  CitationsResult,
  Reference,
  TemplateField,
  TemplateMeta,
  ListTemplatesResult,
  PromptResult,
  InspectFinding,
  InspectResult,
  ReviewerResult,
  LlmRunResult,
  BenchmarkExternalRow,
  BenchmarkResult,
  DoiLookupResult,
  StreamStageEvent,
  DiffSection,
  WordComment,
  ReviewImportResult,
} from "./daemon/types";

export {
  healthCheck,
  exportDocxToFile,
  exportPdfToFile,
  scoreText,
  transformText,
  suggestText,
  listProfiles,
} from "./daemon/core";

export { lintText, checklist, readability, citations } from "./daemon/research";

export { listRefs, upsertRef, deleteRef } from "./daemon/refs";

export { listTemplates, renderPrompt, inspect, reviewer, llmRun } from "./daemon/prompts";

export { doiLookup, importBibtex, exportBibtex, batchStubOrphans } from "./daemon/citations";

export { transformTextStream } from "./daemon/streaming";

export { reviewImport, benchmark } from "./daemon/review";
