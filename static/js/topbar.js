/* Top bar behaviour: theme toggle and the account menu.
 *
 * The theme's *initial* resolution happens in an inline script in <head>, not
 * here — a deferred file runs after first paint, which is exactly when a
 * dark-theme user would see a white flash. This file only handles changes.
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var STORAGE_KEY = "abc-theme";

  /* ------------------------------------------------------------ theme --- */

  function systemPrefersDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function currentTheme() {
    return root.getAttribute("data-theme") || (systemPrefersDark() ? "dark" : "light");
  }

  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    // The button reports which theme is active, so a screen reader hears the
    // state rather than only the action.
    var describe = function () {
      var theme = currentTheme();
      toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      toggle.title = theme === "dark" ? "Switch to light" : "Switch to dark";
    };

    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (e) {
        /* Private mode: the choice applies now but won't outlive the tab. */
      }
      describe();
    });

    describe();

    // Follow the OS while the user has expressed no preference of their own.
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
        var stored = null;
        try {
          stored = localStorage.getItem(STORAGE_KEY);
        } catch (e) { /* ignore */ }
        if (!stored) describe();
      });
    }
  }

  /* ---------------------------------------------------------- account --- */

  var button = document.getElementById("account-button");
  var menu = document.getElementById("account-menu");
  if (!button || !menu) return;

  function isOpen() {
    return button.getAttribute("aria-expanded") === "true";
  }

  function open() {
    menu.hidden = false;
    button.setAttribute("aria-expanded", "true");
  }

  function close(refocus) {
    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (refocus) button.focus();
  }

  button.addEventListener("click", function (event) {
    event.stopPropagation();
    isOpen() ? close(false) : open();
  });

  // Clicking anywhere else closes it — but not a click inside the menu, or
  // the first item would be unusable once these become real actions.
  document.addEventListener("click", function (event) {
    if (isOpen() && !menu.contains(event.target) && event.target !== button) {
      close(false);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && isOpen()) close(true);
  });

  // Not wired yet. Swallow the click so a disabled item cannot half-fire
  // something later, and say so out loud rather than appearing broken.
  menu.querySelectorAll(".is-inert").forEach(function (item) {
    item.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
    });
  });
})();
