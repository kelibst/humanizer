/**
 * daemon/citations.ts — doiLookup, importBibtex, exportBibtex, batchStubOrphans
 *                        (CONTRACT §4)
 *
 * Imports: ./transport, ./types
 */

import { _cfg, _errorMessage, _post } from "./transport";
import { DaemonError } from "./types";
import type { DoiLookupResult, Reference } from "./types";

// ---------------------------------------------------------------------------
// Private helper (shared with refs.ts pattern — duplicated to keep modules independent)
// ---------------------------------------------------------------------------

interface _RawReference {
  id: string;
  authors: string[];
  year: number;
  title: string;
  venue?: string | null;
  doi?: string | null;
  url?: string | null;
  type: "journal" | "book" | "chapter" | "web";
  raw_apa: string;
}

function _refFromRaw(r: _RawReference): Reference {
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
export async function doiLookup(doi: string): Promise<DoiLookupResult> {
  const raw = await _post<{
    authors: string[];
    year: number;
    title: string;
    venue?: string | null;
    doi: string;
    type: "journal" | "book" | "chapter" | "web";
    raw_apa: string;
  }>("/v1/refs/doi-lookup", { doi });
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
export async function importBibtex(
  bibtexContent: string,
  workspaceRoot: string,
  documentPath?: string
): Promise<{ imported: number; skipped: number }> {
  const body: Record<string, unknown> = {
    bibtex_text: bibtexContent,
    workspace_root: workspaceRoot,
  };
  if (documentPath) {
    body.document_path = documentPath;
  }
  const raw = await _post<{ imported: number; skipped: number }>(
    "/v1/refs/bibtex-import",
    body
  );
  return { imported: raw.imported, skipped: raw.skipped };
}

/**
 * GET /v1/refs/bibtex-export — export all workspace references as a BibTeX string.
 *
 * The daemon returns Content-Type: text/plain, so we call the underlying fetch
 * directly rather than _get<T> (which calls resp.json()).
 */
export async function exportBibtex(workspaceRoot: string): Promise<string> {
  const { daemonUrl, token } = _cfg();
  const url =
    `${daemonUrl}/v1/refs/bibtex-export` +
    `?workspace_root=${encodeURIComponent(workspaceRoot)}`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new DaemonError(_errorMessage(0, msg), 0, msg);
  }

  if (!resp.ok) {
    let detail = "";
    try {
      const data = (await resp.json()) as { detail?: string; error?: string };
      detail = data.detail ?? data.error ?? "";
    } catch {
      // ignore
    }
    throw new DaemonError(
      _errorMessage(resp.status as number, detail),
      resp.status as number,
      detail
    );
  }

  return resp.text() as Promise<string>;
}

/**
 * POST /v1/refs/batch-stub — create stub references for orphan citation keys.
 *
 * Stubs have ``title = "[TITLE UNKNOWN]"``, ``doi = null``, ``type = "journal"``.
 * Collisions (same derived id) are silently skipped.
 */
export async function batchStubOrphans(
  orphanKeys: string[],
  workspaceRoot: string
): Promise<{ created: number; skipped: number; refs: Reference[] }> {
  const raw = await _post<{
    created: number;
    skipped: number;
    refs: _RawReference[];
  }>("/v1/refs/batch-stub", {
    orphan_keys: orphanKeys,
    workspace_root: workspaceRoot,
  });
  return {
    created: raw.created,
    skipped: raw.skipped,
    refs: (raw.refs ?? []).map(_refFromRaw),
  };
}
