"use strict";
/**
 * daemon/review.ts — reviewImport, benchmark  (CONTRACT §A2)
 *
 * Imports: ./transport, ./types
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.reviewImport = reviewImport;
exports.benchmark = benchmark;
const transport_1 = require("./transport");
const types_1 = require("./types");
// ---------------------------------------------------------------------------
// v1.6 public API (CONTRACT §A2)
// ---------------------------------------------------------------------------
/**
 * POST /v1/review-import — accept tracked changes from a lecturer-reviewed DOCX.
 *
 * @param docxBase64     Base64-encoded DOCX bytes.
 * @param originalText   The original markdown text the DOCX was generated from.
 * @param workspaceRoot  Optional absolute workspace path.
 */
async function reviewImport(docxBase64, originalText, workspaceRoot) {
    const body = {
        docx_b64: docxBase64,
        original_text: originalText,
    };
    if (workspaceRoot) {
        body.workspace_root = workspaceRoot;
    }
    return (0, transport_1._post)("/v1/review-import", body);
}
/**
 * POST /v1/benchmark — local breakdown + optional external detectors.
 *
 * The server requires header ``X-External-Benchmark: yes`` when ``external``
 * is true; we send the header unconditionally when the caller asks for it.
 */
async function benchmark(text, detectors, external) {
    const body = { text, detectors };
    const { daemonUrl, token } = (0, transport_1._cfg)();
    const url = `${daemonUrl}/v1/benchmark`;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const globalFetch = globalThis.fetch;
    const headers = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
    };
    if (external) {
        headers["X-External-Benchmark"] = "yes";
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let resp;
    try {
        resp = await globalFetch(url, {
            method: "POST",
            headers,
            body: JSON.stringify(body),
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
    const raw = (await resp.json());
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
//# sourceMappingURL=review.js.map