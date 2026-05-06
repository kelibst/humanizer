// Humanizer Citation Checker for Google Docs
// Instructions: Paste this file into Extensions → Apps Script in your Google Doc.
// Set Script Properties (Project Settings → Script Properties):
//   HUMANIZER_URL  →  https://localhost:9999
//   HUMANIZER_TOKEN → (your token from ~/.config/humanizer/serve/token)

function checkCitations() {
  var doc = DocumentApp.getActiveDocument();
  var body = doc.getBody();
  var paras = body.getParagraphs();
  var paragraphTexts = paras.map(function(p) { return p.getText(); });

  var url = PropertiesService.getScriptProperties().getProperty('HUMANIZER_URL');
  var token = PropertiesService.getScriptProperties().getProperty('HUMANIZER_TOKEN');

  if (!url || !token) {
    DocumentApp.getUi().alert('Set HUMANIZER_URL and HUMANIZER_TOKEN in Script Properties first.');
    return;
  }

  var payload = JSON.stringify({ paragraphs: paragraphTexts });
  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: { 'Authorization': 'Bearer ' + token },
    payload: payload,
    muteHttpExceptions: true
  };

  var response = UrlFetchApp.fetch(url + '/v1/citations/google-docs', options);
  if (response.getResponseCode() !== 200) {
    DocumentApp.getUi().alert('Daemon error: ' + response.getContentText());
    return;
  }

  var result = JSON.parse(response.getContentText());

  // Highlight orphan citations in red
  result.orphans.forEach(function(orphan) {
    var idx = orphan.paragraph_idx;
    var start = orphan.char_in_paragraph;
    var end = start + (orphan.end - orphan.start);
    if (idx < paras.length) {
      try {
        paras[idx].editAsText().setForegroundColor(start, end - 1, '#CC0000');
      } catch (e) { /* skip if offsets are off */ }
    }
  });

  // Show sidebar with summary
  var html = HtmlService.createHtmlOutput(
    '<b>Citation Check Results</b><br>' +
    'Orphans: ' + result.orphans.length + '<br>' +
    'Missing: ' + result.missing.length + '<br>' +
    'Unused refs: ' + result.unused.length + '<br><br>' +
    '<b>Orphans (red in doc):</b><br>' +
    result.orphans.map(function(o) { return '• ' + o.key + ' (para ' + o.paragraph_idx + ')'; }).join('<br>') + '<br><br>' +
    '<b>Missing citations:</b><br>' +
    result.missing.map(function(m) { return '• "' + m.claim + '" (para ' + m.paragraph_idx + ')'; }).join('<br>')
  ).setTitle('Humanizer Citations');
  DocumentApp.getUi().showSidebar(html);
}

function onOpen() {
  DocumentApp.getUi().createMenu('Humanizer')
    .addItem('Check Citations', 'checkCitations')
    .addToUi();
}
