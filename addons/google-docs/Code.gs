/**
 * Humanizer Google Docs add-in — server-side glue.
 *
 * The actual HTTP work (talking to https://localhost:9999) happens in the
 * sidebar's in-browser fetch() because UrlFetchApp runs on Google's servers
 * and cannot reach loopback. This file only handles:
 *
 *   - Menu wiring (onOpen)
 *   - Sidebar / settings dialog launching
 *   - Reading the user's selection
 *   - Replacing the selection with rewrite output
 *   - Persisting per-user config (baseUrl, token, profile, backend, model)
 *
 * Contract: see plan/BRIDGE_CONTRACT.md (Appendix A — sidebar fetch pattern).
 */

var CONFIG_KEYS = ['baseUrl', 'token', 'profile', 'backend', 'model'];
var DEFAULT_CONFIG = {
  baseUrl: 'https://localhost:9999',
  token: '',
  profile: 'default_ghanaian',
  backend: 'ollama',
  model: ''
};

/**
 * Build the Humanizer menu when the doc is opened.
 *
 * Note: scopes must be authorised once. Run `onOpen` manually from the Apps
 * Script editor on first install (the user is walked through this in the
 * README "Manual test recipe").
 */
function onOpen(e) {
  DocumentApp.getUi()
    .createMenu('Humanizer')
    .addItem('Open sidebar', 'showSidebar')
    .addItem('Settings…', 'showSettings')
    .addToUi();
}

/** Required by add-in lifecycle hooks. */
function onInstall(e) {
  onOpen(e);
}

/** Open the main rewrite/score sidebar. */
function showSidebar() {
  var html = HtmlService.createTemplateFromFile('sidebar')
    .evaluate()
    .setTitle('Humanizer')
    .setWidth(360);
  DocumentApp.getUi().showSidebar(html);
}

/** Open the modeless settings dialog. */
function showSettings() {
  var html = HtmlService.createTemplateFromFile('settings')
    .evaluate()
    .setWidth(420)
    .setHeight(520);
  DocumentApp.getUi().showModelessDialog(html, 'Humanizer settings');
}

/**
 * Helper used by `<?!= include('foo') ?>` style templates to splice one HTML
 * file into another. Apps Script requires this round-trip even for inline
 * <script> / <style> includes.
 */
function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

// ---------------------------------------------------------------------------
// Selection IO
// ---------------------------------------------------------------------------

/**
 * Return the currently selected text plus a flag indicating whether the
 * selection was empty (in which case we returned the whole document).
 *
 * Shape: { text: string, wholeDoc: boolean }
 *
 * The sidebar uses `wholeDoc` to warn the user before a Rewrite would replace
 * the entire document.
 */
function getSelection() {
  var doc = DocumentApp.getActiveDocument();
  var selection = doc.getSelection();
  if (!selection) {
    return { text: doc.getBody().getText(), wholeDoc: true };
  }
  var rangeElements = selection.getRangeElements();
  var parts = [];
  for (var i = 0; i < rangeElements.length; i++) {
    var re = rangeElements[i];
    var el = re.getElement();
    if (el.editAsText) {
      var t = el.editAsText().getText();
      if (re.isPartial()) {
        var s = re.getStartOffset();
        var e = re.getEndOffsetInclusive();
        parts.push(t.substring(s, e + 1));
      } else {
        parts.push(t);
      }
    }
  }
  return { text: parts.join('\n'), wholeDoc: false };
}

/**
 * Replace the current selection with `newText`.
 *
 * Strategy:
 *   - Single range element, partial: splice with deleteText + insertText on
 *     that element's editable text run.
 *   - Single range element, whole: replace the element's text wholesale.
 *   - Multi-element selection: walk every range element, clear partial slices
 *     on the first/last and delete fully-covered middle elements, then
 *     insert `newText` at the start position.
 *
 * Returns { ok: true, replaced: number } where `replaced` is the original
 * length of the spanned text (mostly diagnostic).
 *
 * Open question (logged in STATE.md): the multi-element path leaves any
 * paragraph/list structure of the deleted middle elements collapsed into a
 * single text run on the first paragraph. Acceptable for v1 because Rewrite
 * output is almost always a flat text block; if a user selects a 5-paragraph
 * block and rewrites, they get a flat replacement with `\n` line breaks
 * which Docs renders as soft breaks.
 */
function replaceSelection(newText) {
  var doc = DocumentApp.getActiveDocument();
  var selection = doc.getSelection();
  if (!selection) {
    throw new Error('No selection. Select some text and try again.');
  }
  var rangeElements = selection.getRangeElements();
  if (rangeElements.length === 0) {
    throw new Error('Empty selection.');
  }

  // Single-element fast path.
  if (rangeElements.length === 1) {
    var re = rangeElements[0];
    var el = re.getElement();
    if (!el.editAsText) {
      throw new Error('Cannot replace this kind of selection.');
    }
    var text = el.editAsText();
    var fullLen = text.getText().length;
    if (re.isPartial()) {
      var start = re.getStartOffset();
      var end = re.getEndOffsetInclusive();
      text.deleteText(start, end);
      text.insertText(start, newText);
      return { ok: true, replaced: end - start + 1 };
    }
    text.setText(newText);
    return { ok: true, replaced: fullLen };
  }

  // Multi-element path. Delete from last to first to keep offsets stable
  // on each editable element, then insert at the original start.
  var first = rangeElements[0];
  var firstEl = first.getElement();
  var firstText = firstEl.editAsText ? firstEl.editAsText() : null;
  var firstStart = first.isPartial() ? first.getStartOffset() : 0;

  for (var i = rangeElements.length - 1; i >= 0; i--) {
    var rEl = rangeElements[i];
    var elem = rEl.getElement();
    if (!elem.editAsText) continue;
    var t = elem.editAsText();
    if (rEl.isPartial()) {
      t.deleteText(rEl.getStartOffset(), rEl.getEndOffsetInclusive());
    } else {
      t.setText('');
    }
  }
  if (firstText) {
    firstText.insertText(firstStart, newText);
  }
  return { ok: true, replaced: -1 };
}

// ---------------------------------------------------------------------------
// Per-user config — PropertiesService.getUserProperties()
// ---------------------------------------------------------------------------

/** Return the current config dict, falling back to defaults for missing keys. */
function getConfig() {
  var props = PropertiesService.getUserProperties();
  var out = {};
  for (var i = 0; i < CONFIG_KEYS.length; i++) {
    var key = CONFIG_KEYS[i];
    var v = props.getProperty(key);
    out[key] = (v === null || v === undefined) ? DEFAULT_CONFIG[key] : v;
  }
  return out;
}

/**
 * Write a partial or full config dict. Keys not in CONFIG_KEYS are ignored.
 * Empty strings are written as-is (not deleted) so the user can clear a value.
 */
function setConfig(obj) {
  if (!obj || typeof obj !== 'object') {
    throw new Error('setConfig expects an object');
  }
  var props = PropertiesService.getUserProperties();
  for (var i = 0; i < CONFIG_KEYS.length; i++) {
    var key = CONFIG_KEYS[i];
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      var val = obj[key];
      if (val === null || val === undefined) val = '';
      props.setProperty(key, String(val));
    }
  }
  return getConfig();
}
