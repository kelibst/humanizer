/**
 * refsPanel.ts — sidebar Reference Library panel handler (v1.5).
 *
 * Messages (incoming from the webview):
 *   { type: "refs.list" }                          — list all workspace refs
 *   { type: "refs.delete", id: string }            — delete a reference
 *   { type: "refs.copyCitationKey", id: string }   — copy key to clipboard (done inside extension)
 *   { type: "refs.openDoi", doi: string }           — open DOI in browser
 *   { type: "refs.importBibtex" }                   — open file picker and import
 *   { type: "refs.exportBibtex" }                   — export and save to disk
 *
 * Messages (outgoing):
 *   { type: "refs.data", refs: Reference[] }
 *   { type: "refs.error", message: string }
 *   { type: "refs.importDone", imported, skipped }
 *   { type: "refs.exportDone", path }
 */

import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import {
  listRefs,
  deleteRef,
  importBibtex,
  exportBibtex,
  DaemonError,
} from "../daemonClient";
import { citationKey } from "./insertCitation";

function _workspaceRoot(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
}

function _activeDocPath(): string | undefined {
  const editor = vscode.window.activeTextEditor;
  if (editor && editor.document.languageId === "markdown") {
    return editor.document.uri.fsPath;
  }
  return undefined;
}

function _errMsg(err: unknown): string {
  return err instanceof DaemonError
    ? err.message
    : err instanceof Error
    ? err.message
    : String(err);
}

// ---------------------------------------------------------------------------
// Individual handlers
// ---------------------------------------------------------------------------

async function _handleList(webview: vscode.Webview): Promise<void> {
  const root = _workspaceRoot();
  if (!root) {
    webview.postMessage({
      type: "refs.error",
      message: "Open a workspace folder to load references.",
    });
    return;
  }
  try {
    const refs = await listRefs(root);
    webview.postMessage({ type: "refs.data", refs });
  } catch (err: unknown) {
    webview.postMessage({ type: "refs.error", message: _errMsg(err) });
  }
}

async function _handleDelete(
  id: string,
  webview: vscode.Webview
): Promise<void> {
  const root = _workspaceRoot();
  if (!root || !id) {
    return;
  }
  try {
    await deleteRef(root, id, _activeDocPath());
    // Re-list after deletion.
    const refs = await listRefs(root);
    webview.postMessage({ type: "refs.data", refs });
    vscode.window.setStatusBarMessage(`Humanizer: deleted reference ${id}`, 4000);
  } catch (err: unknown) {
    webview.postMessage({ type: "refs.error", message: _errMsg(err) });
  }
}

async function _handleCopyCitationKey(id: string): Promise<void> {
  const root = _workspaceRoot();
  if (!root || !id) {
    return;
  }
  try {
    const refs = await listRefs(root);
    const ref = refs.find((r) => r.id === id);
    if (!ref) {
      vscode.window.showWarningMessage(`Humanizer: reference "${id}" not found.`);
      return;
    }
    const key = citationKey(ref);
    await vscode.env.clipboard.writeText(key);
    vscode.window.setStatusBarMessage(`Humanizer: copied "${key}" to clipboard`, 3000);
  } catch (err: unknown) {
    vscode.window.showErrorMessage(`Humanizer: ${_errMsg(err)}`);
  }
}

function _handleOpenDoi(doi: string): void {
  if (!doi) {
    return;
  }
  const url = vscode.Uri.parse(`https://doi.org/${doi}`);
  // openExternal returns Thenable<boolean> — use then/catch not promise .catch
  vscode.env.openExternal(url).then(
    (_ok: boolean) => { /* success — no-op */ },
    (err: unknown) => {
      vscode.window.showErrorMessage(`Humanizer: could not open DOI — ${_errMsg(err)}`);
    }
  );
}

async function _handleImportBibtex(webview: vscode.Webview): Promise<void> {
  const root = _workspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage(
      "Open a workspace folder to import BibTeX references."
    );
    return;
  }

  // Open file picker filtered to .bib files.
  const uris = await vscode.window.showOpenDialog({
    canSelectMany: false,
    canSelectFiles: true,
    canSelectFolders: false,
    filters: { "BibTeX files": ["bib"] },
    title: "Import BibTeX",
  });
  if (!uris || uris.length === 0) {
    return;
  }

  let bibtexContent: string;
  try {
    bibtexContent = fs.readFileSync(uris[0].fsPath, "utf8");
  } catch (err: unknown) {
    vscode.window.showErrorMessage(
      `Humanizer: could not read file — ${_errMsg(err)}`
    );
    return;
  }

  const documentPath = _activeDocPath();
  try {
    const result = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Humanizer: importing BibTeX…",
        cancellable: false,
      },
      () => importBibtex(bibtexContent, root, documentPath)
    );
    webview.postMessage({
      type: "refs.importDone",
      imported: result.imported,
      skipped: result.skipped,
    });
  } catch (err: unknown) {
    vscode.window.showErrorMessage(`Humanizer: BibTeX import failed — ${_errMsg(err)}`);
    webview.postMessage({ type: "refs.error", message: _errMsg(err) });
  }
}

async function _handleExportBibtex(webview: vscode.Webview): Promise<void> {
  const root = _workspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage(
      "Open a workspace folder to export BibTeX references."
    );
    return;
  }

  let bibtexText: string;
  try {
    bibtexText = await exportBibtex(root);
  } catch (err: unknown) {
    vscode.window.showErrorMessage(
      `Humanizer: BibTeX export failed — ${_errMsg(err)}`
    );
    webview.postMessage({ type: "refs.error", message: _errMsg(err) });
    return;
  }

  // Ask where to save the file.
  const saveUri = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.join(root, "references.bib")),
    filters: { "BibTeX files": ["bib"] },
    title: "Export BibTeX",
  });
  if (!saveUri) {
    return;
  }

  try {
    fs.writeFileSync(saveUri.fsPath, bibtexText, "utf8");
    webview.postMessage({ type: "refs.exportDone", path: saveUri.fsPath });
    vscode.window.showInformationMessage(
      `Humanizer: exported ${saveUri.fsPath}`
    );
  } catch (err: unknown) {
    vscode.window.showErrorMessage(
      `Humanizer: could not write file — ${_errMsg(err)}`
    );
  }
}

// ---------------------------------------------------------------------------
// Message router
// ---------------------------------------------------------------------------

export async function handleRefsMessage(
  msg: Record<string, unknown>,
  webview: vscode.Webview
): Promise<void> {
  switch (msg.type) {
    case "refs.list":
      await _handleList(webview);
      break;
    case "refs.delete":
      if (typeof msg.id === "string" && msg.id) {
        await _handleDelete(msg.id, webview);
      }
      break;
    case "refs.copyCitationKey":
      if (typeof msg.id === "string" && msg.id) {
        await _handleCopyCitationKey(msg.id);
      }
      break;
    case "refs.openDoi":
      if (typeof msg.doi === "string" && msg.doi) {
        _handleOpenDoi(msg.doi);
      }
      break;
    case "refs.importBibtex":
      await _handleImportBibtex(webview);
      break;
    case "refs.exportBibtex":
      await _handleExportBibtex(webview);
      break;
    default:
      break;
  }
}
