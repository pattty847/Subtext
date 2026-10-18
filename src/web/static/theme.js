/* Apply the preference before styles load to avoid a flash of the wrong theme. */
(function () {
  'use strict';
  var theme = 'dark';
  try { if (localStorage.getItem('subtext-theme') === 'light') theme = 'light'; } catch (_) {}
  function apply(value) {
    document.documentElement.dataset.theme = value;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = value === 'dark' ? '#141916' : '#f4f1e9';
    var button = document.getElementById('theme-toggle-btn');
    if (button) {
      var label = 'Switch to ' + (value === 'dark' ? 'light' : 'dark') + ' theme';
      button.setAttribute('aria-label', label);
      button.title = label;
      button.setAttribute('aria-pressed', String(value === 'light'));
    }
  }
  apply(theme);
  document.addEventListener('DOMContentLoaded', function () {
    apply(theme);
    document.getElementById('theme-toggle-btn').addEventListener('click', function () {
      theme = theme === 'dark' ? 'light' : 'dark';
      apply(theme);
      try { localStorage.setItem('subtext-theme', theme); } catch (_) {}
    });
  });
}());
