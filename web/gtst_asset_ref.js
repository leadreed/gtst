import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

const STYLE_ID = "gtst-facet-autocomplete-style";
const DEBOUNCE_MS = 150;
const WIDGET_ROW_HEIGHT = 20;

let facetWidgets = [];
let suggestionWidgets = ["version", "tag"];
let schemaPromise = null;
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

function isGtstNodeName(name) {
  return [
    "GTSTAssetRef",
    "BrowseGTST",
    "LoadGTSTImage",
    "SaveGTSTImage",
    "LoadGTSTText",
    "SaveGTSTText",
    "LoadGTSTVideo",
    "SaveGTSTVideo",
    "MarkGTSTReady",
    "TagGTSTVersion",
  ].includes(name);
}

function isSuggestionWidget(widget) {
  return suggestionWidgets.includes(widget?.name);
}

async function loadSchema() {
  if (!schemaPromise) {
    schemaPromise = api.fetchApi("/gtst/schema")
      .then((response) => (response.ok ? response.json() : {}))
      .then((payload) => {
        facetWidgets = Array.isArray(payload.facet_fields) ? payload.facet_fields : [];
        suggestionWidgets = Array.isArray(payload.suggestion_fields)
          ? payload.suggestion_fields
          : [...facetWidgets, "version", "tag"];
        return payload;
      })
      .catch(() => ({}));
  }
  return schemaPromise;
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
  return options?.default ?? "";
}

function committedDefaults(node) {
  return {};
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
    suggestionWidgets.map((name) => [
      name,
      String(node.widgets?.find((widget) => widget.name === name)?.value ?? ""),
    ])
  );
}

function widgetValue(node, name) {
  return String(node?.widgets?.find((widget) => widget.name === name)?.value ?? "");
}

function linkedOriginNode(node, inputName = "asset_ref") {
  const input = node?.inputs?.find((candidate) => candidate.name === inputName);
  const linkId = input?.link;
  const graph = node?.graph ?? app.graph;
  const link = linkId != null ? graph?.links?.[linkId] : null;
  if (!link) {
    return null;
  }
  return graph?.getNodeById?.(link.origin_id) ?? null;
}

function revealTargetForNode(node) {
  if (isAssetRefNode(node)) {
    return { kind: "values", values: valuesForNode(node) };
  }

  if (isBrowserNode(node)) {
    const selected = widgetValue(node, "selected_file_path");
    if (selected) {
      return { kind: "path", path: selected };
    }
    return { kind: "values", values: valuesForNode(node) };
  }

  const upstream = linkedOriginNode(node);
  if (isBrowserNode(upstream)) {
    const selected = widgetValue(upstream, "selected_file_path");
    if (selected) {
      return { kind: "path", path: selected };
    }
    return { kind: "values", values: valuesForNode(upstream) };
  }
  if (isAssetRefNode(upstream)) {
    return { kind: "values", values: valuesForNode(upstream) };
  }
  return null;
}

function notifyError(message) {
  console.error(message);
  if (app.ui?.dialog?.show) {
    app.ui.dialog.show(String(message));
  }
}

async function postJson(url, body) {
  const response = await api.fetchApi(url, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
  const payload = response.ok ? await response.json() : {};
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `GTST request failed: ${response.status}`);
  }
  return payload;
}

async function revealNodeTarget(node) {
  const target = revealTargetForNode(node);
  if (!target) {
    throw new Error("No resolvable GTST asset reference found for this node.");
  }
  if (target.kind === "path") {
    return postJson("/gtst/path_action", {
      action: "reveal",
      path: target.path,
    });
  }
  return postJson("/gtst/resolve_path_action", {
    action: "reveal",
    values: target.values,
  });
}

async function suggestionUrl(field, node) {
  await loadSchema();
  const params = new URLSearchParams({ field });
  for (const [name, value] of Object.entries(valuesForNode(node))) {
    params.set(name, value);
  }
  return `/gtst/facet_values?${params.toString()}`;
}

async function fetchSuggestions(field, node) {
  const response = await api.fetchApi(await suggestionUrl(field, node));
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
    return false;
  }
  const menu = menuElement();
  if (active.input instanceof HTMLInputElement) {
    if (!active.input.isConnected) {
      return false;
    }
    const rect = active.input.getBoundingClientRect();
    menu.style.left = `${rect.left}px`;
    menu.style.top = `${rect.bottom + 4}px`;
    menu.style.width = `${Math.max(140, rect.width)}px`;
    return true;
  }

  const widgetY = active.widget.last_y ?? 0;
  const { x, y, scale } = graphToClient(
    active.node.pos[0] + 8,
    active.node.pos[1] + widgetY + WIDGET_ROW_HEIGHT
  );
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  menu.style.width = `${Math.max(140, (active.node.size?.[0] ?? 180) * scale - 16)}px`;
  return true;
}

function hideMenu() {
  window.clearTimeout(debounceTimer);
  menuValues = [];
  highlightedIndex = 0;
  requestId += 1;
  const menu = menuElement();
  menu.style.display = "none";
  menu.replaceChildren();
}

function clearActive() {
  active = null;
  promptToken += 1;
  hideMenu();
}

function renderMenu(values) {
  if (!active) {
    hideMenu();
    return;
  }
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

  if (!positionMenu()) {
    hideMenu();
    return;
  }
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
  if (facetWidgets.includes(active.field)) {
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
  await loadSchema();
  const start = facetWidgets.indexOf(field) + 1;
  if (start <= 0) {
    return;
  }

  for (const laterField of facetWidgets.slice(start)) {
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
  if (suggestionWidgets.includes(label)) {
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
      if (facetWidgets.includes(committed.field)) {
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

    for (const name of suggestionWidgets) {
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

function addGtstContextMenu(nodeType) {
  const originalGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
  nodeType.prototype.getExtraMenuOptions = function (canvas, options) {
    originalGetExtraMenuOptions?.apply(this, arguments);
    options.push({
      content: "GTST",
      has_submenu: true,
      submenu: {
        options: [
          {
            content: "Reveal",
            callback: () => {
              revealNodeTarget(this).catch((error) => {
                notifyError(error?.message ?? error);
              });
            },
          },
        ],
      },
    });
  };
}

app.registerExtension({
  name: "gtst.assetRefFacetAutocomplete",

  setup() {
    ensureStyles();
    loadSchema();
    installDocumentListeners();
    installWidgetClickHook();
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    await loadSchema();
    if (!isGtstNodeName(nodeData.name)) {
      return;
    }
    addGtstContextMenu(nodeType);
    if (["GTSTAssetRef", "BrowseGTST"].includes(nodeData.name)) {
      enhanceNodePrototype(nodeType, nodeData);
    }
  },
});
