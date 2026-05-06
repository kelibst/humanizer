"use strict";
/**
 * studyStarter.ts — handles the Study Starter sidebar form.
 *
 * Webview message protocol:
 *   incoming { type: "studyStarter:run", topic, discipline, gap?, audience?, methods? }
 *   outgoing { type: "studyStarter:result", prompt, charCount }
 *            { type: "studyStarter:error",  message }
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.handleStudyStarter = handleStudyStarter;
const daemonClient_1 = require("../../daemonClient");
async function handleStudyStarter(msg, webview) {
    const topic = String(msg.topic ?? "").trim();
    const discipline = String(msg.discipline ?? "").trim();
    if (!topic || !discipline) {
        webview.postMessage({
            type: "studyStarter:error",
            message: "Topic and discipline are required.",
        });
        return;
    }
    const context = {
        topic,
        discipline,
    };
    for (const key of ["gap", "audience", "methods"]) {
        const v = msg[key];
        if (typeof v === "string" && v.trim()) {
            context[key] = v.trim();
        }
    }
    try {
        const result = await (0, daemonClient_1.renderPrompt)("study_starter", context);
        webview.postMessage({
            type: "studyStarter:result",
            prompt: result.prompt,
            charCount: result.charCount,
        });
    }
    catch (err) {
        webview.postMessage({
            type: "studyStarter:error",
            message: _friendlyError(err),
        });
    }
}
function _friendlyError(err) {
    if (err instanceof daemonClient_1.DaemonError) {
        if (err.status === 0) {
            return "Start the Humanizer daemon to use research features.";
        }
        if (err.status === 404) {
            return "Research backend not ready (template route missing). Update the daemon.";
        }
        return err.message;
    }
    if (err instanceof Error) {
        return err.message;
    }
    return String(err);
}
//# sourceMappingURL=studyStarter.js.map