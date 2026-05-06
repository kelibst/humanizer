"use strict";
/**
 * daemon/research.ts — lintText, checklist, readability, citations  (CONTRACT §2)
 *
 * Imports: ./transport, ./types
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.lintText = lintText;
exports.checklist = checklist;
exports.readability = readability;
exports.citations = citations;
const transport_1 = require("./transport");
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
async function lintText(text, profile, include) {
    const body = { text };
    if (profile) {
        body.profile = profile;
    }
    if (include && include.length > 0) {
        body.include = include;
    }
    const started = Date.now();
    const raw = await (0, transport_1._post)("/v1/lint", body);
    return {
        spans: raw.spans ?? [],
        elapsedMs: raw.elapsed_ms ?? raw.elapsedMs ?? Date.now() - started,
    };
}
/**
 * POST /v1/checklist — section completeness per archetype.
 */
async function checklist(text, profile) {
    const body = { text };
    if (profile) {
        body.profile = profile;
    }
    const raw = await (0, transport_1._post)("/v1/checklist", body);
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
async function readability(text, profile) {
    const body = { text };
    if (profile) {
        body.profile = profile;
    }
    const raw = await (0, transport_1._post)("/v1/readability", body);
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
async function citations(text, workspaceRoot, profile) {
    const body = { text, workspace_root: workspaceRoot };
    if (profile) {
        body.profile = profile;
    }
    const raw = await (0, transport_1._post)("/v1/citations", body);
    return {
        missing: raw.missing ?? [],
        orphans: raw.orphans ?? [],
        unused: (raw.unused ?? []).map((u) => ({ id: u.id, rawApa: u.raw_apa })),
    };
}
//# sourceMappingURL=research.js.map