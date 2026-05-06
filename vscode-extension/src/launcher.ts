/**
 * launcher.ts — `humanizer.actions` Quick-Pick launcher.
 *
 * Lists every Humanizer command discovered via ``vscode.commands.getCommands(true)``
 * filtered by `^humanizer\.`. Each item shows a static description from
 * COMMAND_DESCRIPTIONS. Recent-use sort lives in
 * ``workspaceState["humanizer.recentActions"]`` (LRU, cap 6).
 *
 * No new npm deps; pure VS Code API. Type-to-filter is handled by VS Code's
 * QuickPick for free.
 */

import * as vscode from "vscode";

const RECENT_KEY = "humanizer.recentActions";
const RECENT_CAP = 6;

/**
 * Static description map. New commands added in v1.4 are listed first; the
 * Quick-Pick falls back to a generic "Humanizer command" label if a command
 * id is unknown. Keep entries terse — they show as `description` next to the
 * label in the Quick-Pick.
 */
const COMMAND_DESCRIPTIONS: Record<string, { label: string; detail: string }> = {
  "humanizer.startDaemon": {
    label: "Start Humanizer Daemon",
    detail: "Launch `humanize serve` in an integrated terminal.",
  },
  "humanizer.scoreFile": {
    label: "Score File",
    detail: "Compute the AI-risk score for the active markdown file.",
  },
  "humanizer.transformSelection": {
    label: "Rewrite Selection",
    detail: "Run the humanizer pipeline over the current selection.",
  },
  "humanizer.suggestSelection": {
    label: "Suggest 3 for Selection",
    detail: "Get three candidate rewrites for the selected text.",
  },
  "humanizer.openSettings": {
    label: "Open Humanizer Settings",
    detail: "Jump to the humanizer.* configuration block.",
  },
  "humanizer.scoreSection": {
    label: "Score Section",
    detail: "Score the section at the cursor only.",
  },
  "humanizer.transformSection": {
    label: "Rewrite Section",
    detail: "Rewrite the section at the cursor only.",
  },
  "humanizer.transformAll": {
    label: "Rewrite All Sections",
    detail: "Iterate every section in the document.",
  },
  "humanizer.exportDocx": {
    label: "Export to .docx",
    detail: "Generate <stem>_humanized.docx next to the current file.",
  },
  "humanizer.showProgress": {
    label: "Show Section Progress",
    detail: "Reveal the Humanizer activity-bar container.",
  },
  "humanizer.insertCitation": {
    label: "Insert Citation",
    detail: "Pick a workspace reference and insert at cursor.",
  },
  "humanizer.openOutline": {
    label: "Open Outline Panel",
    detail: "Focus the sidebar and reveal the outline.",
  },
  "humanizer.openDashboard": {
    label: "Open Research Dashboard",
    detail: "Sparkline + word bars + completeness rings.",
  },
  "humanizer.actions": {
    label: "Humanizer Actions…",
    detail: "Quick-Pick of every Humanizer command.",
  },
  "humanizer.openWelcome": {
    label: "Show Welcome",
    detail: "Re-open the first-launch onboarding cards.",
  },
};

/**
 * Internal commands that should never surface in the launcher even if
 * ``getCommands`` reports them. Anything starting with ``humanizer._`` is
 * automatically excluded; explicit names below catch any future additions.
 */
const HIDDEN_COMMANDS = new Set<string>([]);

/**
 * Register the ``humanizer.actions`` Quick-Pick.
 */
export function registerLauncher(ctx: vscode.ExtensionContext): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("humanizer.actions", async () => {
      await _showLauncher(ctx);
    })
  );
}

async function _showLauncher(ctx: vscode.ExtensionContext): Promise<void> {
  const allCommands = await vscode.commands.getCommands(true);
  const matched = allCommands
    .filter((id) => /^humanizer\./.test(id))
    .filter((id) => !id.startsWith("humanizer._"))
    .filter((id) => !HIDDEN_COMMANDS.has(id));

  if (matched.length === 0) {
    vscode.window.showInformationMessage(
      "Humanizer: no commands registered yet. Try reloading the window."
    );
    return;
  }

  const recent = ctx.workspaceState.get<string[]>(RECENT_KEY, []);
  const ordered = _orderByRecency(matched, recent);

  const items: (vscode.QuickPickItem & { commandId: string })[] = ordered.map(
    (id) => {
      const desc = COMMAND_DESCRIPTIONS[id];
      const isRecent = recent.includes(id);
      return {
        commandId: id,
        label: desc?.label ?? _humanizeCommandId(id),
        description: isRecent ? "$(history) recent" : id,
        detail: desc?.detail ?? "Humanizer command",
      };
    }
  );

  const pick = await vscode.window.showQuickPick(items, {
    placeHolder: "Humanizer actions — type to filter",
    matchOnDescription: true,
    matchOnDetail: true,
  });
  if (!pick) {
    return;
  }

  // LRU update.
  await _bumpRecent(ctx, pick.commandId);

  try {
    await vscode.commands.executeCommand(pick.commandId);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    vscode.window.showErrorMessage(
      `Humanizer: command '${pick.commandId}' failed: ${msg}`
    );
  }
}

function _orderByRecency(commandIds: string[], recent: string[]): string[] {
  const recentSet = new Set(recent);
  const recentIds = recent.filter((id) => commandIds.includes(id));
  const rest = commandIds.filter((id) => !recentSet.has(id));
  rest.sort((a, b) => {
    const la = COMMAND_DESCRIPTIONS[a]?.label ?? a;
    const lb = COMMAND_DESCRIPTIONS[b]?.label ?? b;
    return la.localeCompare(lb);
  });
  return [...recentIds, ...rest];
}

async function _bumpRecent(
  ctx: vscode.ExtensionContext,
  commandId: string
): Promise<void> {
  const current = ctx.workspaceState.get<string[]>(RECENT_KEY, []);
  const next = [commandId, ...current.filter((id) => id !== commandId)].slice(
    0,
    RECENT_CAP
  );
  await ctx.workspaceState.update(RECENT_KEY, next);
}

function _humanizeCommandId(id: string): string {
  // "humanizer.openDashboard" → "Open Dashboard"
  const stem = id.replace(/^humanizer\./, "");
  return stem
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (c) => c.toUpperCase())
    .trim();
}
