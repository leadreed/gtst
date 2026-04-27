import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

const FACET_WIDGETS = ["project", "tree", "asset", "variant", "subvariant"];
const SUGGESTION_WIDGETS = [...FACET_WIDGETS, "version", "tag"];
const DEFAULTS = { variant: "base", subvariant: "default" };
const BROWSER_DEFAULTS = {};
const STYLE_ID = "gtst-facet-autocomplete-style";
const DEBOUNCE_MS = 150;
const WIDGET_ROW_HEIGHT = 20;

let active = null;
let highlightedIndex = 0;
let menuValues = [];
let requestId = 0;
let debounceTimer = null;
let widgetClickWrapped = false;
let promptToken = 0;

function isAssetRefNode(node) {
  return node?.comfyClass === "GTSTAssetRef" || node?.type === "GTSTAssetRef";
}

function isBrowserNode(node) {
  return node?.comfyClass === "BrowseGTST" || node?.type === "BrowseGTST";
}

function isSuggestionNode(node) {
  return isAssetRefNode(node) || isBrowserNode(node);
}

function isSuggestionWidget(widget) {
  return SUGGESTION_WIDGETS.includes(widget?.name);
}

function ensureStyles() {
  if (document.getElementById(STYLE_ID)) {
    return;
  }

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .gtst-facet-suggestions {
      background: var(--comfy-menu-bg, #222);
      border: 1px solid var(--border-color, #666);
      border-radius: 4px;
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.35);
      box-sizing: border-box;
      color: var(--input-text, #ddd);
      display: none;
      font: 12px sans-serif;
      max-height: 150px;
      min-width: 140px;
      overflow-y: auto;
      position: fixed;
      z-index: 10000;
    }

    .gtst-facet-suggestions button {
      background: transparent;
      border: 0;
      color: inherit;
      cursor: pointer;
      display: block;
      font: inherit;
      overflow: hidden;
      padding: 4px 8px;
      text-align: left;
      text-overflow: ellipsis;
      white-space: nowrap;
      width: 100%;
    }

    .gtst-facet-suggestions button[data-highlighted="true"],
    .gtst-facet-suggestions button:hover {
      background: #4f6f8f;
      color: #f2f7ff;
    }
  `;
  document.head.appendChild(style);
}

function menuElement() {
  ensureStyles();
  let menu = document.querySelector(".gtst-facet-suggestions");
  if (!menu) {
    menu = document.createElement("div");
    menu.className = "gtst-facet-suggestions";
    document.body.appendChild(menu);
  }
  return menu;
}

function inputDefaultForWidget(nodeData, name) {
  const spec = nodeData?.input?.required?.[name];
  const options = Array.isArray(spec) ? spec[1] : null;
  const defaults = nodeData?.name === "BrowseGTST" ? BROWSER_DEFAULTS : DEFAULTS;
  return options?.default ?? defaults[name] ?? "";
}

function committedDefaults(node) {
  return isBrowserNode(node) ? BROWSER_DEFAULTS : DEFAULTS;
}

function setWidgetValue(widget, value, node) {
  widget.value = value;
  widget.callback?.(value, app.canvas, node, app.canvas?.graph_mouse, {});
  node?.setDirtyCanvas?.(true, true);
}

function notifyCommitted(node, field) {
  if (!isBrowserNode(node)) {
    return;
  }
  window.dispatchEvent(
    new CustomEvent("gtst:browser-input-committed", {
      detail: { node, field },
    })
  );
}

function valuesForNode(node) {
  return Object.fromEntries(
    SUGGESTION_WIDGETS.map((name) => [
      name,
      String(node.widgets?.find((widget) => widget.name === name)?.value ?? ""),
    ])
  );
}

function suggestionUrl(field, node) {
  const params = new URLSearchParams({ field });
  for (const [name, value] of Object.entries(valuesForNode(node))) {
    params.set(name, value);
  }
  return `/gtst/facet_values?${params.toString()}`;
}

async function fetchSuggestions(field, node) {
  const response = await api.fetchApi(suggestionUrl(field, node));
  if (!response.ok) {
    return [];
  }
  const payload = await response.json();
  return Array.isArray(payload.values) ? payload.values : [];
}

function startsWithFilter(values, query) {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) {
    return values;
  }
  return values.filter((value) =>
    String(value).toLocaleLowerCase().startsWith(normalized)
  );
}

function activeQuery() {
  return String(active?.input?.value ?? active?.widget?.value ?? "");
}

function graphToClient(x, y) {
  const canvas = app.canvas;
  const rect = canvas.canvas.getBoundingClientRect();
  const scale = canvas.ds?.scale ?? 1;
  const offset = canvas.ds?.offset ?? [0, 0];
  return {
    x: rect.left + (x + offset[0]) * scale,
    y: rect.top + (y + offset[1]) * scale,
    scale,
  };
}

function positionMenu() {
  if (!active) {
    return;
  }
  const menu = menuElement();
  if (active.input instanceof HTMLInputElement) {
    const rect = active.input.getBoundingClientRect();
    menu.style.left = `${rect.left}px`;
    menu.style.top = `${rect.bottom + 4}px`;
    menu.style.width = `${Math.max(140, rect.width)}px`;
    return;
  }

  const widgetY = active.widget.last_y ?? 0;
  const { x, y, scale } = graphToClient(
    active.node.pos[0] + 8,
    active.node.pos[1] + widgetY + WIDGET_ROW_HEIGHT
  );
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  menu.style.width = `${Math.max(140, (active.node.size?.[0] ?? 180) * scale - 16)}px`;
}

function hideMenu() {
  menuValues = [];
  highlightedIndex = 0;
  requestId += 1;
  menuElement().style.display = "none";
}

function clearActive() {
  active = null;
  promptToken += 1;
  hideMenu();
}

function renderMenu(values) {
  const menu = menuElement();
  menu.replaceChildren(
    ...values.map((value, index) => {
      const item = document.createElement("button");
      item.type = "button";
      item.textContent = value;
      item.dataset.highlighted = String(index === highlightedIndex);
      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
        chooseSuggestion(index);
      });
      return item;
    })
  );

  if (!values.length) {
    hideMenu();
    return;
  }

  positionMenu();
  menu.style.display = "block";
}

async function refreshSuggestions(immediate = false) {
  if (!active) {
    return;
  }
  window.clearTimeout(debounceTimer);
  const run = async () => {
    const currentRequest = ++requestId;
    const field = active.field;
    const node = active.node;
    const values = await fetchSuggestions(field, node);
    if (
      currentRequest !== requestId ||
      !active ||
      active.field !== field ||
      active.node !== node
    ) {
      return;
    }
    menuValues = startsWithFilter(values, activeQuery());
    highlightedIndex = 0;
    renderMenu(menuValues);
  };

  if (immediate) {
    await run();
  } else {
    debounceTimer = window.setTimeout(run, DEBOUNCE_MS);
  }
}

function closeValueDialog() {
  const input = active?.input;
  if (!(input instanceof HTMLInputElement)) {
    return;
  }
  const dialog = input.closest(".graphdialog");
  const okButton = [...(dialog?.querySelectorAll("button") ?? [])].find(
    (button) => button.textContent?.trim().toLocaleLowerCase() === "ok"
  );
  if (okButton) {
    okButton.click();
    return;
  }
  dialog?.remove();
}

function applySuggestion(index, { closeDialog = false } = {}) {
  if (!active || !menuValues[index]) {
    return false;
  }
  const value = menuValues[index];
  if (active.input instanceof HTMLInputElement) {
    active.input.value = value;
    active.input.dispatchEvent(new Event("input", { bubbles: true }));
    active.input.dispatchEvent(new Event("change", { bubbles: true }));
    active.input.focus();
  }
  setWidgetValue(active.widget, value, active.node);
  if (FACET_WIDGETS.includes(active.field)) {
    commitFacet(active.node, active.field);
  }
  notifyCommitted(active.node, active.field);
  hideMenu();
  if (closeDialog) {
    closeValueDialog();
  }
  return true;
}

function chooseSuggestion(index) {
  applySuggestion(index, { closeDialog: true });
}

function candidateNodeForField(field) {
  if (active?.node?.widgets?.some((widget) => widget.name === field)) {
    return active.node;
  }
  const selected = Object.values(app.canvas.selected_nodes ?? {}).find(
    isSuggestionNode
  );
  if (selected?.widgets?.some((widget) => widget.name === field)) {
    return selected;
  }
  const over = app.canvas.node_over;
  if (isSuggestionNode(over)) {
    return over;
  }
  return null;
}

function activateFacet(node, field) {
  const widget = node?.widgets?.find((candidate) => candidate.name === field);
  if (!widget) {
    return false;
  }
  active = { node, widget, field, promptToken };
  hideMenu();
  refreshSuggestions(true);
  return true;
}

function setPendingPrompt(node, widget) {
  if (isSuggestionNode(node) && isSuggestionWidget(widget)) {
    promptToken += 1;
    active = { node, widget, field: widget.name, promptToken };
    return;
  }
  clearActive();
}

async function commitFacet(node, field) {
  const start = FACET_WIDGETS.indexOf(field) + 1;
  if (start <= 0) {
    return;
  }

  for (const laterField of FACET_WIDGETS.slice(start)) {
    const widget = node.widgets?.find((candidate) => candidate.name === laterField);
    if (!widget) {
      continue;
    }

    const validValues = await fetchSuggestions(laterField, node);
    const current = String(widget.value ?? "");
    const defaults = committedDefaults(node);
    const fallback = defaults[laterField] ?? "";
    if (!current && !fallback) {
      continue;
    }
    if (!validValues.includes(current)) {
      setWidgetValue(widget, fallback, node);
    }
  }
}

function fieldFromInput(target) {
  if (!(target instanceof HTMLInputElement)) {
    return null;
  }
  const label = target.getAttribute("aria-label");
  if (SUGGESTION_WIDGETS.includes(label)) {
    return label;
  }
  if (
    target.matches(".graphdialog .value") &&
    active?.promptToken === promptToken &&
    isSuggestionNode(active.node) &&
    isSuggestionWidget(active.widget)
  ) {
    return active?.field ?? null;
  }
  return null;
}

function installDocumentListeners() {
  document.addEventListener("focusin", (event) => {
    const field = fieldFromInput(event.target);
    if (!field) {
      return;
    }
    const node = candidateNodeForField(field);
    if (node && activateFacet(node, field)) {
      active.input = event.target;
    }
  });

  document.addEventListener("input", (event) => {
    const field = fieldFromInput(event.target);
    if (!field) {
      return;
    }
    if (!active || active.field !== field) {
      const node = candidateNodeForField(field);
      if (!node || !activateFacet(node, field)) {
        return;
      }
    }
    active.input = event.target;
    if (event.target.getAttribute("aria-label")) {
      setWidgetValue(active.widget, event.target.value, active.node);
    }
    refreshSuggestions();
  });

  document.addEventListener("keydown", (event) => {
    const field = fieldFromInput(event.target);
    if (!field || !active || active.field !== field) {
      return;
    }

    if (event.key === "Escape") {
      hideMenu();
      return;
    }
    if (event.key === "ArrowDown" && menuValues.length) {
      event.preventDefault();
      event.stopPropagation();
      highlightedIndex = (highlightedIndex + 1) % menuValues.length;
      renderMenu(menuValues);
      return;
    }
    if (event.key === "ArrowUp" && menuValues.length) {
      event.preventDefault();
      event.stopPropagation();
      highlightedIndex =
        (highlightedIndex - 1 + menuValues.length) % menuValues.length;
      renderMenu(menuValues);
      return;
    }
    if (event.key === "Tab" && menuValues.length) {
      event.preventDefault();
      event.stopPropagation();
      applySuggestion(highlightedIndex);
    }
  }, true);

  document.addEventListener("focusout", (event) => {
    const field = fieldFromInput(event.target);
    if (!field || !active || active.field !== field) {
      return;
    }
    const committed = active;
    window.setTimeout(() => {
      if (committed.input instanceof HTMLInputElement) {
        setWidgetValue(committed.widget, committed.input.value, committed.node);
      }
      if (FACET_WIDGETS.includes(committed.field)) {
        commitFacet(committed.node, committed.field);
      }
      notifyCommitted(committed.node, committed.field);
      hideMenu();
    }, 100);
  });

  document.addEventListener("pointerdown", (event) => {
    if (menuElement().contains(event.target)) {
      return;
    }
    if (!fieldFromInput(event.target)) {
      hideMenu();
    }
  });
}

function installWidgetClickHook() {
  if (widgetClickWrapped || !app.canvas?.processWidgetClick) {
    return;
  }
  widgetClickWrapped = true;

  const originalProcessWidgetClick = app.canvas.processWidgetClick;
  app.canvas.processWidgetClick = function (event, node, widget, pointer) {
    setPendingPrompt(node, widget);
    return originalProcessWidgetClick.call(this, event, node, widget, pointer);
  };
}

function widgetAtCanvasPoint(node, canvasY) {
  return node.widgets?.find((widget) => {
    if (!isSuggestionWidget(widget)) {
      return false;
    }
    const top = widget.last_y ?? -1;
    return canvasY >= top && canvasY <= top + WIDGET_ROW_HEIGHT;
  });
}

function enhanceNodePrototype(nodeType, nodeData) {
  const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    originalOnNodeCreated?.apply(this, arguments);

    for (const name of SUGGESTION_WIDGETS) {
      const widget = this.widgets?.find((candidate) => candidate.name === name);
      if (!widget) {
        continue;
      }
      widget.options ??= {};
      widget.options.gtstFacet = true;
      if (!widget.value) {
        setWidgetValue(widget, inputDefaultForWidget(nodeData, name), this);
      }
    }
  };

  const originalOnMouseDown = nodeType.prototype.onMouseDown;
  nodeType.prototype.onMouseDown = function (event, localPos, graphCanvas) {
    const widget = widgetAtCanvasPoint(this, localPos?.[1] ?? -1);
    if (widget) {
      setPendingPrompt(this, widget);
    }
    return originalOnMouseDown?.apply(this, [event, localPos, graphCanvas]);
  };
}

app.registerExtension({
  name: "gtst.assetRefFacetAutocomplete",

  setup() {
    ensureStyles();
    installDocumentListeners();
    installWidgetClickHook();
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!["GTSTAssetRef", "BrowseGTST"].includes(nodeData.name)) {
      return;
    }
    enhanceNodePrototype(nodeType, nodeData);
  },
});
