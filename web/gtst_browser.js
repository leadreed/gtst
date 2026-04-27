import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

const FACET_WIDGETS = ["project", "tree", "asset", "variant", "subvariant"];
const SUGGESTION_WIDGETS = [...FACET_WIDGETS, "version", "tag"];
const STYLE_ID = "gtst-browser-style";
const RESULT_LIMIT = 200;
const DEFAULT_NODE_SIZE = [420, 520];
const WIDGET_ROW_HEIGHT = 20;

const browserNodes = new Set();
let animationStarted = false;

function isBrowserNode(node) {
  return node?.comfyClass === "BrowseGTST" || node?.type === "BrowseGTST";
}

function ensureStyles() {
  if (document.getElementById(STYLE_ID)) {
    return;
  }

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .gtst-browser-grid {
      background: #191b1f;
      border: 1px solid var(--border-color, #555);
      border-radius: 6px;
      box-sizing: border-box;
      color: var(--input-text, #ddd);
      display: flex;
      flex-direction: column;
      font: 12px sans-serif;
      overflow: hidden;
      position: fixed;
      z-index: 20;
    }

    .gtst-browser-status {
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      box-sizing: border-box;
      color: #aeb7c2;
      flex: 0 0 auto;
      overflow: hidden;
      padding: 5px 8px;
    }

    .gtst-browser-status-line {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .gtst-browser-status-line + .gtst-browser-status-line {
      margin-top: 2px;
    }

    .gtst-browser-items {
      align-content: start;
      box-sizing: border-box;
      display: grid;
      flex: 1 1 auto;
      gap: 8px;
      overflow-x: hidden;
      overflow-y: auto;
      padding: 8px;
    }

    .gtst-browser-tile {
      background: #242830;
      border: 1px solid #3c4450;
      border-radius: 6px;
      box-sizing: border-box;
      color: inherit;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      min-width: 0;
      overflow: hidden;
      padding: 0;
      text-align: left;
    }

    .gtst-browser-tile[data-selected="true"] {
      border-color: #78a8ff;
      box-shadow: inset 0 0 0 1px #78a8ff;
    }

    .gtst-browser-preview {
      align-items: center;
      background: #101216;
      box-sizing: border-box;
      display: flex;
      flex: 1 1 auto;
      justify-content: center;
      min-height: 0;
      overflow: hidden;
      padding: 6px;
      width: 100%;
    }

    .gtst-browser-preview img,
    .gtst-browser-preview video {
      height: 100%;
      max-height: 100%;
      max-width: 100%;
      object-fit: contain;
      width: 100%;
    }

    .gtst-browser-text {
      box-sizing: border-box;
      color: #dce3ec;
      display: -webkit-box;
      line-height: 1.3;
      overflow: hidden;
      overflow-wrap: anywhere;
      white-space: normal;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 8;
    }

    .gtst-browser-file {
      color: #b9c4d0;
      font-size: 28px;
      letter-spacing: 0;
      text-transform: uppercase;
    }

    .gtst-browser-label {
      box-sizing: border-box;
      flex: 0 0 38px;
      min-width: 0;
      overflow: hidden;
      padding: 5px 7px 6px;
    }

    .gtst-browser-title,
    .gtst-browser-subtitle {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .gtst-browser-title {
      color: #f0f4f8;
    }

    .gtst-browser-subtitle {
      color: #9aa7b5;
      font-size: 11px;
      margin-top: 2px;
    }
  `;
  document.head.appendChild(style);
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

function widgetValue(node, name) {
  return String(node.widgets?.find((widget) => widget.name === name)?.value ?? "");
}

function setWidgetValue(node, name, value) {
  const widget = node.widgets?.find((candidate) => candidate.name === name);
  if (!widget) {
    return;
  }
  widget.value = value;
  widget.callback?.(value, app.canvas, node, app.canvas?.graph_mouse, {});
  node.setDirtyCanvas?.(true, true);
}

function browserValues(node) {
  return Object.fromEntries(
    SUGGESTION_WIDGETS.map((name) => [name, widgetValue(node, name)])
  );
}

function selectedPath(node) {
  return widgetValue(node, "selected_file_path");
}

function tileSize(node) {
  const value = Number(widgetValue(node, "preview_item_size"));
  return Math.min(240, Math.max(80, Number.isFinite(value) ? value : 140));
}

function browserUrl(node) {
  const params = new URLSearchParams({
    mode: widgetValue(node, "mode") || "current",
    limit: String(RESULT_LIMIT),
  });
  for (const [name, value] of Object.entries(browserValues(node))) {
    params.set(name, value);
  }
  return `/gtst/browser_results?${params.toString()}`;
}

function fileUrl(filePath) {
  return `/gtst/browser_file?path=${encodeURIComponent(filePath)}`;
}

function hideWidget(widget) {
  if (!widget || widget.gtstHidden) {
    return;
  }
  widget.gtstHidden = true;
  widget.computeSize = () => [0, -4];
  widget.draw = () => {};
}

function gridTop(node) {
  const visibleWidgets = (node.widgets ?? []).filter(
    (widget) => !widget.gtstHidden
  );
  const widgetBottoms = visibleWidgets.map(
    (widget, index) =>
      (typeof widget.last_y === "number" ? widget.last_y : 24 + index * WIDGET_ROW_HEIGHT) +
      WIDGET_ROW_HEIGHT
  );
  return Math.max(210, Math.max(0, ...widgetBottoms) + 10);
}

function ensureOverlay(node) {
  ensureStyles();
  if (node.gtstBrowser?.element) {
    return node.gtstBrowser;
  }

  const element = document.createElement("div");
  element.className = "gtst-browser-grid";

  const status = document.createElement("div");
  status.className = "gtst-browser-status";
  const resultStatus = document.createElement("span");
  resultStatus.className = "gtst-browser-status-line";
  const selectionStatus = document.createElement("span");
  selectionStatus.className = "gtst-browser-status-line";
  status.append(resultStatus, selectionStatus);

  const items = document.createElement("div");
  items.className = "gtst-browser-items";

  element.append(status, items);
  document.body.appendChild(element);

  node.gtstBrowser = {
    element,
    items,
    resultStatus,
    selectionStatus,
    status,
    payloadItems: [],
    requestId: 0,
  };
  return node.gtstBrowser;
}

function setResultStatus(node, text) {
  const state = ensureOverlay(node);
  state.resultStatus.textContent = text;
}

function selectedItem(node) {
  const selected = selectedPath(node);
  if (!selected) {
    return null;
  }
  return ensureOverlay(node).payloadItems.find((item) => item.file_path === selected) ?? null;
}

function updateSelectionStatus(node) {
  const state = ensureOverlay(node);
  const item = selectedItem(node);
  state.selectionStatus.textContent = item?.label ? `Selected: ${item.label}` : "No selection";
}

function renderPreview(item) {
  const preview = document.createElement("div");
  preview.className = "gtst-browser-preview";

  if (item.media_type === "image") {
    const image = document.createElement("img");
    image.loading = "lazy";
    image.src = fileUrl(item.file_path);
    preview.append(image);
    return preview;
  }

  if (item.media_type === "video") {
    const video = document.createElement("video");
    video.autoplay = true;
    video.loop = true;
    video.muted = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.src = fileUrl(item.file_path);
    video.addEventListener("mouseenter", () => {
      video.muted = false;
    });
    video.addEventListener("mouseleave", () => {
      video.muted = true;
    });
    video.play?.().catch?.(() => {});
    preview.append(video);
    return preview;
  }

  if (item.media_type === "text") {
    const text = document.createElement("div");
    text.className = "gtst-browser-text";
    text.textContent = item.preview_text ?? "";
    preview.append(text);
    return preview;
  }

  const file = document.createElement("div");
  file.className = "gtst-browser-file";
  file.textContent = (item.file_path?.split(".").pop() || "file").slice(0, 5);
  preview.append(file);
  return preview;
}

function renderTile(node, item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "gtst-browser-tile";
  button.dataset.selected = String(item.file_path === selectedPath(node));

  const label = document.createElement("div");
  label.className = "gtst-browser-label";

  const title = document.createElement("span");
  title.className = "gtst-browser-title";
  title.textContent = item.label ?? item.version ?? "GTST asset";

  const subtitle = document.createElement("span");
  subtitle.className = "gtst-browser-subtitle";
  subtitle.textContent = item.subtitle ?? item.file_path ?? "";

  label.append(title, subtitle);
  button.append(renderPreview(item), label);
  button.addEventListener("click", () => {
    const nextValue = item.file_path === selectedPath(node) ? "" : item.file_path;
    setWidgetValue(node, "selected_file_path", nextValue);
    renderGrid(node);
  });
  return button;
}

function renderGrid(node) {
  const state = ensureOverlay(node);
  const size = tileSize(node);
  state.items.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size}px, 1fr))`;
  state.items.style.gridAutoRows = `${size + 38}px`;
  state.items.replaceChildren(
    ...state.payloadItems.map((item) => renderTile(node, item))
  );
  updateSelectionStatus(node);
}

async function refreshBrowser(node) {
  if (!isBrowserNode(node)) {
    return;
  }
  const state = ensureOverlay(node);
  const requestId = ++state.requestId;
  setResultStatus(node, "Loading previews...");
  updateSelectionStatus(node);

  try {
    const response = await api.fetchApi(browserUrl(node));
    const payload = response.ok ? await response.json() : { items: [] };
    if (requestId !== state.requestId) {
      return;
    }

    state.payloadItems = Array.isArray(payload.items) ? payload.items : [];
    const paths = new Set(state.payloadItems.map((item) => item.file_path));
    if (selectedPath(node) && !paths.has(selectedPath(node))) {
      setWidgetValue(node, "selected_file_path", "");
    }

    const count = state.payloadItems.length;
    if (payload.error) {
      setResultStatus(node, payload.error);
    } else if (!count) {
      setResultStatus(node, "No previews");
    } else if (payload.capped) {
      setResultStatus(node, `Showing first ${count} previews`);
    } else {
      setResultStatus(node, `${count} preview${count === 1 ? "" : "s"}`);
    }
    renderGrid(node);
  } catch (error) {
    if (requestId !== state.requestId) {
      return;
    }
    state.payloadItems = [];
    setResultStatus(node, String(error));
    renderGrid(node);
  }
}

function scheduleRefreshBrowser(node) {
  const state = ensureOverlay(node);
  window.clearTimeout(state.refreshTimer);
  state.refreshTimer = window.setTimeout(() => {
    wrapBrowserWidgets(node);
    refreshBrowser(node);
  }, 0);
}

function positionOverlay(node) {
  const state = ensureOverlay(node);
  if (!node.graph || node.flags?.collapsed) {
    state.element.style.display = "none";
    return;
  }

  const top = gridTop(node);
  const { x, y, scale } = graphToClient(node.pos[0] + 8, node.pos[1] + top);
  const width = Math.max(120, (node.size?.[0] ?? DEFAULT_NODE_SIZE[0]) - 16);
  const height = Math.max(120, (node.size?.[1] ?? DEFAULT_NODE_SIZE[1]) - top - 8);
  state.element.style.display = "flex";
  state.element.style.left = `${x}px`;
  state.element.style.top = `${y}px`;
  state.element.style.width = `${width}px`;
  state.element.style.height = `${height}px`;
  state.element.style.transform = `scale(${scale})`;
  state.element.style.transformOrigin = "top left";
}

function startOverlayLoop() {
  if (animationStarted) {
    return;
  }
  animationStarted = true;

  const tick = () => {
    for (const node of browserNodes) {
      positionOverlay(node);
    }
    window.requestAnimationFrame(tick);
  };
  window.requestAnimationFrame(tick);
}

function wrapBrowserWidgets(node) {
  const selected = node.widgets?.find((widget) => widget.name === "selected_file_path");
  hideWidget(selected);

  const mode = node.widgets?.find((widget) => widget.name === "mode");
  if (mode && !mode.gtstBrowserWrapped) {
    mode.gtstBrowserWrapped = true;
    const original = mode.callback;
    mode.callback = function () {
      const result = original?.apply(this, arguments);
      refreshBrowser(node);
      return result;
    };
  }

  const size = node.widgets?.find((widget) => widget.name === "preview_item_size");
  if (size && !size.gtstBrowserWrapped) {
    size.gtstBrowserWrapped = true;
    const original = size.callback;
    size.callback = function () {
      const result = original?.apply(this, arguments);
      renderGrid(node);
      return result;
    };
  }
}

window.addEventListener("gtst:browser-input-committed", (event) => {
  const node = event.detail?.node;
  if (isBrowserNode(node)) {
    refreshBrowser(node);
  }
});

app.registerExtension({
  name: "gtst.browserGrid",

  setup() {
    ensureStyles();
    startOverlayLoop();
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "BrowseGTST") {
      return;
    }

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalOnNodeCreated?.apply(this, arguments);
      this.size = [
        Math.max(this.size?.[0] ?? 0, DEFAULT_NODE_SIZE[0]),
        Math.max(this.size?.[1] ?? 0, DEFAULT_NODE_SIZE[1]),
      ];
      browserNodes.add(this);
      ensureOverlay(this);
      wrapBrowserWidgets(this);
      scheduleRefreshBrowser(this);
    };

    const originalOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = originalOnConfigure?.apply(this, arguments);
      browserNodes.add(this);
      ensureOverlay(this);
      scheduleRefreshBrowser(this);
      return result;
    };

    const originalOnRemoved = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function () {
      browserNodes.delete(this);
      this.gtstBrowser?.element?.remove();
      return originalOnRemoved?.apply(this, arguments);
    };
  },
});
