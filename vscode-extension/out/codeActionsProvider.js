"use strict";
/**
 * codeActionsProvider.ts — Quick-Fix actions for Humanizer diagnostics.
 *
 * For each `llm-vocab` diagnostic, surfaces one `CodeAction.QuickFix` per
 * profile suggestion that performs a `WorkspaceEdit` replacing the squiggled
 * range with the alternative.
 *
 * For `missing-citation` / `orphan-citation`, surfaces a single action that
 * runs `humanizer.insertCitation` (Agent B's command). If Agent B has not
 * shipped yet, Agent A may register a no-op handler via
 * `registerExternalAction(code, handler)` so other modules can hook in later.
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
exports.registerExternalAction = registerExternalAction;
exports.registerCodeActionsProvider = registerCodeActionsProvider;
const vscode = __importStar(require("vscode"));
const diagnostics_1 = require("./diagnostics");
const _externalHandlers = new Map();
/**
 * Allow other modules (Agent B) to register a custom Quick-Fix handler for a
 * given lint code. Called from `extension.ts` after activation, e.g. to wire
 * `missing-citation` → a Quick-Pick.
 *
 * Round-1 use is opt-in; the default behaviour is to dispatch
 * `humanizer.insertCitation`.
 */
function registerExternalAction(code, handler) {
    _externalHandlers.set(code, handler);
    return new vscode.Disposable(() => {
        if (_externalHandlers.get(code) === handler) {
            _externalHandlers.delete(code);
        }
    });
}
function _vocabFixes(document, diagnostic, span) {
    const out = [];
    const original = document.getText(diagnostic.range);
    for (const suggestion of span.suggestions) {
        const action = new vscode.CodeAction(`Humanizer: replace "${original}" → "${suggestion}"`, vscode.CodeActionKind.QuickFix);
        const edit = new vscode.WorkspaceEdit();
        edit.replace(document.uri, diagnostic.range, _matchCase(original, suggestion));
        action.edit = edit;
        action.diagnostics = [diagnostic];
        action.isPreferred = out.length === 0;
        out.push(action);
    }
    return out;
}
/**
 * Preserve the leading-capital and ALL-CAPS shape of the original token so
 * that "Delve into…" becomes "Examine into…", not "examine into…".
 */
function _matchCase(original, replacement) {
    if (!original) {
        return replacement;
    }
    if (original === original.toUpperCase() && /[A-Z]/.test(original)) {
        return replacement.toUpperCase();
    }
    if (original[0] === original[0].toUpperCase() && /[A-Z]/.test(original[0])) {
        return replacement.charAt(0).toUpperCase() + replacement.slice(1);
    }
    return replacement;
}
function _citationFix(document, diagnostic, span) {
    const code = span.code;
    const action = new vscode.CodeAction(code === "missing-citation"
        ? "Humanizer: insert citation…"
        : "Humanizer: link or add reference…", vscode.CodeActionKind.QuickFix);
    const handler = _externalHandlers.get(code);
    if (handler) {
        // Defer to the externally-registered handler (e.g. Agent B's Quick-Pick).
        action.command = {
            command: "humanizer._dispatchExternalAction",
            title: action.title,
            arguments: [document.uri.toString(), code, diagnostic.range],
        };
    }
    else {
        // Default: dispatch Agent B's `humanizer.insertCitation` command. If Agent B
        // hasn't shipped, the command will be a no-op / "command not found"; that
        // is the documented Round-1 fallback.
        action.command = {
            command: "humanizer.insertCitation",
            title: action.title,
            arguments: [document.uri.toString(), diagnostic.range],
        };
    }
    action.diagnostics = [diagnostic];
    return action;
}
class HumanizerCodeActionsProvider {
    provideCodeActions(document, range, context) {
        const out = [];
        // Index the current spans for this document by exact range so we can
        // recover suggestions / token even if `context.diagnostics` arrives without
        // a matching code (e.g. third-party providers).
        const spans = (0, diagnostics_1.spansFor)(document);
        const spanByKey = new Map();
        for (const s of spans) {
            spanByKey.set(`${s.start}:${s.end}:${s.code}`, s);
        }
        for (const diag of context.diagnostics) {
            if (diag.source !== "humanizer") {
                continue;
            }
            const startOff = document.offsetAt(diag.range.start);
            const endOff = document.offsetAt(diag.range.end);
            const code = diag.code ?? "";
            const span = spanByKey.get(`${startOff}:${endOff}:${code}`);
            if (!span) {
                continue;
            }
            // Ignore diagnostics whose range does not actually overlap the requested
            // range — VS Code already filters most of these, but mouse-over selection
            // can over-broaden the input.
            if (!diag.range.intersection(range)) {
                continue;
            }
            if (span.code === "llm-vocab" && span.suggestions.length > 0) {
                for (const a of _vocabFixes(document, diag, span)) {
                    out.push(a);
                }
            }
            else if (span.code === "missing-citation" ||
                span.code === "orphan-citation") {
                out.push(_citationFix(document, diag, span));
            }
        }
        return out;
    }
}
HumanizerCodeActionsProvider.providedKinds = [vscode.CodeActionKind.QuickFix];
/**
 * Register the code-actions provider for markdown. Also registers an internal
 * dispatch command (`humanizer._dispatchExternalAction`) used by external
 * handlers — the command is private (under-prefixed) and not contributed to
 * the user-visible palette.
 */
function registerCodeActionsProvider(ctx) {
    const provider = vscode.languages.registerCodeActionsProvider({ language: "markdown" }, new HumanizerCodeActionsProvider(), { providedCodeActionKinds: HumanizerCodeActionsProvider.providedKinds });
    ctx.subscriptions.push(provider);
    ctx.subscriptions.push(vscode.commands.registerCommand("humanizer._dispatchExternalAction", async (uriStr, code, range) => {
        const handler = _externalHandlers.get(code);
        if (!handler) {
            return;
        }
        const uri = vscode.Uri.parse(uriStr);
        const doc = await vscode.workspace.openTextDocument(uri);
        await handler(doc, range);
    }));
    return provider;
}
//# sourceMappingURL=codeActionsProvider.js.map