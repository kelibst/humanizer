"use strict";
/**
 * daemon/citations.ts — doiLookup, importBibtex, exportBibtex, batchStubOrphans
 *                        (CONTRACT §4)
 *
 * Imports: ./transport, ./types
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.doiLookup = doiLookup;
exports.importBibtex = importBibtex;
exports.exportBibtex = exportBibtex;
exports.batchStubOrphans = batchStubOrphans;
const transport_1 = require("./transport");
const types_1 = require("./types");
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
// ---------------------------------------------------------------------------
// v1.5 public API (CONTRACT §4)
// ---------------------------------------------------------------------------
/**
 * POST /v1/refs/doi-lookup — resolve a DOI via CrossRef.
 * Throws DaemonError(404) when the DOI is not found.
 * Throws DaemonError(502) when CrossRef is unreachable.
 * Result is NOT saved to references.json; the caller calls upsertRef() after
 * user confirmation.
 */
async function doiLookup(doi) {
    const raw = await (0, transport_1._post)("/v1/refs/doi-lookup", { doi });
    return {
        authors: raw.authors,
        year: raw.year,
        title: raw.title,
        venue: raw.venue ?? undefined,
        doi: raw.doi,
        type: raw.type,
        rawApa: raw.raw_apa,
    };
}
/**
 * POST /v1/refs/bibtex-import — parse and import BibTeX text into references.json.
 *
 * @param bibtexContent  Raw BibTeX text.
 * @param workspaceRoot  Absolute path to the workspace root that owns references.json.
 * @param documentPath   Optional absolute path to the active .md file; when
 *                       supplied the daemon regenerates the ## References block.
 */
async function importBibtex(bibtexContent, workspaceRoot, documentPath) {
    const body = {
        bibtex_text: bibtexContent,
        workspace_root: workspaceRoot,
    };
    if (documentPath) {
        body.document_path = documentPath;
    }
    const raw = await (0, transport_1._post)("/v1/refs/bibtex-import", body);
    return { imported: raw.imported, skipped: raw.skipped };
}
/**
 * GET /v1/refs/bibtex-export — export all workspace references as a BibTeX string.
 *
 * The daemon returns Content-Type: text/plain, so we call the underlying fetch
 * directly rather than _get<T> (which calls resp.json()).
 */
async function exportBibtex(workspaceRoot) {
    const { daemonUrl, token } = (0, transport_1._cfg)();
    const url = `${daemonUrl}/v1/refs/bibtex-export` +
        `?workspace_root=${encodeURIComponent(workspaceRoot)}`;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const globalFetch = globalThis.fetch;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let resp;
    try {
        resp = await globalFetch(url, {
            method: "GET",
            headers: { Authorization: `Bearer ${token}` },
        });
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new types_1.DaemonError((0, transport_1._errorMessage)(0, msg), 0, msg);
    }
    if (!resp.ok) {
        let detail = "";
        try {
            const data = (await resp.json());
            detail = data.detail ?? data.error ?? "";
        }
        catch {
            // ignore
        }
        throw new types_1.DaemonError((0, transport_1._errorMessage)(resp.status, detail), resp.status, detail);
    }
    return resp.text();
}
/**
 * POST /v1/refs/batch-stub — create stub references for orphan citation keys.
 *
 * Stubs have ``title = "[TITLE UNKNOWN]"``, ``doi = null``, ``type = "journal"``.
 * Collisions (same derived id) are silently skipped.
 */
async function batchStubOrphans(orphanKeys, workspaceRoot) {
    const raw = await (0, transport_1._post)("/v1/refs/batch-stub", {
        orphan_keys: orphanKeys,
        workspace_root: workspaceRoot,
    });
    return {
        created: raw.created,
        skipped: raw.skipped,
        refs: (raw.refs ?? []).map(_refFromRaw),
    };
}
//# sourceMappingURL=citations.js.map