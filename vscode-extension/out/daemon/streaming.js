"use strict";
/**
 * daemon/streaming.ts — transformTextStream (SSE parsing)  (CONTRACT §4)
 *
 * Imports: ./transport, ./types
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.transformTextStream = transformTextStream;
const transport_1 = require("./transport");
const types_1 = require("./types");
const core_1 = require("./core");
// ---------------------------------------------------------------------------
// v1.5 public API (CONTRACT §4)
// ---------------------------------------------------------------------------
/**
 * POST /v1/transform/stream — SSE-streamed humanization pipeline.
 *
 * Falls back transparently to ``transformText()`` when the v1.5 route is absent
 * (DaemonError 404). In fallback mode ``onProgress`` is not called; the
 * resolved TransformResult is identical to what ``transformText`` returns.
 *
 * @param text       Input markdown text.
 * @param opts       Same options as transformText().
 * @param onProgress Called for each SSE frame (stage events + determ_step).
 *                   The ``done`` and ``error`` frames are consumed internally
 *                   and never surfaced through this callback.
 * @param signal     Optional AbortSignal for cancellation.
 */
async function transformTextStream(text, opts, onProgress, signal) {
    const { daemonUrl, token } = (0, transport_1._cfg)();
    const url = `${daemonUrl}/v1/transform/stream`;
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const globalFetch = globalThis.fetch;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let resp;
    try {
        resp = await globalFetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
                Accept: "text/event-stream",
            },
            body: JSON.stringify(body),
            ...(signal ? { signal } : {}),
        });
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new types_1.DaemonError((0, transport_1._errorMessage)(0, msg), 0, msg);
    }
    // 404 → the v1.5 route is not yet deployed. Fall back to transformText().
    if (resp.status === 404) {
        return (0, core_1.transformText)(text, opts);
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
    // --- SSE stream parsing ---
    // Each event is: `data: <JSON>\n\n`
    // We read the body as a ReadableStream<Uint8Array> and split on double-newlines.
    const reader = 
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    // eslint-disable-next-line no-constant-condition
    while (true) {
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        buffer += decoder.decode(value, { stream: true });
        // Split on SSE frame delimiter (\n\n).
        const frames = buffer.split("\n\n");
        // Keep the last (possibly incomplete) chunk.
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
            const line = frame.trim();
            if (!line.startsWith("data:")) {
                continue;
            }
            const json = line.slice("data:".length).trim();
            if (!json) {
                continue;
            }
            let event;
            try {
                event = JSON.parse(json);
            }
            catch {
                continue;
            }
            if (event.type === "done") {
                // Terminal event — extract TransformResult and return.
                return {
                    output: event.output,
                    pre_score: event.pre_score,
                    post_score: event.post_score,
                    notes: event.notes,
                    llm_used: event.llm_used,
                };
            }
            if (event.type === "error") {
                throw new types_1.DaemonError(event.message, 500, event.message);
            }
            // Notify caller about stage/determ_step events.
            onProgress(event);
        }
    }
    // Stream ended without a `done` frame — treat as a network error.
    throw new types_1.DaemonError("SSE stream closed without a 'done' event.", 0, "Stream ended prematurely.");
}
//# sourceMappingURL=streaming.js.map