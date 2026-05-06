"use strict";
/**
 * daemonClient.ts — typed /v1/ API wrapper for the humanize serve daemon.
 *
 * Agent B depends on these exact exports. Do NOT change signatures without
 * updating plan/VS_CODE_EXTENSION_CONTRACT.md §1.
 *
 * Uses Node 18 native fetch (no npm HTTP dependencies).
 * Reads daemonUrl and token from VS Code settings on every call so changes
 * take effect immediately without reloading the extension.
 *
 * TLS note: the daemon uses a self-signed cert. TLS verification is disabled
 * globally at extension activation time via extension.ts::_patchTls().
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.DaemonError = void 0;
exports.healthCheck = healthCheck;
exports.scoreText = scoreText;
exports.transformText = transformText;
exports.suggestText = suggestText;
exports.listProfiles = listProfiles;
exports.lintText = lintText;
exports.checklist = checklist;
exports.readability = readability;
exports.citations = citations;
exports.listRefs = listRefs;
exports.upsertRef = upsertRef;
exports.deleteRef = deleteRef;
exports.listTemplates = listTemplates;
exports.renderPrompt = renderPrompt;
exports.inspect = inspect;
exports.reviewer = reviewer;
exports.llmRun = llmRun;
exports.doiLookup = doiLookup;
exports.importBibtex = importBibtex;
exports.exportBibtex = exportBibtex;
exports.batchStubOrphans = batchStubOrphans;
exports.transformTextStream = transformTextStream;
exports.benchmark = benchmark;
const vscode = __importStar(require("vscode"));
// ---------------------------------------------------------------------------
// DaemonError
// ---------------------------------------------------------------------------
class DaemonError extends Error {
    constructor(message, status, detail) {
        super(message);
        this.status = status;
        this.detail = detail;
        this.name = "DaemonError";
    }
}
exports.DaemonError = DaemonError;
// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------
/**
 * Read daemon URL and token from the current VS Code workspace configuration.
 * Called fresh on every request so mid-session setting changes take effect.
 */
function _cfg() {
    const cfg = vscode.workspace.getConfiguration("humanizer");
    return {
        daemonUrl: cfg.get("daemonUrl", "https://localhost:9999").replace(/\/$/, ""),
        token: cfg.get("token", ""),
    };
}
/**
 * Human-readable error message per CONTRACT §10.
 */
function _errorMessage(status, detail) {
    if (status === 0) {
        return "Humanizer daemon is not running. Run 'Start Humanizer Daemon' first.";
    }
    if (status === 401) {
        return "Invalid token. Update humanizer.token in settings.";
    }
    if (status === 502) {
        return "LLM stage failed. Untick 'Include LLM' and try again, or check Ollama.";
    }
    return detail || `Daemon returned HTTP ${status}.`;
}
/**
 * Core POST wrapper. Sends JSON body, returns parsed JSON, throws DaemonError
 * on any non-2xx or network failure.
 *
 * The `fetch` global is available in Node 18+ (undici). TLS cert verification
 * is disabled globally at extension activation via `process.env.NODE_TLS_REJECT_UNAUTHORIZED`.
 */
async function _post(path, body) {
    const { daemonUrl, token } = _cfg();
    const url = `${daemonUrl}${path}`;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const globalFetch = 
    // Node 18 exposes fetch as a global; older Node versions used node-fetch.
    // We cast through any to avoid TS complaining about the undici fetch type.
    globalThis.fetch;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let resp;
    try {
        resp = await globalFetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify(body),
        });
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new DaemonError(_errorMessage(0, msg), 0, msg);
    }
    if (!resp.ok) {
        let detail = "";
        try {
            const data = (await resp.json());
            detail = data.detail ?? data.error ?? "";
        }
        catch {
            // ignore JSON parse errors
        }
        throw new DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
    }
    return resp.json();
}
async function _get(path) {
    const { daemonUrl, token } = _cfg();
    const url = `${daemonUrl}${path}`;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const globalFetch = globalThis.fetch;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let resp;
    try {
        resp = await globalFetch(url, {
            method: "GET",
            headers: {
                Authorization: `Bearer ${token}`,
            },
        });
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new DaemonError(_errorMessage(0, msg), 0, msg);
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
        throw new DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
    }
    return resp.json();
}
async function _delete(path) {
    const { daemonUrl, token } = _cfg();
    const url = `${daemonUrl}${path}`;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const globalFetch = globalThis.fetch;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let resp;
    try {
        resp = await globalFetch(url, {
            method: "DELETE",
            headers: {
                Authorization: `Bearer ${token}`,
            },
        });
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new DaemonError(_errorMessage(0, msg), 0, msg);
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
        throw new DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
    }
    return resp.json();
}
// ---------------------------------------------------------------------------
// Public API (CONTRACT §1)
// ---------------------------------------------------------------------------
/**
 * GET /v1/health — confirm the daemon is up and list configured backends.
 */
