/**
 * daemon/refs.ts — listRefs, upsertRef, deleteRef  (CONTRACT §1 / §3)
 *
 * Imports: ./transport, ./types
 * _refFromRaw and _refToRaw are private helpers — not re-exported.
 */

import { _get, _post, _delete } from "./transport";
import type { Reference } from "./types";

// ---------------------------------------------------------------------------
// Private helpers
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

function _refToRaw(r: Partial<Reference>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
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
export async function listRefs(workspaceRoot: string): Promise<Reference[]> {
  const qs = `?workspace_root=${encodeURIComponent(workspaceRoot)}`;
  const raw = await _get<{ refs: _RawReference[] }>(`/v1/refs${qs}`);
  return (raw.refs ?? []).map(_refFromRaw);
}

/**
 * POST /v1/refs — upsert a reference. Server fills in `id` on create.
 *
 * If `documentPath` is provided, the daemon may also rewrite the markdown
 * `## References` block in that file (per CONTRACT §1.6 side-effects).
 */
export async function upsertRef(
  workspaceRoot: string,
  ref: Partial<Reference>,
  documentPath?: string
): Promise<Reference> {
  const body: Record<string, unknown> = {
    ..._refToRaw(ref),
    workspace_root: workspaceRoot,
  };
  if (documentPath) {
    body.document_path = documentPath;
  }
  const raw = await _post<_RawReference>("/v1/refs", body);
  return _refFromRaw(raw);
}

/**
 * DELETE /v1/refs/{id}?workspace_root={absolute_path} — remove a reference.
 */
export async function deleteRef(
  workspaceRoot: string,
  id: string,
  documentPath?: string
): Promise<void> {
  const params = new URLSearchParams({ workspace_root: workspaceRoot });
  if (documentPath) {
    params.set("document_path", documentPath);
  }
  await _delete<{ deleted: boolean }>(
    `/v1/refs/${encodeURIComponent(id)}?${params.toString()}`
  );
}
