"use strict";
/**
 * daemon/types.ts — all shared interfaces and the DaemonError class.
 *
 * No internal imports — this is the root of the daemon/ dependency graph.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.DaemonError = void 0;
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
//# sourceMappingURL=types.js.map