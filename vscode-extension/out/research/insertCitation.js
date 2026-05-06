"use strict";
/**
 * insertCitation.ts — ``humanizer.insertCitation`` Quick-Pick command.
 *
 * Lists ``references.json`` entries via ``GET /v1/refs``, lets the user pick
 * one, inserts ``(LastAuthor, Year)`` (or the et-al form for 3+ authors) at
 * the cursor, and re-saves the same entry through ``POST /v1/refs`` with the
 * active document's path so the markdown ``## References`` block regenerates.
 *
 * If no workspace folder is open, surfaces a friendly warning and bails.
 *
 * If the user picks "+ New reference…", a chained Quick-Pick collects the
 * minimum APA-7 fields (authors, year, title) and POSTs a fresh record.
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
exports.citationKey = citationKey;
exports.runInsertCitation = runInsertCitation;
exports.registerInsertCitationCommand = registerInsertCitationCommand;
const vscode = __importStar(require("vscode"));
const daemonClient_1 = require("../daemonClient");
const NEW_REF_LABEL = "$(plus) New reference…";
const DOI_LOOKUP_LABEL = "$(search) Look up by DOI…";
const MANUAL_LABEL = "$(edit) Enter details manually";
function _workspaceRoot() {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        return undefined;
    }
    return folders[0].uri.fsPath;
}
function _lastName(author) {
    const a = (author || "").trim();
    if (!a) {
        return "Anon";
    }
    if (a.includes(",")) {
        return a.split(",")[0].trim();
    }
    const parts = a.split(/\s+/);
    return parts[parts.length - 1];
}
function citationKey(ref) {
    if (!ref.authors || ref.authors.length === 0) {
        return `(Anon, ${ref.year})`;
    }
    if (ref.authors.length >= 3) {
        return `(${_lastName(ref.authors[0])} et al., ${ref.year})`;
    }
    if (ref.authors.length === 2) {
        return `(${_lastName(ref.authors[0])} & ${_lastName(ref.authors[1])}, ${ref.year})`;
    }
    return `(${_lastName(ref.authors[0])}, ${ref.year})`;
}
async function _promptForNewReference(workspaceRoot, documentPath) {
    // v1.5: first show a mode Quick-Pick — DOI lookup vs manual entry.
    const modePick = await vscode.window.showQuickPick([
        {
            label: DOI_LOOKUP_LABEL,
            description: "Fetch metadata from CrossRef by DOI",
            mode: "doi",
        },
        {
            label: MANUAL_LABEL,
            description: "Enter authors, year and title yourself",
            mode: "manual",
        },
    ], { placeHolder: "How would you like to add this reference?" });
    if (!modePick) {
        return undefined;
    }
    if (modePick.mode === "doi") {
        return _promptViaDoi(workspaceRoot, documentPath);
    }
    return _promptManually(workspaceRoot, documentPath);
}
/**
 * DOI lookup flow per CONTRACT §A2 / BRIEF §5.
 *
 * 1. Input box for DOI.
 * 2. Validate `^10\.\d{4,}`.
 * 3. Spinner → doiLookup().
 * 4. Confirm Quick-Pick showing resolved metadata.
 * 5. upsertRef() → return reference.
 *
 * DaemonError(404) → warn and fall through to manual entry.
 * Other error → abort and show error.
 */
