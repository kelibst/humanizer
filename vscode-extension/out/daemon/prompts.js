"use strict";
/**
 * daemon/prompts.ts — listTemplates, renderPrompt, inspect, reviewer, llmRun
 *                     (CONTRACT §1 / §5)
 *
 * Imports: ./transport, ./types
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.listTemplates = listTemplates;
exports.renderPrompt = renderPrompt;
exports.inspect = inspect;
exports.reviewer = reviewer;
exports.llmRun = llmRun;
const transport_1 = require("./transport");
// ---------------------------------------------------------------------------
// v1.4 public API (CONTRACT §1 / §5)
// ---------------------------------------------------------------------------
/**
 * GET /v1/research/templates — list every prompt-template id, name and field set.
 */
async function listTemplates() {
    const raw = await (0, transport_1._get)("/v1/research/templates");
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
async function renderPrompt(templateId, context) {
    const raw = await (0, transport_1._post)("/v1/research/prompt", { template_id: templateId, context });
    return {
        prompt: raw.prompt ?? "",
        charCount: raw.char_count ?? raw.charCount ?? (raw.prompt ? raw.prompt.length : 0),
    };
}
/**
 * POST /v1/research/inspect — run deterministic checks on a section + drill-down prompts.
 */
async function inspect(sectionText, sectionType) {
    const raw = await (0, transport_1._post)("/v1/research/inspect", {
        section_text: sectionText,
        section_type: sectionType,
    });
    return { findings: raw.findings ?? [] };
}
/**
 * POST /v1/research/reviewer — render a peer-reviewer prompt for the document.
 */
async function reviewer(fullText, persona) {
    const raw = await (0, transport_1._post)("/v1/research/reviewer", {
        full_text: fullText,
        persona,
    });
    return { prompt: raw.prompt ?? "" };
}
/**
 * POST /v1/llm/run — thin wrapper around the configured backend.
 */
async function llmRun(prompt, backend, model) {
    const body = { prompt, backend };
    if (model) {
        body.model = model;
    }
    const raw = await (0, transport_1._post)("/v1/llm/run", body);
    return {
        output: raw.output ?? "",
        elapsedSeconds: raw.elapsed_seconds ?? raw.elapsedSeconds ?? 0,
    };
}
//# sourceMappingURL=prompts.js.map