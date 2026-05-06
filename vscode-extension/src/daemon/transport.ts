/**
 * daemon/transport.ts — low-level HTTP helpers.
 *
 * Imports: ./types only (DaemonError).
 * Not re-exported from the barrel (internal to daemon/).
 */

import * as vscode from "vscode";
import { DaemonError } from "./types";

/**
 * Read daemon URL and token from the current VS Code workspace configuration.
 * Called fresh on every request so mid-session setting changes take effect.
 */
export function _cfg(): { daemonUrl: string; token: string } {
  const cfg = vscode.workspace.getConfiguration("humanizer");
  return {
    daemonUrl: cfg.get<string>("daemonUrl", "https://localhost:9999").replace(/\/$/, ""),
    token: cfg.get<string>("token", ""),
  };
}

/**
 * Human-readable error message per CONTRACT §10.
 */
export function _errorMessage(status: number, detail: string): string {
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
export async function _post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const { daemonUrl, token } = _cfg();
  const url = `${daemonUrl}${path}`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    // Node 18 exposes fetch as a global; older Node versions used node-fetch.
    // We cast through any to avoid TS complaining about the undici fetch type.
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
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
      // ignore JSON parse errors
    }
    throw new DaemonError(_errorMessage(resp.status as number, detail), resp.status as number, detail);
  }

  return resp.json() as Promise<T>;
}

export async function _get<T>(path: string): Promise<T> {
  const { daemonUrl, token } = _cfg();
  const url = `${daemonUrl}${path}`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
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
    throw new DaemonError(_errorMessage(resp.status as number, detail), resp.status as number, detail);
  }

  return resp.json() as Promise<T>;
}

export async function _delete<T>(path: string): Promise<T> {
  const { daemonUrl, token } = _cfg();
  const url = `${daemonUrl}${path}`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalFetch: (url: string, init?: Record<string, unknown>) => Promise<any> =
    (globalThis as unknown as { fetch: typeof fetch }).fetch;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resp: any;
  try {
    resp = await globalFetch(url, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
      },
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

  return resp.json() as Promise<T>;
}
