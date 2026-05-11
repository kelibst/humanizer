"use strict";
/**
 * daemonClient.ts — barrel re-export. Do not add logic here.
 *
 * All implementation lives in ./daemon/. This file exists so every existing
 * caller (extension.ts, sectionProcessor.ts, research/index.ts, etc.) compiles
 * without any import-path changes.
 *
 * Agent B depends on these exact exports. Do NOT change signatures without
 * updating plan/VS_CODE_EXTENSION_CONTRACT.md §1.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.benchmark = exports.reviewImport = exports.transformTextStream = exports.batchStubOrphans = exports.exportBibtex = exports.importBibtex = exports.doiLookup = exports.llmRun = exports.reviewer = exports.inspect = exports.renderPrompt = exports.listTemplates = exports.deleteRef = exports.upsertRef = exports.listRefs = exports.citations = exports.readability = exports.checklist = exports.lintText = exports.listProfiles = exports.suggestText = exports.transformText = exports.scoreText = exports.exportPdfToFile = exports.exportDocxToFile = exports.healthCheck = exports.DaemonError = void 0;
var types_1 = require("./daemon/types");
Object.defineProperty(exports, "DaemonError", { enumerable: true, get: function () { return types_1.DaemonError; } });
var core_1 = require("./daemon/core");
Object.defineProperty(exports, "healthCheck", { enumerable: true, get: function () { return core_1.healthCheck; } });
Object.defineProperty(exports, "exportDocxToFile", { enumerable: true, get: function () { return core_1.exportDocxToFile; } });
Object.defineProperty(exports, "exportPdfToFile", { enumerable: true, get: function () { return core_1.exportPdfToFile; } });
Object.defineProperty(exports, "scoreText", { enumerable: true, get: function () { return core_1.scoreText; } });
Object.defineProperty(exports, "transformText", { enumerable: true, get: function () { return core_1.transformText; } });
Object.defineProperty(exports, "suggestText", { enumerable: true, get: function () { return core_1.suggestText; } });
Object.defineProperty(exports, "listProfiles", { enumerable: true, get: function () { return core_1.listProfiles; } });
var research_1 = require("./daemon/research");
Object.defineProperty(exports, "lintText", { enumerable: true, get: function () { return research_1.lintText; } });
Object.defineProperty(exports, "checklist", { enumerable: true, get: function () { return research_1.checklist; } });
Object.defineProperty(exports, "readability", { enumerable: true, get: function () { return research_1.readability; } });
Object.defineProperty(exports, "citations", { enumerable: true, get: function () { return research_1.citations; } });
var refs_1 = require("./daemon/refs");
Object.defineProperty(exports, "listRefs", { enumerable: true, get: function () { return refs_1.listRefs; } });
Object.defineProperty(exports, "upsertRef", { enumerable: true, get: function () { return refs_1.upsertRef; } });
Object.defineProperty(exports, "deleteRef", { enumerable: true, get: function () { return refs_1.deleteRef; } });
var prompts_1 = require("./daemon/prompts");
Object.defineProperty(exports, "listTemplates", { enumerable: true, get: function () { return prompts_1.listTemplates; } });
Object.defineProperty(exports, "renderPrompt", { enumerable: true, get: function () { return prompts_1.renderPrompt; } });
Object.defineProperty(exports, "inspect", { enumerable: true, get: function () { return prompts_1.inspect; } });
Object.defineProperty(exports, "reviewer", { enumerable: true, get: function () { return prompts_1.reviewer; } });
Object.defineProperty(exports, "llmRun", { enumerable: true, get: function () { return prompts_1.llmRun; } });
var citations_1 = require("./daemon/citations");
Object.defineProperty(exports, "doiLookup", { enumerable: true, get: function () { return citations_1.doiLookup; } });
Object.defineProperty(exports, "importBibtex", { enumerable: true, get: function () { return citations_1.importBibtex; } });
Object.defineProperty(exports, "exportBibtex", { enumerable: true, get: function () { return citations_1.exportBibtex; } });
Object.defineProperty(exports, "batchStubOrphans", { enumerable: true, get: function () { return citations_1.batchStubOrphans; } });
var streaming_1 = require("./daemon/streaming");
Object.defineProperty(exports, "transformTextStream", { enumerable: true, get: function () { return streaming_1.transformTextStream; } });
var review_1 = require("./daemon/review");
Object.defineProperty(exports, "reviewImport", { enumerable: true, get: function () { return review_1.reviewImport; } });
Object.defineProperty(exports, "benchmark", { enumerable: true, get: function () { return review_1.benchmark; } });
//# sourceMappingURL=daemonClient.js.map