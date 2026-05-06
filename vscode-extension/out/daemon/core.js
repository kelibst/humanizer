"use strict";
/**
 * daemon/core.ts — healthCheck, exportDocxToFile, scoreText, transformText,
 *                  suggestText, listProfiles  (CONTRACT §1)
 *
 * Imports: ./transport, ./types
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.healthCheck = healthCheck;
exports.exportDocxToFile = exportDocxToFile;
exports.scoreText = scoreText;
exports.transformText = transformText;
exports.suggestText = suggestText;
exports.listProfiles = listProfiles;
const transport_1 = require("./transport");
// ---------------------------------------------------------------------------
// Public API (CONTRACT §1)
// ---------------------------------------------------------------------------
/**
 * GET /v1/health — confirm the daemon is up and list configured backends.
 */
async function healthCheck() {
    return (0, transport_1._get)("/v1/health");
}
/**
 * POST /v1/export/docx — write text as a new .docx at outputPath on the daemon host.
 */
async function exportDocxToFile(text, outputPath) {
    await (0, transport_1._post)("/v1/export/docx", {
        text,
        output_path: outputPath,
    });
}
/**
 * POST /v1/score — score text for AI-risk.
 */
async function scoreText(text, profile) {
    const body = { text };
    if (profile) {
        body.profile = profile;
    }
    return (0, transport_1._post)("/v1/score", body);
}
/**
 * POST /v1/transform — run the humanization pipeline on text.
 */
async function transformText(text, opts) {
    const body = { text };
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
    return (0, transport_1._post)("/v1/transform", body);
}
/**
 * POST /v1/suggest — get N candidate rewrites.
 */
async function suggestText(text, opts) {
    const body = { text };
    if (opts.n !== undefined) {
        body.n = opts.n;
    }
    if (opts.profile) {
        body.profile = opts.profile;
    }
    const result = await (0, transport_1._post)("/v1/suggest", body);
    return result.candidates;
}
/**
 * GET /v1/profiles — list available voice profiles.
 */
async function listProfiles() {
    const result = await (0, transport_1._get)("/v1/profiles");
    return result.profiles;
}
//# sourceMappingURL=core.js.map