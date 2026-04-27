import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

const FACET_WIDGETS = ["project", "tree", "asset", "variant", "subvariant"];
const DEFAULTS = { variant: "base", subvariant: "default" };
const STYLE_ID = "gtst-facet-autocomplete-style";
const DEBOUNCE_MS = 150;
const WIDGET_ROW_HEIGHT = 20;

let active = null;
let highlightedIndex = 0;
let menuValues = [];
let requestId = 0;
let debounceTimer = null;

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
      background: var(--content-hover-bg, #444);
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
  return options?.default ?? DEFAULTS[name] ?? "";
}

function setWidgetValue(widget, value, node) {
  widget.value = value;
  widget.callback?.(value, app.canvas, node, app.canvas?.graph_mouse, {});
  node?.setDirtyCanvas?.(true, true);
}

function valuesForNode(node) {
  return Object.fromEntries(
    FACET_WIDGETS.map((name) => [
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
  menuElement().style.display = "none";
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
    const values = await fetchSuggestions(active.field, active.node);
    if (currentRequest !== requestId || !active) {
      return;
    }
    menuValues = startsWithFilter(values, String(active.widget.value ?? ""));
    highlightedIndex = 0;
    renderMenu(menuValues);
  };

  if (immediate) {
    await run();
  } else {
    debounceTimer = window.setTimeout(run, DEBOUNCE_MS);
  }
}

function chooseSuggestion(index) {
  if (!active || !menuValues[index]) {
    return;
  }
  setWidgetValue(active.widget, menuValues[index], active.node);
  commitFacet(active.node, active.field);
  hideMenu();
}

function candidateNodeForField(field) {
  const selected = Object.values(app.canvas.selected_nodes ?? {}).find(
    (node) => node?.comfyClass === "GTSTAssetRef" || node?.type === "GTSTAssetRef"
  );
  if (selected?.widgets?.some((widget) => widget.name === field)) {
    return selected;
  }
  if (active?.node?.widgets?.some((widget) => widget.name === field)) {
    return active.node;
  }
  const over = app.canvas.node_over;
  if (over?.comfyClass === "GTSTAssetRef" || over?.type === "GTSTAssetRef") {
    return over;
  }
  return null;
}

function activateFacet(node, field) {
  const widget = node?.widgets?.find((candidate) => candidate.name === field);
  if (!widget) {
    return false;
  }
  active = { node, widget, field };
  refreshSuggestions(true);
  return true;
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
    const fallback = DEFAULTS[laterField] ?? "";
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
  return FACET_WIDGETS.includes(label) ? label : null;
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
    const node = active?.field === field ? active.node : candidateNodeForField(field);
    if (!node || !activateFacet(node, field)) {
      return;
    }
    active.input = event.target;
    setWidgetValue(active.widget, event.target.value, active.node);
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
      highlightedIndex = (highlightedIndex + 1) % menuValues.length;
      renderMenu(menuValues);
      return;
    }
    if (event.key === "ArrowUp" && menuValues.length) {
      event.preventDefault();
      highlightedIndex =
        (highlightedIndex - 1 + menuValues.length) % menuValues.length;
      renderMenu(menuValues);
      return;
    }
    if (event.key === "Enter" && menuValues.length) {
      event.preventDefault();
      chooseSuggestion(highlightedIndex);
    }
  });

  document.addEventListener("focusout", (event) => {
    const field = fieldFromInput(event.target);
    if (!field || !active || active.field !== field) {
      return;
    }
    const committed = active;
    window.setTimeout(() => {
      commitFacet(committed.node, committed.field);
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

function widgetAtCanvasPoint(node, canvasY) {
  return node.widgets?.find((widget) => {
    if (!FACET_WIDGETS.includes(widget.name)) {
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

    for (const name of FACET_WIDGETS) {
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
      active = { node: this, widget, field: widget.name };
      refreshSuggestions(true);
    }
    return originalOnMouseDown?.apply(this, [event, localPos, graphCanvas]);
  };
}

app.registerExtension({
  name: "gtst.assetRefFacetAutocomplete",

  setup() {
    ensureStyles();
    installDocumentListeners();
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "GTSTAssetRef") {
      return;
    }
    enhanceNodePrototype(nodeType, nodeData);
  },
});
