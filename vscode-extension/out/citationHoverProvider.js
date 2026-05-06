"use strict";
/**
 * citationHoverProvider.ts — hover cards for in-text citation spans.
 *
 * CONTRACT §4: hover regex = /\([A-Za-z][^)]+,\s*\d{4}[a-z]?\)/
 * Matches "(Smith, 2020)" / "(Smith & Doe, 2020)" / "(Smith et al., 2019a)".
 * On hover, match by last name + year against a 30-second TTL cached
 * listRefs() call. Return a MarkdownString with title / authors / year /
 * venue / DOI link. No hover when no reference matches.
 * Cache is invalidated when references.json is saved.
 *
 * Exports:
 *   registerCitationHoverProvider(ctx)
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
exports.registerCitationHoverProvider = registerCitationHoverProvider;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("./daemonClient");
const CACHE_TTL_MS = 30000;
const _cache = new Map();
function _workspaceRoot() {
    const folders = vscode.workspace.workspaceFolders;
    return folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
}
/** Invalidate cache for the workspace containing ``uri``. */
function _invalidateCache(uri) {
    const folders = vscode.workspace.workspaceFolders ?? [];
    for (const folder of folders) {
        if (uri.fsPath.startsWith(folder.uri.fsPath)) {
            _cache.delete(folder.uri.fsPath);
        }
    }
}
async function _getRefs(root) {
    const entry = _cache.get(root);
    if (entry && Date.now() - entry.at < CACHE_TTL_MS) {
        return entry.refs;
    }
    try {
        const refs = await (0, daemonClient_1.listRefs)(root);
        _cache.set(root, { refs, at: Date.now() });
        return refs;
    }
    catch (err) {
        // Daemon down / not configured — return empty; do not surface an error
        // toast from hover (that would be very noisy).
        if (err instanceof daemonClient_1.DaemonError) {
            return [];
        }
        return [];
    }
}
// ---------------------------------------------------------------------------
// Citation span regex
// ---------------------------------------------------------------------------
// Matches "(Smith, 2020)" / "(Smith & Doe, 2020)" / "(Smith et al., 2019a)"
// CONTRACT §A2 hover regex.
const CITATION_RE = /\([A-Za-z][^)]+,\s*\d{4}[a-z]?\)/g;
/** Extract the first last name and year from a raw citation key string. */
function _parseCitationKey(raw) {
    // raw looks like "(Smith, 2020)" or "(Smith & Doe, 2020)" or "(Smith et al., 2019a)"
    const inner = raw.replace(/^\(/, "").replace(/\)$/, "");
    // Year is the 4-digit number (possibly followed by one letter) near the end
    const yearMatch = /(\d{4})[a-z]?$/.exec(inner.trim());
    if (!yearMatch) {
        return undefined;
    }
    const year = parseInt(yearMatch[1], 10);
    // Last name: everything up to the first "&", "et al", or ","
    const namePart = inner.split(/&|et\s+al|,/)[0].trim();
    if (!namePart) {
        return undefined;
    }
    return { lastName: namePart, year };
}
/** Match a parsed key against a reference by last name (case-insensitive) + year. */
function _matchRef(lastName, year, refs) {
    const lowerLast = lastName.toLowerCase();
    return refs.find((r) => {
        if (r.year !== year) {
            return false;
        }
        if (!r.authors || r.authors.length === 0) {
            return false;
        }
        // authors[0] is in "Last, F." format; extract the last name.
        const authorLast = r.authors[0].split(",")[0].trim().toLowerCase();
        return authorLast === lowerLast || authorLast.startsWith(lowerLast);
    });
}
// ---------------------------------------------------------------------------
// Hover provider
// ---------------------------------------------------------------------------
class CitationHoverProvider {
    async provideHover(document, position, _token) {
        const root = _workspaceRoot();
        if (!root) {
            return undefined;
        }
        // Find any citation span on the current line that contains the cursor.
        const lineText = document.lineAt(position.line).text;
        let match;
        CITATION_RE.lastIndex = 0;
        while ((match = CITATION_RE.exec(lineText)) !== null) {
            const start = match.index;
            const end = start + match[0].length;
            if (position.character < start || position.character > end) {
                continue;
            }
            // Found a citation span at the cursor — parse and look up.
            const parsed = _parseCitationKey(match[0]);
            if (!parsed) {
                continue;
            }
            const refs = await _getRefs(root);
            const ref = _matchRef(parsed.lastName, parsed.year, refs);
            if (!ref) {
                // No match — return undefined so VS Code shows no hover.
                return undefined;
            }
            // Build hover card.
            const md = new vscode.MarkdownString(undefined, true);
            md.isTrusted = true;
            md.appendMarkdown(`**${ref.title}**\n\n`);
            md.appendMarkdown(`*${ref.authors.join("; ")}* (${ref.year})\n\n`);
            if (ref.venue) {
                md.appendMarkdown(`${ref.venue}\n\n`);
            }
            if (ref.doi) {
                md.appendMarkdown(`[${ref.doi}](https://doi.org/${ref.doi})\n\n`);
            }
            const hoverRange = new vscode.Range(new vscode.Position(position.line, start), new vscode.Position(position.line, end));
            return new vscode.Hover(md, hoverRange);
        }
        return undefined;
    }
}
// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------
/**
 * Register the hover provider and references.json file-watcher.
 * Call once from activate().
 */
function registerCitationHoverProvider(ctx) {
    ctx.subscriptions.push(vscode.languages.registerHoverProvider({ language: "markdown" }, new CitationHoverProvider()));
    // Invalidate the cache whenever references.json changes.
    const watcher = vscode.workspace.createFileSystemWatcher("**/references.json", false, // onCreate
    false, // onChange
    true // do not watch deletes (no-op for cache)
    );
    watcher.onDidChange(_invalidateCache);
    watcher.onDidCreate(_invalidateCache);
    ctx.subscriptions.push(watcher);
}
//# sourceMappingURL=citationHoverProvider.js.map