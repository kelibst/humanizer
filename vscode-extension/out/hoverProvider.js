"use strict";
/**
 * hoverProvider.ts — explanatory hover for Humanizer diagnostics.
 *
 * Pulls the diagnostic at the hovered position from the shared
 * `humanizer` collection and renders a `MarkdownString` with:
 *  - the human-readable message (which lint rule triggered),
 *  - the lint code (e.g. `llm-vocab`) so the user can suppress / search,
 *  - up to 3 academic alternatives (when present in the LintSpan).
 *
 * Hover content is non-interactive (`isTrusted = false`) — Quick-Fix is the
 * action surface; this is just an explainer.
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
exports.registerHoverProvider = registerHoverProvider;
const vscode = __importStar(require("vscode"));
const diagnostics_1 = require("./diagnostics");
const MAX_ALTERNATIVES = 3;
function _humanCode(code) {
    switch (code) {
        case "llm-vocab":
            return "AI-flavoured vocabulary";
        case "long-sentence":
            return "Sentence too long for profile target";
        case "topic-perfection":
            return "Textbook-clean topic sentence (AI tic)";
        case "list-overuse":
            return "Three-item list (AI rule of three)";
        case "missing-citation":
            return "Quantitative claim without citation";
        case "orphan-citation":
            return "Citation has no entry in references.json";
        default:
            return code;
    }
}
function _renderHover(document, diagnostics) {
    if (diagnostics.length === 0) {
        return undefined;
    }
    // Stable-sort: most specific first (warning before info).
    const sorted = diagnostics.slice().sort((a, b) => a.severity - b.severity);
    const md = new vscode.MarkdownString();
    md.isTrusted = false;
    md.supportHtml = false;
    for (let i = 0; i < sorted.length; i += 1) {
        if (i > 0) {
            md.appendMarkdown("\n\n---\n\n");
        }
        const diag = sorted[i];
        const codeStr = diag.code ?? "humanizer";
        md.appendMarkdown(`**Humanizer — ${_humanCode(codeStr)}**`);
        md.appendMarkdown(`\n\n${diag.message}`);
        const span = (0, diagnostics_1.spanForDiagnostic)(document, diag);
        if (span && span.suggestions.length > 0) {
            const alts = span.suggestions.slice(0, MAX_ALTERNATIVES);
            md.appendMarkdown("\n\n**Try:** ");
            md.appendMarkdown(alts.map((a) => `\`${a}\``).join(", "));
        }
        md.appendMarkdown(`\n\n_Code: \`${codeStr}\`_`);
    }
    return new vscode.Hover(md);
}
class HumanizerHoverProvider {
    provideHover(document, position) {
        const collection = (0, diagnostics_1.getCollection)();
        if (!collection) {
            return undefined;
        }
        const all = collection.get(document.uri);
        if (!all || all.length === 0) {
            return undefined;
        }
        const here = all.filter((d) => d.range.contains(position));
        return _renderHover(document, here);
    }
}
function registerHoverProvider(ctx) {
    const provider = vscode.languages.registerHoverProvider({ language: "markdown" }, new HumanizerHoverProvider());
    ctx.subscriptions.push(provider);
    return provider;
}
//# sourceMappingURL=hoverProvider.js.map