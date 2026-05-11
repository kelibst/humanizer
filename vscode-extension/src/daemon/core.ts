/**
 * daemon/core.ts — healthCheck, exportDocxToFile, scoreText, transformText,
 *                  suggestText, listProfiles  (CONTRACT §1)
 *
 * Imports: ./transport, ./types
 */

import { _get, _post } from "./transport";
import type { ScoreResult, TransformResult, Candidate, ProfileSummary } from "./types";

// ---------------------------------------------------------------------------
// Public API (CONTRACT §1)
// ---------------------------------------------------------------------------

/**
 * GET /v1/health — confirm the daemon is up and list configured backends.
 */
export async function healthCheck(): Promise<{ ok: boolean; backends_configured: string[] }> {
  return _get<{ ok: boolean; backends_configured: string[] }>("/v1/health");
}

/**
 * POST /v1/export/docx — write text as a new .docx at outputPath on the daemon host.
 */
export async function exportDocxToFile(text: string, outputPath: string): Promise<void> {
  await _post<{ ok: boolean; path: string }>("/v1/export/docx", {
    text,
    output_path: outputPath,
  });
}

/**
 * POST /v1/export/pdf — write text as a linked PDF (via LibreOffice/pandoc on the daemon host).
 */
export async function exportPdfToFile(text: string, outputPath: string): Promise<void> {
  await _post<{ ok: boolean; path: string }>("/v1/export/pdf", {
    text,
    output_path: outputPath,
  });
}

/**
 * POST /v1/score — score text for AI-risk.
 */
export async function scoreText(text: string, profile?: string): Promise<ScoreResult> {
  const body: Record<string, unknown> = { text };
  if (profile) {
    body.profile = profile;
  }
  return _post<ScoreResult>("/v1/score", body);
}

/**
 * POST /v1/transform — run the humanization pipeline on text.
 */
export async function transformText(
  text: string,
  opts: {
    profile?: string;
    stages?: string[];
    backend?: string;
    model?: string;
  }
): Promise<TransformResult> {
  const body: Record<string, unknown> = { text };
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
  return _post<TransformResult>("/v1/transform", body);
}

/**
 * POST /v1/suggest — get N candidate rewrites.
 */
export async function suggestText(
  text: string,
  opts: { n?: number; profile?: string }
): Promise<Candidate[]> {
  const body: Record<string, unknown> = { text };
  if (opts.n !== undefined) {
    body.n = opts.n;
  }
  if (opts.profile) {
    body.profile = opts.profile;
  }
  const result = await _post<{ candidates: Candidate[] }>("/v1/suggest", body);
  return result.candidates;
}

/**
 * GET /v1/profiles — list available voice profiles.
 */
export async function listProfiles(): Promise<ProfileSummary[]> {
  const result = await _get<{ profiles: ProfileSummary[] }>("/v1/profiles");
  return result.profiles;
}
