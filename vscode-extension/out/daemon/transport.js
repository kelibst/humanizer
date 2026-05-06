"use strict";
/**
 * daemon/transport.ts — low-level HTTP helpers.
 *
 * Imports: ./types only (DaemonError).
 * Not re-exported from the barrel (internal to daemon/).
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
exports._cfg = _cfg;
exports._errorMessage = _errorMessage;
exports._post = _post;
exports._get = _get;
exports._delete = _delete;
const vscode = __importStar(require("vscode"));
const types_1 = require("./types");
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
        throw new types_1.DaemonError(_errorMessage(0, msg), 0, msg);
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
        throw new types_1.DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
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
        throw new types_1.DaemonError(_errorMessage(0, msg), 0, msg);
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
        throw new types_1.DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
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
        throw new types_1.DaemonError(_errorMessage(0, msg), 0, msg);
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
        throw new types_1.DaemonError(_errorMessage(resp.status, detail), resp.status, detail);
    }
    return resp.json();
}
//# sourceMappingURL=transport.js.map