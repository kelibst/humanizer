/**
 * studyStarter.ts — handles the Study Starter sidebar form.
 *
 * Webview message protocol:
 *   incoming { type: "studyStarter:run", topic, discipline, gap?, audience?, methods? }
 *   outgoing { type: "studyStarter:result", prompt, charCount }
 *            { type: "studyStarter:error",  message }
 */

import * as vscode from "vscode";
import { renderPrompt, DaemonError } from "../../daemonClient";

export async function handleStudyStarter(
  msg: Record<string, unknown>,
  webview: vscode.Webview
): Promise<void> {
  const topic = String(msg.topic ?? "").trim();
  const discipline = String(msg.discipline ?? "").trim();

  if (!topic || !discipline) {
    webview.postMessage({
      type: "studyStarter:error",
      message: "Topic and discipline are required.",
    });
    return;
  }

  const context: Record<string, string> = {
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
    const result = await renderPrompt("study_starter", context);
    webview.postMessage({
      type: "studyStarter:result",
      prompt: result.prompt,
      charCount: result.charCount,
    });
  } catch (err: unknown) {
    webview.postMessage({
      type: "studyStarter:error",
      message: _friendlyError(err),
    });
  }
}

function _friendlyError(err: unknown): string {
  if (err instanceof DaemonError) {
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
