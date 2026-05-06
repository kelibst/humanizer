"use strict";
/**
 * daemon/refs.ts — listRefs, upsertRef, deleteRef  (CONTRACT §1 / §3)
 *
 * Imports: ./transport, ./types
 * _refFromRaw and _refToRaw are private helpers — not re-exported.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.listRefs = listRefs;
exports.upsertRef = upsertRef;
exports.deleteRef = deleteRef;
const transport_1 = require("./transport");
function _refFromRaw(r) {
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
function _refToRaw(r) {
    const out = {};
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
// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
/**
 * GET /v1/refs?workspace_root={absolute_path} — list references.
 */
async function listRefs(workspaceRoot) {
    const qs = `?workspace_root=${encodeURIComponent(workspaceRoot)}`;
    const raw = await (0, transport_1._get)(`/v1/refs${qs}`);
    return (raw.refs ?? []).map(_refFromRaw);
}
/**
 * POST /v1/refs — upsert a reference. Server fills in `id` on create.
 *
 * If `documentPath` is provided, the daemon may also rewrite the markdown
 * `## References` block in that file (per CONTRACT §1.6 side-effects).
 */
async function upsertRef(workspaceRoot, ref, documentPath) {
    const body = {
        ..._refToRaw(ref),
        workspace_root: workspaceRoot,
    };
    if (documentPath) {
        body.document_path = documentPath;
    }
    const raw = await (0, transport_1._post)("/v1/refs", body);
    return _refFromRaw(raw);
}
/**
 * DELETE /v1/refs/{id}?workspace_root={absolute_path} — remove a reference.
 */
async function deleteRef(workspaceRoot, id, documentPath) {
    const params = new URLSearchParams({ workspace_root: workspaceRoot });
    if (documentPath) {
        params.set("document_path", documentPath);
    }
    await (0, transport_1._delete)(`/v1/refs/${encodeURIComponent(id)}?${params.toString()}`);
}
//# sourceMappingURL=refs.js.map