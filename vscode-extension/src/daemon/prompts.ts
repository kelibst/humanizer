/**
 * daemon/prompts.ts — listTemplates, renderPrompt, inspect, reviewer, llmRun
 *                     (CONTRACT §1 / §5)
 *
 * Imports: ./transport, ./types
 */

import { _get, _post } from "./transport";
import type {
  ListTemplatesResult,
  PromptResult,
  InspectResult,
  ReviewerResult,
  LlmRunResult,
} from "./types";

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