async function healthCheck() {
    return _get("/v1/health");
}
/**
 * POST /v1/score — score text for AI-risk.
 */
async function scoreText(text, profile) {
    const body = { text };
    if (profile) {
        body.profile = profile;
    }
    return _post("/v1/score", body);
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
    return _post("/v1/transform", body);
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
    const result = await _post("/v1/suggest", body);
    return result.candidates;
}
/**
 * GET /v1/profiles — list available voice profiles.
 */
async function listProfiles() {
    const result = await _get("/v1/profiles");
    return result.profiles;
}
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
    const raw = await _post("/v1/lint", body);
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
    const raw = await _post("/v1/checklist", body);
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
    const raw = await _post("/v1/readability", body);
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
    const raw = await _post("/v1/citations", body);
    return {
        missing: raw.missing ?? [],
        orphans: raw.orphans ?? [],
        unused: (raw.unused ?? []).map((u) => ({ id: u.id, rawApa: u.raw_apa })),
    };
}
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
/**
 * GET /v1/refs?workspace_root={absolute_path} — list references.
 */
async function listRefs(workspaceRoot) {
    const qs = `?workspace_root=${encodeURIComponent(workspaceRoot)}`;
    const raw = await _get(`/v1/refs${qs}`);
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
    const raw = await _post("/v1/refs", body);
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
    await _delete(`/v1/refs/${encodeURIComponent(id)}?${params.toString()}`);
}
// ---------------------------------------------------------------------------
// v1.4 public API (CONTRACT §1 / §5)
// ---------------------------------------------------------------------------
/**
 * GET /v1/research/templates — list every prompt-template id, name and field set.
 */
async function listTemplates() {
    const raw = await _get("/v1/research/templates");
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
    const raw = await _post("/v1/research/prompt", { template_id: templateId, context });
    return {
        prompt: raw.prompt ?? "",
        charCount: raw.char_count ?? raw.charCount ?? (raw.prompt ? raw.prompt.length : 0),
    };
}
/**
 * POST /v1/research/inspect — run deterministic checks on a section + drill-down prompts.
 */
async function inspect(sectionText, sectionType) {
    const raw = await _post("/v1/research/inspect", {
        section_text: sectionText,
        section_type: sectionType,
    });
    return { findings: raw.findings ?? [] };
}
/**
 * POST /v1/research/reviewer — render a peer-reviewer prompt for the document.
 */
async function reviewer(fullText, persona) {
    const raw = await _post("/v1/research/reviewer", {
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
    const raw = await _post("/v1/llm/run", body);
    return {
        output: raw.output ?? "",
        elapsedSeconds: raw.elapsed_seconds ?? raw.elapsedSeconds ?? 0,
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
    const raw = await _post("/v1/refs/doi-lookup", { doi });
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
    const raw = await _post("/v1/refs/bibtex-import", body);
    return { imported: raw.imported, skipped: raw.skipped };
}
/**
 * GET /v1/refs/bibtex-export — export all workspace references as a BibTeX string.
 *
 * The daemon returns Content-Type: text/plain, so we call the underlying fetch
 * directly rather than _get<T> (which calls resp.json()).
 */
async function exportBibtex(workspaceRoot) {
    const { daemonUrl, token } = _cfg();
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
        throw new DaemonError(_errorMessage(0, msg), 0, msg);
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
        throw new DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
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
    const raw = await _post("/v1/refs/batch-stub", {
        orphan_keys: orphanKeys,
        workspace_root: workspaceRoot,
    });
    return {
        created: raw.created,
        skipped: raw.skipped,
        refs: (raw.refs ?? []).map(_refFromRaw),
    };
}
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
    const { daemonUrl, token } = _cfg();
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
        throw new DaemonError(_errorMessage(0, msg), 0, msg);
    }
    // 404 → the v1.5 route is not yet deployed. Fall back to transformText().
    if (resp.status === 404) {
        return transformText(text, opts);
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
        throw new DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
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
                throw new DaemonError(event.message, 500, event.message);
            }
            // Notify caller about stage/determ_step events.
            onProgress(event);
        }
    }
    // Stream ended without a `done` frame — treat as a network error.
    throw new DaemonError("SSE stream closed without a 'done' event.", 0, "Stream ended prematurely.");
}
/**
 * POST /v1/benchmark — local breakdown + optional external detectors.
 *
 * The server requires header ``X-External-Benchmark: yes`` when ``external``
 * is true; we send the header unconditionally when the caller asks for it.
 */
async function benchmark(text, detectors, external) {
    const body = { text, detectors };
    const { daemonUrl, token } = _cfg();
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
        throw new DaemonError(_errorMessage(0, msg), 0, msg);
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
        throw new DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
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
//# sourceMappingURL=daemonClient.js.map