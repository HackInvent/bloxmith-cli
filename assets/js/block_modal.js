/**
 * Role: Mounts the CLI block modal frontend asset.
 * File Name: block_modal.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2026-05-18
 */

(function () {
  "use strict";

  const registry = (window.CWBlockUiBlocks = window.CWBlockUiBlocks || {});

  /**
   * Return the CLI modal tabs in visual order.
   *
   * @param {HTMLElement} root - Mounted CLI modal root.
   * @returns {HTMLElement[]} Tab buttons controlled by this block asset.
   */
  function tabElements(root) {
    return Array.from(root.querySelectorAll("[data-cli-modal-tab]"));
  }

  /**
   * Return the CLI modal panels in visual order.
   *
   * @param {HTMLElement} root - Mounted CLI modal root.
   * @returns {HTMLElement[]} Panels controlled by the tab list.
   */
  function panelElements(root) {
    return Array.from(root.querySelectorAll("[data-cli-modal-panel]"));
  }

  /**
   * Return all per-output command editors from the modal.
   *
   * @param {HTMLElement} root - Mounted CLI modal root.
   * @returns {HTMLElement[]} Command textareas bound to output ports.
   */
  function commandEditors(root) {
    return Array.from(root.querySelectorAll("[data-cli-command-port-id]"));
  }

  /**
   * Refresh the visible command count shown in the modal header.
   *
   * @param {HTMLElement} root - Mounted CLI modal root.
   */
  function updateCommandCount(root) {
    const count = root.querySelector("[data-cli-command-count]");
    if (!count) {
      return;
    }
    const total = commandEditors(root).length;
    count.textContent = `${total} commande${total > 1 ? "s" : ""}`;
  }

  /**
   * Enable quote-inputs only when shell mode is enabled.
   *
   * @param {HTMLElement} root - Mounted CLI modal root.
   */
  function updateQuoteInputState(root) {
    const useShell = root.querySelector("[data-cli-use-shell]");
    const quoteInputs = root.querySelector("[data-cli-quote-inputs]");
    if (!(useShell instanceof HTMLInputElement) || !(quoteInputs instanceof HTMLInputElement)) {
      return;
    }
    quoteInputs.disabled = !useShell.checked;
  }

  /**
   * Select one CLI modal tab, hide inactive panels, and optionally focus the tab.
   *
   * @param {HTMLElement} root - Mounted CLI modal root.
   * @param {HTMLElement} tab - Tab element to activate.
   * @param {object} options - Activation options.
   * @param {boolean} options.focus - Whether to move keyboard focus to the tab.
   */
  function activateTab(root, tab, { focus = false } = {}) {
    if (!(tab instanceof HTMLElement)) {
      return;
    }
    const tabId = String(tab.dataset.cliTabId || "");
    for (const candidate of tabElements(root)) {
      const selected = candidate === tab;
      candidate.setAttribute("aria-selected", selected ? "true" : "false");
      candidate.tabIndex = selected ? 0 : -1;
    }
    for (const panel of panelElements(root)) {
      panel.hidden = String(panel.dataset.cliTabId || "") !== tabId;
    }
    if (focus) {
      tab.focus();
    } else if (tabId === "command") {
      commandEditors(root)[0]?.focus();
    }
  }

  /**
   * Move tab selection by keyboard to a neighboring CLI tab.
   *
   * @param {HTMLElement} root - Mounted CLI modal root.
   * @param {HTMLElement} current - Currently focused tab.
   * @param {number} direction - Relative movement, usually -1 or 1.
   */
  function moveTab(root, current, direction) {
    const tabs = tabElements(root);
    const index = tabs.indexOf(current);
    if (index < 0 || !tabs.length) {
      return;
    }
    const nextIndex = (index + direction + tabs.length) % tabs.length;
    activateTab(root, tabs[nextIndex], { focus: true });
  }

  registry.cli = {
    /**
     * Bind CLI modal tabs, command shortcuts, and dependent shell options.
     *
     * @param {HTMLElement} root - Mounted CLI modal root.
     */
    mount(root) {
      const selected = root.querySelector('[data-cli-modal-tab][aria-selected="true"]')
        || root.querySelector("[data-cli-modal-tab]");
      const applyButton = root.querySelector("[data-block-apply]");
      activateTab(root, selected);
      updateCommandCount(root);
      updateQuoteInputState(root);

      root.addEventListener("click", (event) => {
        const target = event.target instanceof Element ? event.target : null;
        const tab = target?.closest("[data-cli-modal-tab]");
        if (!tab || !root.contains(tab)) {
          return;
        }
        event.preventDefault();
        activateTab(root, tab, { focus: true });
      });

      root.addEventListener("change", (event) => {
        const target = event.target instanceof Element ? event.target : null;
        if (target?.matches("[data-cli-use-shell]")) {
          updateQuoteInputState(root);
        }
      });

      root.addEventListener("keydown", (event) => {
        const target = event.target instanceof Element ? event.target : null;
        const tab = target?.closest("[data-cli-modal-tab]");
        if (tab && root.contains(tab)) {
          if (event.key === "ArrowRight" || event.key === "ArrowDown") {
            event.preventDefault();
            moveTab(root, tab, 1);
          } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
            event.preventDefault();
            moveTab(root, tab, -1);
          } else if (event.key === "Home") {
            event.preventDefault();
            activateTab(root, tabElements(root)[0], { focus: true });
          } else if (event.key === "End") {
            event.preventDefault();
            const tabs = tabElements(root);
            activateTab(root, tabs[tabs.length - 1], { focus: true });
          }
          return;
        }
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
          event.preventDefault();
          applyButton?.click();
        }
      });

      window.setTimeout(() => commandEditors(root)[0]?.focus(), 0);
    },
  };
})();