async function _promptViaDoi(workspaceRoot, documentPath) {
    const doiInput = await vscode.window.showInputBox({
        title: "Look up by DOI",
        prompt: "Paste the DOI (e.g. 10.1000/xyz)",
        validateInput: (v) => /^10\.\d{4,}/.test(v.trim())
            ? null
            : "DOI must start with 10.NNNN — e.g. 10.1038/nature12345",
    });
    if (!doiInput) {
        return undefined;
    }
    const doi = doiInput.trim();
    // Spinner while fetching
    let resolved;
    try {
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: `Humanizer: resolving DOI ${doi}…`,
            cancellable: false,
        }, async () => {
            resolved = await (0, daemonClient_1.doiLookup)(doi);
        });
    }
    catch (err) {
        if (err instanceof daemonClient_1.DaemonError && err.status === 404) {
            vscode.window.showWarningMessage(`Humanizer: DOI not found (${doi}). Falling through to manual entry.`);
            return _promptManually(workspaceRoot, documentPath);
        }
        const msg = err instanceof daemonClient_1.DaemonError
            ? err.message
            : err instanceof Error
                ? err.message
                : String(err);
        vscode.window.showErrorMessage(`Humanizer: DOI lookup failed — ${msg}`);
        return undefined;
    }
    if (!resolved) {
        return undefined;
    }
    // Confirmation Quick-Pick showing the resolved metadata.
    const authorStr = resolved.authors.slice(0, 3).join("; ") +
        (resolved.authors.length > 3 ? " et al." : "");
    const confirm = await vscode.window.showQuickPick([
        {
            label: "$(check) Use this reference",
            description: resolved.title,
            detail: `${authorStr} (${resolved.year})${resolved.venue ? " · " + resolved.venue : ""}`,
            accept: true,
        },
        {
            label: "$(close) Cancel",
            description: "",
            accept: false,
        },
    ], { placeHolder: "Confirm DOI result" });
    if (!confirm || !confirm.accept) {
        return undefined;
    }
    // Save the resolved reference to references.json.
    const partial = {
        authors: resolved.authors,
        year: resolved.year,
        title: resolved.title,
        type: resolved.type,
        doi: resolved.doi,
    };
    if (resolved.venue) {
        partial.venue = resolved.venue;
    }
    if (resolved.rawApa) {
        partial.rawApa = resolved.rawApa;
    }
    try {
        return await (0, daemonClient_1.upsertRef)(workspaceRoot, partial, documentPath);
    }
    catch (err) {
        const msg = err instanceof daemonClient_1.DaemonError
            ? err.message
            : err instanceof Error
                ? err.message
                : String(err);
        vscode.window.showErrorMessage(`Humanizer: ${msg}`);
        return undefined;
    }
}
/** Original manual-entry flow (extracted from the old _promptForNewReference). */
async function _promptManually(workspaceRoot, documentPath) {
    const authorsRaw = await vscode.window.showInputBox({
        title: "New reference — Authors",
        prompt: 'Authors in APA format. Use ";" to separate, e.g. "Smith, J.; Doe, A."',
        validateInput: (v) => (v && v.trim() ? null : "At least one author is required."),
    });
    if (!authorsRaw) {
        return undefined;
    }
    const authors = authorsRaw
        .split(";")
        .map((a) => a.trim())
        .filter((a) => a.length > 0);
    const yearRaw = await vscode.window.showInputBox({
        title: "New reference — Year",
        prompt: "4-digit year",
        validateInput: (v) => /^\d{4}$/.test(v.trim()) ? null : "Year must be 4 digits.",
    });
    if (!yearRaw) {
        return undefined;
    }
    const year = parseInt(yearRaw.trim(), 10);
    const title = await vscode.window.showInputBox({
        title: "New reference — Title",
        prompt: "Title of the work",
        validateInput: (v) => (v && v.trim() ? null : "Title is required."),
    });
    if (!title) {
        return undefined;
    }
    const venue = await vscode.window.showInputBox({
        title: "New reference — Venue (optional)",
        prompt: "Journal / publisher / website (leave blank to skip)",
    });
    const partial = {
        authors,
        year,
        title: title.trim(),
        type: "journal",
    };
    if (venue && venue.trim()) {
        partial.venue = venue.trim();
    }
    try {
        return await (0, daemonClient_1.upsertRef)(workspaceRoot, partial, documentPath);
    }
    catch (err) {
        const msg = err instanceof daemonClient_1.DaemonError
            ? err.message
            : err instanceof Error
                ? err.message
                : String(err);
        vscode.window.showErrorMessage(`Humanizer: ${msg}`);
        return undefined;
    }
}
async function runInsertCitation() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "markdown") {
        vscode.window.showWarningMessage("Open a Markdown file to insert a citation.");
        return;
    }
    const root = _workspaceRoot();
    if (!root) {
        vscode.window.showWarningMessage("Open a workspace folder so Humanizer can find references.json.");
        return;
    }
    let refs;
    try {
        refs = await (0, daemonClient_1.listRefs)(root);
    }
    catch (err) {
        const msg = err instanceof daemonClient_1.DaemonError
            ? err.message
            : err instanceof Error
                ? err.message
                : String(err);
        vscode.window.showErrorMessage(`Humanizer: ${msg}`);
        return;
    }
    const items = refs.map((r) => ({
        label: citationKey(r),
        description: r.title,
        detail: r.rawApa,
        ref: r,
    }));
    items.push({ label: NEW_REF_LABEL, isNew: true });
    const pick = await vscode.window.showQuickPick(items, {
        placeHolder: refs.length > 0
            ? "Select a reference to cite, or create a new one."
            : "No references yet — pick 'New reference…' to add one.",
        matchOnDescription: true,
        matchOnDetail: true,
    });
    if (!pick) {
        return;
    }
    const documentPath = editor.document.uri.fsPath;
    let ref = pick.ref;
    if (pick.isNew) {
        ref = await _promptForNewReference(root, documentPath);
        if (!ref) {
            return;
        }
    }
    else if (ref) {
        // Re-POST the picked ref with documentPath so the markdown References
        // block regenerates if the markers are missing.
        try {
            ref = await (0, daemonClient_1.upsertRef)(root, {
                id: ref.id,
                authors: ref.authors,
                year: ref.year,
                title: ref.title,
                venue: ref.venue ?? undefined,
                doi: ref.doi ?? undefined,
                url: ref.url ?? undefined,
                type: ref.type,
                rawApa: ref.rawApa,
            }, documentPath);
        }
        catch {
            // Non-fatal; the in-text citation is still the goal.
        }
    }
    if (!ref) {
        return;
    }
    const key = citationKey(ref);
    await editor.edit((eb) => {
        if (editor.selection.isEmpty) {
            eb.insert(editor.selection.active, key);
        }
        else {
            eb.replace(editor.selection, key);
        }
    });
}
function registerInsertCitationCommand(ctx) {
    ctx.subscriptions.push(vscode.commands.registerCommand("humanizer.insertCitation", runInsertCitation));
}
//# sourceMappingURL=insertCitation.js.map