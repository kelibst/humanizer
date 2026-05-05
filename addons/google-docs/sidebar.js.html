/* Humanizer sidebar — in-browser logic.
 *
 * IMPORTANT: this code runs in the *browser* (the iframe Apps Script renders
 * for the sidebar), not on Google's servers. That's why we use `fetch()` —
 * `UrlFetchApp` runs server-side and cannot reach https://localhost:9999.
 *
 * Server-side glue exposed via google.script.run:
 *   getConfig()      -> { baseUrl, token, profile, backend, model }
 *   setConfig(obj)   -> { ...same shape... }
 *   getSelection()   -> { text, wholeDoc }
 *   replaceSelection(newText) -> { ok, replaced }
 *   showSettings()   (open the modeless dialog)
 */

(function () {
  'use strict';

  // Local state -------------------------------------------------------------
  var state = {
    config: null,
    busy: false,
    suggestions: null,
    chosenSuggestion: -1
  };

  // DOM helpers -------------------------------------------------------------
  function $(id) { return document.getElementById(id); }

  function setStatus(kind, text) {
    var el = $('hz-status');
    el.classList.remove('hz-status--idle', 'hz-status--ok', 'hz-status--warn',
                        'hz-status--err', 'hz-status--busy');
    el.classList.add('hz-status--' + kind);
    $('hz-status-text').textContent = text;
  }

  function log(message, level) {
    var div = document.createElement('div');
    div.className = 'hz-log-entry';
    if (level) div.classList.add('hz-log-entry--' + level);
    var ts = new Date().toLocaleTimeString();
    div.textContent = '[' + ts + '] ' + message;
    var pane = $('hz-log');
    pane.appendChild(div);
    pane.scrollTop = pane.scrollHeight;
  }

  function setBusy(flag) {
    state.busy = flag;
    var disabled = flag || !state.config || !state.config.token || !state.config.baseUrl;
    $('hz-score-btn').disabled    = disabled;
    $('hz-rewrite-btn').disabled  = disabled;
    $('hz-suggest-btn').disabled  = disabled;
  }

  function classifyBand(score) {
    if (score < 0.34) return 'low';
    if (score < 0.67) return 'med';
    return 'high';
  }

  // google.script.run as a Promise ------------------------------------------
  function gsRun(name) {
    var args = Array.prototype.slice.call(arguments, 1);
    return new Promise(function (resolve, reject) {
      var runner = google.script.run
        .withSuccessHandler(resolve)
        .withFailureHandler(function (err) {
          reject(err && err.message ? new Error(err.message) : err);
        });
      runner[name].apply(runner, args);
    });
  }

  // HTTP -----------------------------------------------------------------
  function bridgeFetch(path, init) {
    if (!state.config) return Promise.reject(new Error('config not loaded'));
    if (!state.config.baseUrl) return Promise.reject(new Error('Set the bridge URL in Settings.'));
    if (!state.config.token)   return Promise.reject(new Error('Set the bearer token in Settings.'));
    init = init || {};
    init.mode = 'cors';
    init.headers = Object.assign({
      'Authorization': 'Bearer ' + state.config.token,
      'Content-Type':  'application/json'
    }, init.headers || {});
    var url = state.config.baseUrl.replace(/\/+$/, '') + path;
    return fetch(url, init).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (body) {
          var detail = body;
          try { detail = JSON.parse(body).detail || body; } catch (_) {}
          var err = new Error('HTTP ' + r.status + ': ' + detail);
          err.status = r.status;
          throw err;
        });
      }
      return r.json();
    });
  }

  // Render: score gauge -----------------------------------------------------
  function renderScore(report) {
    $('hz-score-panel').classList.remove('hz-hidden');
    var score = Number(report.score) || 0;
    var pct = Math.round(score * 100);
    $('hz-gauge-fill').style.width = pct + '%';
    $('hz-gauge-value').textContent = score.toFixed(3);

    var band = classifyBand(score);
    var bandEl = $('hz-gauge-band');
    bandEl.textContent = band.toUpperCase();
    bandEl.className = 'hz-band hz-band--' + band;

    var list = $('hz-why-list');
    list.innerHTML = '';
    var components = (report.components || []).slice();
    components.sort(function (a, b) {
      return (b.value * b.weight) - (a.value * a.weight);
    });
    components.slice(0, 3).forEach(function (c) {
      var li = document.createElement('li');
      var name = document.createElement('div');
      name.className = 'hz-why-name';
      name.textContent = c.name + ' — ' + Number(c.value || 0).toFixed(2)
                       + ' × ' + Number(c.weight || 0).toFixed(2);
      var detail = document.createElement('div');
      detail.className = 'hz-why-detail';
      detail.textContent = c.detail || '';
      li.appendChild(name);
      li.appendChild(detail);
      list.appendChild(li);
    });
  }

  // Render: suggestions -----------------------------------------------------
  function renderSuggestions(payload) {
    state.suggestions = payload.candidates || [];
    state.chosenSuggestion = -1;
    var panel = $('hz-suggest-panel');
    panel.classList.remove('hz-hidden');
    var list = $('hz-suggest-list');
    list.innerHTML = '';

    state.suggestions.forEach(function (cand, idx) {
      var card = document.createElement('div');
      card.className = 'hz-suggest-card';
      card.dataset.idx = String(idx);

      var head = document.createElement('div');
      head.className = 'hz-suggest-head';
      var label = document.createElement('span');
      label.textContent = 'Candidate ' + (idx + 1) + '  (seed ' + cand.seed + ')';
      var score = document.createElement('span');
      var band = classifyBand(Number(cand.score) || 0);
      score.className = 'hz-band hz-band--' + band;
      score.textContent = Number(cand.score).toFixed(3) + ' ' + band.toUpperCase();
      head.appendChild(label);
      head.appendChild(score);

      var body = document.createElement('div');
      body.className = 'hz-suggest-text';
      body.textContent = cand.text;

      card.appendChild(head);
      card.appendChild(body);
      card.addEventListener('click', function () {
        var prev = list.querySelector('.hz-suggest-card--active');
        if (prev) prev.classList.remove('hz-suggest-card--active');
        card.classList.add('hz-suggest-card--active');
        state.chosenSuggestion = idx;
        $('hz-suggest-apply').disabled = false;
      });
      list.appendChild(card);
    });

    $('hz-suggest-apply').disabled = true;
  }

  // Action: Score -----------------------------------------------------------
  function actionScore() {
    if (state.busy) return;
    setBusy(true);
    setStatus('busy', 'Scoring…');
    log('Score: fetching selection');
    gsRun('getSelection')
      .then(function (sel) {
        if (!sel.text || !sel.text.trim()) {
          throw new Error('Document is empty.');
        }
        if (sel.wholeDoc) log('No selection — scoring whole document.', 'warn');
        return bridgeFetch('/v1/score', {
          method: 'POST',
          body: JSON.stringify({ text: sel.text, profile: state.config.profile || undefined })
        });
      })
      .then(function (report) {
        renderScore(report);
        setStatus('ok', 'Score: ' + Number(report.score).toFixed(3) + ' (' + report.band + ')');
        log('Score = ' + Number(report.score).toFixed(3) + ' (' + report.band + ')', 'ok');
      })
      .catch(function (err) {
        setStatus('err', err.message || 'Score failed');
        log('Score failed: ' + (err.message || err), 'err');
      })
      .then(function () { setBusy(false); });
  }

  // Action: Rewrite ---------------------------------------------------------
  function actionRewrite() {
    if (state.busy) return;
    var includeLLM = $('hz-include-llm').checked;
    var stages = includeLLM
      ? ['prescan', 'llm', 'determ', 'postscan']
      : ['prescan', 'determ', 'postscan'];

    setBusy(true);
    setStatus('busy', includeLLM ? 'Rewriting (with LLM)…' : 'Rewriting…');
    log('Rewrite: stages = ' + stages.join(', '));

    var captured;
    gsRun('getSelection')
      .then(function (sel) {
        if (!sel.text || !sel.text.trim()) throw new Error('Document is empty.');
        captured = sel;
        if (sel.wholeDoc) log('No selection — would replace whole doc; aborting.', 'err');
        if (sel.wholeDoc) throw new Error('Select some text first; refusing to replace the whole doc.');
        var body = {
          text: sel.text,
          profile: state.config.profile || undefined,
          stages: stages
        };
        if (state.config.backend) body.backend = state.config.backend;
        if (state.config.model)   body.model   = state.config.model;
        return bridgeFetch('/v1/transform', {
          method: 'POST',
          body: JSON.stringify(body)
        });
      })
      .then(function (result) {
        return gsRun('replaceSelection', result.output).then(function () { return result; });
      })
      .then(function (result) {
        if (result.post_score) renderScore(result.post_score);
        var post = result.post_score && result.post_score.score;
        var pre  = result.pre_score  && result.pre_score.score;
        var msg = 'Rewrite done in ' + Number(result.elapsed_seconds || 0).toFixed(2) + 's';
        if (pre !== undefined && post !== undefined) {
          msg += ' (' + Number(pre).toFixed(2) + ' → ' + Number(post).toFixed(2) + ')';
        }
        setStatus('ok', msg);
        log(msg, 'ok');
        (result.notes || []).forEach(function (n) { log('note: ' + n, 'warn'); });
      })
      .catch(function (err) {
        // 502 means the LLM stage failed; if we asked for it, suggest the user untick it.
        if (err.status === 502 && includeLLM) {
          setStatus('warn', 'Backend unavailable — uncheck LLM and retry.');
          log('Backend 502: ' + (err.message || err) + ' — try without LLM.', 'warn');
        } else {
          setStatus('err', err.message || 'Rewrite failed');
          log('Rewrite failed: ' + (err.message || err), 'err');
        }
      })
      .then(function () { setBusy(false); });
  }

  // Action: Suggest 3 -------------------------------------------------------
  function actionSuggest() {
    if (state.busy) return;
    setBusy(true);
    setStatus('busy', 'Generating 3 suggestions…');
    log('Suggest: n=3');

    gsRun('getSelection')
      .then(function (sel) {
        if (!sel.text || !sel.text.trim()) throw new Error('Document is empty.');
        if (sel.wholeDoc) log('No selection — using whole document for suggestions.', 'warn');
        var body = {
          text: sel.text,
          profile: state.config.profile || undefined,
          n: 3
        };
        if (state.config.backend) body.backend = state.config.backend;
        if (state.config.model)   body.model   = state.config.model;
        return bridgeFetch('/v1/suggest', {
          method: 'POST',
          body: JSON.stringify(body)
        });
      })
      .then(function (payload) {
        renderSuggestions(payload);
        setStatus('ok', 'Got ' + (payload.candidates || []).length + ' candidates');
        log('Suggest: ' + (payload.candidates || []).length + ' candidates rendered', 'ok');
      })
      .catch(function (err) {
        setStatus('err', err.message || 'Suggest failed');
        log('Suggest failed: ' + (err.message || err), 'err');
      })
      .then(function () { setBusy(false); });
  }

  // Action: Apply chosen suggestion ----------------------------------------
  function actionApplySuggestion() {
    if (state.chosenSuggestion < 0 || !state.suggestions) return;
    var cand = state.suggestions[state.chosenSuggestion];
    if (!cand) return;
    setBusy(true);
    setStatus('busy', 'Applying candidate ' + (state.chosenSuggestion + 1) + '…');
    gsRun('replaceSelection', cand.text)
      .then(function () {
        setStatus('ok', 'Applied candidate ' + (state.chosenSuggestion + 1));
        log('Applied candidate ' + (state.chosenSuggestion + 1)
          + ' (score ' + Number(cand.score).toFixed(3) + ')', 'ok');
      })
      .catch(function (err) {
        setStatus('err', err.message || 'Apply failed');
        log('Apply failed: ' + (err.message || err), 'err');
      })
      .then(function () { setBusy(false); });
  }

  // Health probe + initial config load -------------------------------------
  function probeHealth() {
    setStatus('busy', 'Pinging daemon…');
    bridgeFetch('/v1/health', { method: 'GET' })
      .then(function (h) {
        var configured = (h.backends_configured || []).join(', ') || 'none';
        setStatus('ok', 'Daemon v' + (h.version || '?') + ' — ' + configured);
        log('Daemon up. Backends configured: ' + configured, 'ok');
        setBusy(false);
      })
      .catch(function (err) {
        if (err.status === 401) {
          setStatus('err', 'Bad token — open Settings.');
          log('401 from /v1/health — token rejected.', 'err');
        } else {
          setStatus('warn', 'Daemon unreachable — start `humanize serve` and trust the cert.');
          log('Health failed: ' + (err.message || err) + '. Run `humanize serve` and visit '
            + (state.config && state.config.baseUrl ? state.config.baseUrl + '/v1/health' : 'the bridge URL')
            + ' once to accept the self-signed cert.', 'warn');
        }
        setBusy(false);
      });
  }

  function init() {
    $('hz-settings-btn').addEventListener('click', function () {
      gsRun('showSettings').then(function () {
        // After the dialog closes, reload config and re-probe.
        loadConfig();
      });
    });
    $('hz-score-btn').addEventListener('click', actionScore);
    $('hz-rewrite-btn').addEventListener('click', actionRewrite);
    $('hz-suggest-btn').addEventListener('click', actionSuggest);
    $('hz-suggest-apply').addEventListener('click', actionApplySuggestion);

    loadConfig();
  }

  function loadConfig() {
    setStatus('busy', 'Loading config…');
    gsRun('getConfig')
      .then(function (cfg) {
        state.config = cfg;
        if (!cfg.baseUrl || !cfg.token) {
          setStatus('warn', 'Open Settings (cog) to set base URL and token.');
          log('Config incomplete — opening Settings is required.', 'warn');
          setBusy(false);
          return;
        }
        probeHealth();
      })
      .catch(function (err) {
        setStatus('err', 'Config load failed.');
        log('getConfig failed: ' + (err.message || err), 'err');
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
