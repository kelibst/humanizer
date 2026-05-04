/* Humanizer settings dialog — in-browser logic.
 *
 * Reads / writes via google.script.run -> Code.gs (PropertiesService).
 * Pulls the profile list from the bridge daemon directly via fetch() once
 * the user has provided a base URL + token.
 */

(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }

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

  function toast(level, message) {
    var el = $('hz-toast');
    el.className = 'hz-toast hz-toast--' + level;
    el.textContent = message;
    el.classList.remove('hz-hidden');
  }

  function clearToast() {
    var el = $('hz-toast');
    el.classList.add('hz-hidden');
    el.textContent = '';
  }

  // Pull the profile list via in-browser fetch (same reason as sidebar.js).
  function fetchProfiles(baseUrl, token) {
    if (!baseUrl || !token) return Promise.reject(new Error('missing'));
    return fetch(baseUrl.replace(/\/+$/, '') + '/v1/profiles', {
      method: 'GET',
      mode: 'cors',
      headers: { 'Authorization': 'Bearer ' + token }
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function populateProfiles(currentSelection) {
    var sel = $('hz-profile');
    var baseUrl = $('hz-baseUrl').value.trim();
    var token   = $('hz-token').value.trim();
    if (!baseUrl || !token) {
      sel.innerHTML = '<option value="default_ghanaian">default_ghanaian (set URL + token to load list)</option>';
      sel.value = currentSelection || 'default_ghanaian';
      return;
    }
    fetchProfiles(baseUrl, token)
      .then(function (data) {
        var profiles = (data.profiles || []);
        if (profiles.length === 0) {
          sel.innerHTML = '<option value="default_ghanaian">default_ghanaian</option>';
          sel.value = 'default_ghanaian';
          return;
        }
        sel.innerHTML = '';
        profiles.forEach(function (p) {
          var opt = document.createElement('option');
          opt.value = p.name;
          opt.textContent = p.name + (p.is_bundled ? ' (bundled)' : '');
          sel.appendChild(opt);
        });
        sel.value = currentSelection && profiles.some(function (p) { return p.name === currentSelection; })
          ? currentSelection
          : profiles[0].name;
        toast('ok', 'Loaded ' + profiles.length + ' profile(s) from daemon.');
      })
      .catch(function (err) {
        sel.innerHTML = '<option value="default_ghanaian">default_ghanaian (daemon unreachable)</option>';
        sel.value = currentSelection || 'default_ghanaian';
        toast('warn', 'Could not load profiles: ' + (err.message || err));
      });
  }

  function loadConfig() {
    return gsRun('getConfig').then(function (cfg) {
      $('hz-baseUrl').value = cfg.baseUrl || '';
      $('hz-token').value   = cfg.token   || '';
      $('hz-backend').value = cfg.backend || 'ollama';
      $('hz-model').value   = cfg.model   || '';
      populateProfiles(cfg.profile || 'default_ghanaian');
    }).catch(function (err) {
      toast('err', 'Failed to read config: ' + (err.message || err));
    });
  }

  function saveConfig(e) {
    if (e && e.preventDefault) e.preventDefault();
    clearToast();
    var data = {
      baseUrl: $('hz-baseUrl').value.trim(),
      token:   $('hz-token').value.trim(),
      profile: $('hz-profile').value,
      backend: $('hz-backend').value,
      model:   $('hz-model').value.trim()
    };
    $('hz-save-btn').disabled = true;
    gsRun('setConfig', data)
      .then(function () {
        toast('ok', 'Saved. Close this dialog and click any sidebar action.');
        setTimeout(function () { google.script.host.close(); }, 700);
      })
      .catch(function (err) {
        $('hz-save-btn').disabled = false;
        toast('err', 'Save failed: ' + (err.message || err));
      });
  }

  function init() {
    $('hz-settings-form').addEventListener('submit', saveConfig);
    $('hz-cancel-btn').addEventListener('click', function () {
      google.script.host.close();
    });

    // Refresh the profile dropdown when the user finishes editing URL or
    // token (blur is enough — no need to spam fetches on every keystroke).
    $('hz-baseUrl').addEventListener('blur', function () { populateProfiles($('hz-profile').value); });
    $('hz-token').addEventListener('blur',   function () { populateProfiles($('hz-profile').value); });

    loadConfig();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
