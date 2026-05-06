/**
 * daemon/review.ts — reviewImport, benchmark  (CONTRACT §A2)
 *
 * Imports: ./transport, ./types
 */

import { _cfg, _errorMessage, _post } from "./transport";
import { DaemonError } from "./types";
import type { ReviewImportResult, BenchmarkResult } from "./types";

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
export async function reviewImport(
  docxBase64: string,
  originalText: string,
  workspaceRoot?: string
): Promise<ReviewImportResult> {
  const body: Record<string, unknown> = {
    docx_b64: docxBase64,
    original_text: originalText,
  };
  if (workspaceRoot) {
    body.workspace_root = workspaceRoot;
  }
  return _post<ReviewImportResult>("/v1/review-import", body);
}

/**
 * POST /v1/benchmark — local breakdown + optional external detectors.
 *
 * The server requires header ``X-External-Benchmark: yes`` when ``external``
 * is true; we send the header unconditionally when the caller asks for it.
 */
export async function benchmark(
  text: string,
  detectors: string[],
  external: boolean
): Promise<BenchmarkResult> {
  const body: Record<string, unknown> = { text, detectors };
  const { daemonUrl, token } = _cfg();
  const url = `${daemonUrl}/v1/benchmark`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (external) {
    headers["X-External-Benchmark"] = "yes";
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
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

  const raw = (await resp.json()) as {
    humanizer: { score: number; band: string };
    external: Array<{
      detector: string;
      score?: number;
      band?: string;
      confidence?: number | null;
      elapsed_ms?: number;
      elapsedMs?: number;
      error?: string;
    }>;
  };
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
