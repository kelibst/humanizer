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

import * as vscode from "vscode";
import {
  DaemonError,
  Reference,
  listRefs,
  upsertRef,
} from "../daemonClient";

const NEW_REF_LABEL = "$(plus) New reference…";

interface RefQuickPickItem extends vscode.QuickPickItem {
  ref?: Reference;
  isNew?: boolean;
}

function _workspaceRoot(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    return undefined;
  }
  return folders[0].uri.fsPath;
}

function _lastName(author: string): string {
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

export function citationKey(ref: Reference): string {
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

async function _promptForNewReference(
  workspaceRoot: string,
  documentPath: string | undefined
): Promise<Reference | undefined> {
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
    validateInput: (v) =>
      /^\d{4}$/.test(v.trim()) ? null : "Year must be 4 digits.",
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

  const partial: Partial<Reference> = {
    authors,
    year,
    title: title.trim(),
    type: "journal",
  };
  if (venue && venue.trim()) {
    partial.venue = venue.trim();
  }

  try {
    return await upsertRef(workspaceRoot, partial, documentPath);
  } catch (err: unknown) {
    const msg =
      err instanceof DaemonError
        ? err.message
        : err instanceof Error
        ? err.message
        : String(err);
    vscode.window.showErrorMessage(`Humanizer: ${msg}`);
    return undefined;
  }
}

export async function runInsertCitation(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    vscode.window.showWarningMessage(
      "Open a Markdown file to insert a citation."
    );
    return;
  }
  const root = _workspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage(
      "Open a workspace folder so Humanizer can find references.json."
    );
    return;
  }

  let refs: Reference[];
  try {
    refs = await listRefs(root);
  } catch (err: unknown) {
    const msg =
      err instanceof DaemonError
        ? err.message
        : err instanceof Error
        ? err.message
        : String(err);
    vscode.window.showErrorMessage(`Humanizer: ${msg}`);
    return;
  }

  const items: RefQuickPickItem[] = refs.map((r) => ({
    label: citationKey(r),
    description: r.title,
    detail: r.rawApa,
    ref: r,
  }));
  items.push({ label: NEW_REF_LABEL, isNew: true });

  const pick = await vscode.window.showQuickPick(items, {
    placeHolder:
      refs.length > 0
        ? "Select a reference to cite, or create a new one."
        : "No references yet — pick 'New reference…' to add one.",
    matchOnDescription: true,
    matchOnDetail: true,
  });
  if (!pick) {
    return;
  }

  const documentPath = editor.document.uri.fsPath;
  let ref: Reference | undefined = pick.ref;
  if (pick.isNew) {
    ref = await _promptForNewReference(root, documentPath);
    if (!ref) {
      return;
    }
  } else if (ref) {
    // Re-POST the picked ref with documentPath so the markdown References
    // block regenerates if the markers are missing.
    try {
      ref = await upsertRef(
        root,
        {
          id: ref.id,
          authors: ref.authors,
          year: ref.year,
          title: ref.title,
          venue: ref.venue ?? undefined,
          doi: ref.doi ?? undefined,
          url: ref.url ?? undefined,
          type: ref.type,
          rawApa: ref.rawApa,
        },
        documentPath
      );
    } catch {
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
    } else {
      eb.replace(editor.selection, key);
    }
  });
}

export function registerInsertCitationCommand(
  ctx: vscode.ExtensionContext
): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("humanizer.insertCitation", runInsertCitation)
  );
}
