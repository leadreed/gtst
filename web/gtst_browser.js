import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

const STYLE_ID = "gtst-browser-style";
const RESULT_LIMIT = 1000;
const DEFAULT_NODE_SIZE = [420, 520];
const WIDGET_ROW_HEIGHT = 20;
const TILE_FOOTER_HEIGHT = 45;
const LOAD_PREVIEW_MIN_SIZE = [360, 380];
const LOAD_PREVIEW_INSET = 8;
const LOAD_PREVIEW_COMPACT_SIZE = [120, 90];
const BYPASS_MODE = 4;

const browserNodes = new Set();
const loadPreviewNodes = new Set();
let suggestionWidgets = ["version", "tag"];
let browserModes = ["current", "latest only", "all versions"];
let tagFilterModes = ["OR", "AND"];
let schemaPromise = null;
let animationStarted = false;
let executionRefreshTimer = null;
let activeActionMenu = null;

function isBrowserNode(node) {
  return node?.comfyClass === "BrowseGTST" || node?.type === "BrowseGTST";
}

function isAssetRefNode(node) {
  return node?.comfyClass === "GTSTAssetRef" || node?.type === "GTSTAssetRef";
}

function isLoadPreviewNode(node) {
  return ["LoadGTSTImage", "LoadGTSTVideo"].includes(
    node?.comfyClass ?? node?.type
  );
}

function expectedLoadPreviewMediaType(node) {
  const name = node?.comfyClass ?? node?.type;
  if (name === "LoadGTSTImage") {
    return "image";
  }
  if (name === "LoadGTSTVideo") {
    return "video";
  }
  return null;
}

function isNodeMutedOrBypassed(node) {
  return (
    node?.mode === globalThis.LiteGraph?.NEVER ||
    node?.mode === BYPASS_MODE ||
    node?.flags?.muted === true ||
    node?.flags?.bypassed === true
  );
}

function syncNodeDisabledState(element, node) {
  element.dataset.nodeDisabled = String(isNodeMutedOrBypassed(node));
}

async function loadSchema() {
  if (!schemaPromise) {
    schemaPromise = api.fetchApi("/gtst/schema")
      .then((response) => (response.ok ? response.json() : {}))
      .then((payload) => {
        suggestionWidgets = Array.isArray(payload.suggestion_fields)
          ? payload.suggestion_fields
          : ["version", "tag"];
        browserModes = Array.isArray(payload.browser_modes)
          ? payload.browser_modes
          : browserModes;
        tagFilterModes = Array.isArray(payload.browser_tag_filter_modes)
          ? payload.browser_tag_filter_modes
          : tagFilterModes;
        return payload;
      })
      .catch(() => ({}));
  }
  return schemaPromise;
}

function ensureStyles() {
  const style = document.getElementById(STYLE_ID) ?? document.createElement("style");
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

    .gtst-browser-tag-summary {
      align-items: center;
      display: none;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 4px;
      overflow: hidden;
    }

    .gtst-browser-tag-summary-label {
      color: #aeb7c2;
      flex: 0 0 auto;
    }

    .gtst-browser-tag-summary-chip,
    .gtst-browser-tag-chip {
      align-items: center;
      background: rgba(120, 168, 255, 0.12);
      border: 1px solid rgba(120, 168, 255, 0.26);
      border-radius: 4px;
      box-sizing: border-box;
      color: #cbd9ee;
      display: inline-flex;
      font: inherit;
      line-height: 1;
      max-width: 100%;
      min-width: 0;
    }

    .gtst-browser-tag-summary-chip {
      cursor: pointer;
      padding: 3px 6px;
    }

    .gtst-browser-tag-summary-chip:hover {
      background: rgba(120, 168, 255, 0.28);
      border-color: rgba(120, 168, 255, 0.72);
      color: #f2f7ff;
    }

    .gtst-browser-tag-summary-chip[data-active="true"] {
      background: rgba(120, 168, 255, 0.42);
      border-color: rgba(174, 206, 255, 0.95);
      box-shadow:
        0 0 0 1px rgba(174, 206, 255, 0.35),
        0 0 10px rgba(120, 168, 255, 0.28);
      color: #ffffff;
      font-weight: 700;
    }

    .gtst-browser-items {
      align-content: start;
      box-sizing: border-box;
      display: grid;
      flex: 1 1 auto;
      gap: 8px;
      min-height: 0;
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
      position: relative;
      text-align: left;
    }

    .gtst-browser-tile:focus-visible {
      outline: 2px solid #78a8ff;
      outline-offset: -2px;
    }

    .gtst-browser-tile[data-selected="true"] {
      border-color: #78a8ff;
      box-shadow: inset 0 0 0 1px #78a8ff;
    }

    .gtst-browser-grid[data-node-disabled="true"] .gtst-browser-tile,
    .gtst-load-preview[data-node-disabled="true"] .gtst-load-preview-body {
      filter: grayscale(0.75) saturate(0.45);
      opacity: 0.42;
    }

    .gtst-browser-tile-menu-button {
      align-items: center;
      background: rgba(12, 15, 19, 0.86);
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 4px;
      color: #f4f7fb;
      cursor: pointer;
      display: inline-flex;
      font: 15px/1 sans-serif;
      height: 24px;
      justify-content: center;
      opacity: 0;
      padding: 0;
      position: absolute;
      right: 6px;
      top: 6px;
      transition: opacity 120ms ease;
      width: 24px;
      z-index: 2;
    }

    .gtst-browser-tile:hover .gtst-browser-tile-menu-button,
    .gtst-browser-tile-menu-button:focus-visible,
    .gtst-browser-tile-menu-button[data-open="true"] {
      opacity: 1;
    }

    .gtst-browser-action-menu {
      background: var(--comfy-menu-bg, #222);
      border: 1px solid var(--border-color, #666);
      border-radius: 4px;
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.35);
      box-sizing: border-box;
      color: var(--input-text, #ddd);
      display: none;
      font: 12px sans-serif;
      min-width: 116px;
      overflow: hidden;
      position: fixed;
      z-index: 10001;
    }

    .gtst-browser-action-menu button {
      background: transparent;
      border: 0;
      color: inherit;
      cursor: pointer;
      display: block;
      font: inherit;
      padding: 6px 9px;
      text-align: left;
      width: 100%;
    }

    .gtst-browser-action-menu button:hover:not(:disabled) {
      background: #4f6f8f;
      color: #f2f7ff;
    }

    .gtst-browser-action-menu button:disabled {
      color: #7e8792;
      cursor: default;
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
      position: relative;
      width: 100%;
    }

    .gtst-browser-version-badge {
      align-items: center;
      background: rgba(12, 15, 19, 0.82);
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 4px;
      box-sizing: border-box;
      color: #f4f7fb;
      display: inline-flex;
      font-size: 11px;
      font-weight: 600;
      gap: 4px;
      left: 6px;
      line-height: 1;
      max-width: calc(100% - 12px);
      overflow: hidden;
      padding: 4px 5px;
      pointer-events: none;
      position: absolute;
      text-overflow: ellipsis;
      top: 6px;
      white-space: nowrap;
      z-index: 1;
    }

    .gtst-browser-version-badge[data-ready="true"] {
      background: rgba(38, 118, 74, 0.92);
      border-color: rgba(145, 230, 170, 0.78);
      color: #f4fff7;
      box-shadow: 0 0 0 1px rgba(18, 70, 42, 0.35);
    }

    .gtst-browser-ready-check {
      color: #ffffff;
      font-size: 12px;
      line-height: 1;
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
      flex: 0 0 var(--gtst-browser-footer-size, 50px);
      min-width: 0;
      overflow: hidden;
      padding: 5px 7px 5px;
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

    .gtst-browser-tags {
      display: flex;
      gap: 4px;
      margin-top: 4px;
      overflow: hidden;
      white-space: nowrap;
      width: 100%;
    }

    .gtst-browser-tag-chip {
      flex: 0 0 auto;
      font-size: 10px;
      max-width: 92px;
      overflow: hidden;
      padding: 2px 5px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .gtst-load-preview {
      background: #191b1f;
      border: 1px solid var(--border-color, #555);
      border-radius: 6px;
      box-sizing: border-box;
      color: var(--input-text, #ddd);
      display: flex;
      flex-direction: column;
      font: 12px sans-serif;
      overflow: hidden;
      padding: 8px;
      position: fixed;
      z-index: 20;
    }

    .gtst-load-preview-status {
      color: #aeb7c2;
      flex: 0 0 auto;
      margin-bottom: 6px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .gtst-load-preview-body {
      display: flex;
      flex: 1 1 auto;
      min-height: 0;
    }

    .gtst-load-preview-tile {
      cursor: default;
      height: 100%;
      width: 100%;
    }

    .gtst-load-preview-message {
      align-items: center;
      background: #242830;
      border: 1px solid #3c4450;
      border-radius: 6px;
      box-sizing: border-box;
      color: #dce3ec;
      display: flex;
      flex: 1 1 auto;
      justify-content: center;
      line-height: 1.35;
      min-height: 0;
      overflow-wrap: anywhere;
      padding: 12px;
      text-align: center;
      width: 100%;
    }
  `;
  if (!style.parentElement) {
    document.head.appendChild(style);
  }
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

function clientToGraph(clientX, clientY) {
  const canvas = app.canvas;
  const rect = canvas.canvas.getBoundingClientRect();
  const scale = canvas.ds?.scale ?? 1;
  const offset = canvas.ds?.offset ?? [0, 0];
  return {
    x: (clientX - rect.left) / scale - offset[0],
    y: (clientY - rect.top) / scale - offset[1],
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

function modeWidget(node) {
  return node.widgets?.find((widget) => widget.name === "mode");
}

function tagFilterModeWidget(node) {
  return node.widgets?.find((widget) => widget.name === "tag_filter_mode");
}

function normalizedMode(node) {
  const mode = modeWidget(node);
  sanitizeModeWidget(node, mode);
  return browserModes.includes(String(mode?.value ?? ""))
    ? String(mode.value)
    : "current";
}

function normalizedTagFilterMode(node) {
  const mode = tagFilterModeWidget(node);
  sanitizeTagFilterModeWidget(node, mode);
  return tagFilterModes.includes(String(mode?.value ?? ""))
    ? String(mode.value)
    : "OR";
}

function browserValues(node) {
  return Object.fromEntries(
    suggestionWidgets.map((name) => [name, widgetValue(node, name)])
  );
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

function splitTagValue(value) {
  return String(value ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function joinTagValue(tags) {
  return [...new Set(tags)].join(", ");
}

function toggleTagValue(value, tag) {
  const tags = splitTagValue(value);
  const next = tags.includes(tag)
    ? tags.filter((candidate) => candidate !== tag)
    : [...tags, tag];
  return joinTagValue(next);
}

function selectedPath(node) {
  return widgetValue(node, "selected_file_path");
}

function tileSize(node) {
  const value = Number(widgetValue(node, "preview_item_size"));
  return Math.min(600, Math.max(80, Number.isFinite(value) ? value : 140));
}

async function browserUrl(node) {
  await loadSchema();
  const params = new URLSearchParams({
    mode: normalizedMode(node),
    tag_filter_mode: normalizedTagFilterMode(node),
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

function actionMenuElement() {
  ensureStyles();
  let menu = document.querySelector(".gtst-browser-action-menu");
  if (!menu) {
    menu = document.createElement("div");
    menu.className = "gtst-browser-action-menu";
    document.body.appendChild(menu);
  }
  return menu;
}

function hideActionMenu() {
  if (activeActionMenu?.button) {
    activeActionMenu.button.dataset.open = "false";
  }
  activeActionMenu = null;
  actionMenuElement().style.display = "none";
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

async function previewAssetPayload(values, signal) {
  const response = await api.fetchApi("/gtst/preview_asset", {
    method: "POST",
    body: JSON.stringify({ values }),
    headers: { "Content-Type": "application/json" },
    signal,
  });
  const payload = response.ok ? await response.json() : {};
  if (!response.ok) {
    throw new Error(payload.error || `GTST request failed: ${response.status}`);
  }
  return payload;
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function showActionError(node, error) {
  const message = error?.message ?? String(error);
  console.error(message);
  setTileActionStatus(node, message);
}

function promptForTag(item) {
  const label = item.label ? ` for ${item.label}` : "";
  const tag = window.prompt(`Add GTST tag${label}`, "");
  return tag == null ? null : tag.trim();
}

function positionNodeAtClient(node, clientX, clientY) {
  const point = clientToGraph(clientX, clientY);
  const size = node.size ?? node.computeSize?.() ?? [220, 120];
  node.pos = [point.x - size[0] / 2, point.y - 12];
  node.setDirtyCanvas?.(true, true);
  app.graph.setDirtyCanvas?.(true, true);
}

function positionNodeAtGraphMouse(node) {
  const graphMouse = app.canvas?.graph_mouse;
  if (!Array.isArray(graphMouse)) {
    return;
  }
  const size = node.size ?? node.computeSize?.() ?? [220, 120];
  node.pos = [graphMouse[0] - size[0] / 2, graphMouse[1] - 12];
}

function startAssetRefPlacement(sourceNode, node, event) {
  setTileActionStatus(sourceNode, "Click to place Asset Ref");
  if (Number.isFinite(event?.clientX) && Number.isFinite(event?.clientY)) {
    positionNodeAtClient(node, event.clientX, event.clientY);
  } else {
    positionNodeAtGraphMouse(node);
  }

  const move = (moveEvent) => {
    positionNodeAtClient(node, moveEvent.clientX, moveEvent.clientY);
  };
  const finish = (clickEvent) => {
    clickEvent.preventDefault();
    clickEvent.stopPropagation();
    positionNodeAtClient(node, clickEvent.clientX, clickEvent.clientY);
    cleanup();
    setTileActionStatus(sourceNode, "Asset Ref created");
  };
  const cancel = (keyEvent) => {
    if (keyEvent.key !== "Escape") {
      return;
    }
    app.graph.remove?.(node);
    cleanup();
    setTileActionStatus(sourceNode, "Asset Ref creation canceled");
  };
  const cleanup = () => {
    document.removeEventListener("pointermove", move, true);
    document.removeEventListener("pointerdown", finish, true);
    document.removeEventListener("keydown", cancel, true);
  };

  window.setTimeout(() => {
    document.addEventListener("pointermove", move, true);
    document.addEventListener("pointerdown", finish, true);
    document.addEventListener("keydown", cancel, true);
  }, 0);
}

function createAssetRefNode(sourceNode, item, event) {
  const created = LiteGraph.createNode("GTSTAssetRef");
  if (!created) {
    throw new Error("Could not create GTST Asset Ref node.");
  }
  app.graph.add(created);

  for (const [name, value] of Object.entries(item.facets ?? {})) {
    setWidgetValue(created, name, String(value));
  }
  setWidgetValue(created, "version", String(item.version ?? ""));
  setWidgetValue(created, "tag", "");

  app.canvas.selectNode?.(created);
  created.setDirtyCanvas?.(true, true);
  app.graph.setDirtyCanvas?.(true, true);
  startAssetRefPlacement(sourceNode, created, event);
  return created;
}

function refreshGtstPreviewSurfaces() {
  scheduleRefreshAllBrowsers();
  scheduleRefreshAllLoadPreviews();
}

async function runTileAction(node, item, action, event) {
  try {
    if (action === "create-asset-ref") {
      createAssetRefNode(node, item, event);
      return;
    }
    if (action === "copy") {
      await copyText(item.file_path);
      setTileActionStatus(node, "Copied path");
      return;
    }
    if (action === "set-ready") {
      await postJson("/gtst/set_ready", { path: item.file_path });
      refreshGtstPreviewSurfaces();
      return;
    }
    if (action === "add-tag") {
      const tag = promptForTag(item);
      if (!tag) {
        return;
      }
      await postJson("/gtst/add_tag", { path: item.file_path, tag });
      refreshGtstPreviewSurfaces();
      return;
    }
    await postJson("/gtst/path_action", {
      action,
      path: item.file_path,
    });
  } catch (error) {
    showActionError(node, error);
  }
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
  const tagSummary = document.createElement("div");
  tagSummary.className = "gtst-browser-tag-summary";
  const selectionStatus = document.createElement("span");
  selectionStatus.className = "gtst-browser-status-line";
  status.append(resultStatus, selectionStatus, tagSummary);

  const items = document.createElement("div");
  items.className = "gtst-browser-items";

  element.append(status, items);
  document.body.appendChild(element);

  node.gtstBrowser = {
    element,
    items,
    resultStatus,
    selectionStatus,
    tagSummary,
    status,
    payloadItems: [],
    requestId: 0,
    resultController: null,
  };
  return node.gtstBrowser;
}

function loadPreviewSlotBottoms(node, isInput) {
  const slots = isInput ? node.inputs : node.outputs;
  return (slots ?? []).map((_, index) => {
    const pos = node.getConnectionPos?.(isInput, index, [0, 0]);
    if (!pos || typeof pos[1] !== "number" || typeof node.pos?.[1] !== "number") {
      return 0;
    }
    return pos[1] - node.pos[1] + (LiteGraph?.NODE_SLOT_HEIGHT ?? WIDGET_ROW_HEIGHT) * 0.5;
  });
}

function loadPreviewTop(node) {
  const widgetBottoms = (node.widgets ?? []).map(
    (widget, index) =>
      (typeof widget.last_y === "number" ? widget.last_y : 24 + index * WIDGET_ROW_HEIGHT) +
      WIDGET_ROW_HEIGHT
  );
  const slotBottoms = [
    ...loadPreviewSlotBottoms(node, true),
    ...loadPreviewSlotBottoms(node, false),
  ];
  return Math.max(0, ...widgetBottoms, ...slotBottoms) + LOAD_PREVIEW_INSET;
}

function ensureLoadPreviewOverlay(node) {
  ensureStyles();
  if (node.gtstLoadPreview?.element) {
    return node.gtstLoadPreview;
  }

  const element = document.createElement("div");
  element.className = "gtst-load-preview";

  const status = document.createElement("div");
  status.className = "gtst-load-preview-status";

  const body = document.createElement("div");
  body.className = "gtst-load-preview-body";

  element.append(status, body);
  document.body.appendChild(element);

  node.gtstLoadPreview = {
    element,
    status,
    body,
    previewItem: null,
    previewMode: null,
    requestId: 0,
    resultController: null,
  };
  return node.gtstLoadPreview;
}

function setResultStatus(node, text) {
  const state = ensureOverlay(node);
  state.resultStatus.textContent = text;
}

function canShowBrowserStatus(node) {
  return isBrowserNode(node);
}

function setTileActionStatus(node, text) {
  if (canShowBrowserStatus(node)) {
    setResultStatus(node, text);
  }
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

function sortedTagCounts(items) {
  const counts = new Map();
  for (const item of items) {
    for (const tag of new Set(item.tags ?? [])) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }
  return [...counts.entries()].sort(([left], [right]) => {
    if (left === "ready") {
      return -1;
    }
    if (right === "ready") {
      return 1;
    }
    return String(left).localeCompare(String(right));
  });
}

function updateTagSummary(node) {
  const state = ensureOverlay(node);
  const tagCounts = sortedTagCounts(state.payloadItems);
  state.tagSummary.replaceChildren();
  if (!tagCounts.length) {
    state.tagSummary.style.display = "none";
    return;
  }

  const currentTags = splitTagValue(widgetValue(node, "tag"));
  const label = document.createElement("span");
  label.className = "gtst-browser-tag-summary-label";
  label.textContent = "Tags:";

  state.tagSummary.append(
    label,
    ...tagCounts.map(([tag, count]) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "gtst-browser-tag-summary-chip";
      chip.dataset.active = String(currentTags.includes(tag));
      chip.textContent = `${tag} ${count}`;
      chip.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        setWidgetValue(node, "tag", toggleTagValue(widgetValue(node, "tag"), tag));
        refreshBrowser(node);
      });
      return chip;
    })
  );
  state.tagSummary.style.display = "flex";
}

function renderGtstPreview(item) {
  const preview = document.createElement("div");
  preview.className = "gtst-browser-preview";
  preview.append(renderVersionBadge(item));

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

function renderVersionBadge(item) {
  const badge = document.createElement("div");
  badge.className = "gtst-browser-version-badge";
  badge.textContent = displayVersion(item.version);
  const isReady = item.is_ready === true;
  badge.dataset.ready = String(isReady);

  if (isReady) {
    const check = document.createElement("span");
    check.className = "gtst-browser-ready-check";
    check.textContent = "✓";
    badge.append(check);
  }

  return badge;
}

function displayVersion(version) {
  return String(version ?? "").replace(/^v0*(\d+)$/, "v$1");
}

function renderGtstTileTags(item) {
  const tags = item.tags ?? [];
  if (!tags.length) {
    return null;
  }

  const row = document.createElement("div");
  row.className = "gtst-browser-tags";
  row.append(
    ...tags.map((tag) => {
      const chip = document.createElement("span");
      chip.className = "gtst-browser-tag-chip";
      chip.textContent = tag;
      return chip;
    })
  );
  return row;
}

function renderGtstTileLabel(item) {
  const label = document.createElement("div");
  label.className = "gtst-browser-label";

  const title = document.createElement("span");
  title.className = "gtst-browser-title";
  title.textContent = item.label ?? item.version ?? "GTST asset";

  const tagRow = renderGtstTileTags(item);
  label.append(title);
  if (tagRow) {
    label.append(tagRow);
  }
  return label;
}

function gtstItemTooltip(item) {
  const tags = item.tags?.length ? item.tags.join(", ") : "none";
  return [
    item.label ?? "GTST asset",
    item.subtitle ?? "",
    `Tags: ${tags}`,
  ]
    .filter(Boolean)
    .join("\n");
}

function renderTileMenuButton(node, item) {
  const menuButton = document.createElement("button");
  menuButton.type = "button";
  menuButton.className = "gtst-browser-tile-menu-button";
  menuButton.title = "GTST actions";
  menuButton.textContent = "⋯";
  menuButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    showTileActionMenu(node, item, menuButton);
  });
  return menuButton;
}

function renderGtstStandaloneTile(node, item, size) {
  const tile = document.createElement("div");
  tile.className = "gtst-browser-tile gtst-load-preview-tile";
  tile.style.setProperty("--gtst-browser-preview-size", `${size}px`);
  tile.style.setProperty("--gtst-browser-footer-size", `${TILE_FOOTER_HEIGHT}px`);
  tile.dataset.path = item.file_path ?? "";
  tile.title = gtstItemTooltip(item);
  tile.append(
    renderGtstPreview(item),
    renderTileMenuButton(node, item),
    renderGtstTileLabel(item)
  );
  return tile;
}

function renderTile(node, item) {
  const button = document.createElement("div");
  button.className = "gtst-browser-tile";
  button.style.setProperty("--gtst-browser-preview-size", `${tileSize(node)}px`);
  button.style.setProperty("--gtst-browser-footer-size", `${TILE_FOOTER_HEIGHT}px`);
  button.dataset.path = item.file_path ?? "";
  button.dataset.selected = String(item.file_path === selectedPath(node));
  button.title = gtstItemTooltip(item);
  button.role = "button";
  button.tabIndex = 0;

  const label = renderGtstTileLabel(item);
  button.append(renderGtstPreview(item), renderTileMenuButton(node, item), label);
  button.addEventListener("click", () => {
    const nextValue = item.file_path === selectedPath(node) ? "" : item.file_path;
    setWidgetValue(node, "selected_file_path", nextValue);
    updateGridSelection(node);
  });
  button.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    button.click();
  });
  return button;
}

function showTileActionMenu(node, item, anchor) {
  const menu = actionMenuElement();
  hideActionMenu();
  activeActionMenu = { node, item, button: anchor };
  anchor.dataset.open = "true";

  const actions = [
    ["Reveal", "reveal", false],
    ["Open", "open", false],
    ["Copy path", "copy", false],
    ["Create Asset Ref", "create-asset-ref", false],
    ["Add tag", "add-tag", false],
    [item.is_ready === true ? "Ready" : "Set ready", "set-ready", item.is_ready === true],
  ];
  menu.replaceChildren(
    ...actions.map(([label, action, disabled]) => {
      const itemButton = document.createElement("button");
      itemButton.type = "button";
      itemButton.textContent = label;
      itemButton.disabled = disabled;
      itemButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        hideActionMenu();
        runTileAction(node, item, action, event);
      });
      return itemButton;
    })
  );

  const rect = anchor.getBoundingClientRect();
  menu.style.left = `${rect.right - 116}px`;
  menu.style.top = `${rect.bottom + 4}px`;
  menu.style.display = "block";
}

function renderGrid(node) {
  hideActionMenu();
  const state = ensureOverlay(node);
  const size = tileSize(node);
  const scrollTop = state.items.scrollTop;
  state.items.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size}px, 1fr))`;
  state.items.style.gridAutoRows = `${size + TILE_FOOTER_HEIGHT}px`;
  state.items.replaceChildren(
    ...state.payloadItems.map((item) => renderTile(node, item))
  );
  state.items.scrollTop = scrollTop;
  updateTagSummary(node);
  updateSelectionStatus(node);
}

function loadPreviewValues(node) {
  const upstream = linkedOriginNode(node);
  if (!isAssetRefNode(upstream)) {
    return null;
  }
  return browserValues(upstream);
}

function loadPreviewPanelSize(node) {
  const top = loadPreviewTop(node);
  return {
    width: Math.max(0, (node.size?.[0] ?? 0) - LOAD_PREVIEW_INSET * 2),
    height: Math.max(0, (node.size?.[1] ?? 0) - top - LOAD_PREVIEW_INSET),
  };
}

function isCompactLoadPreview(node) {
  const { width, height } = loadPreviewPanelSize(node);
  return (
    width < LOAD_PREVIEW_COMPACT_SIZE[0] ||
    height < LOAD_PREVIEW_COMPACT_SIZE[1]
  );
}

function loadPreviewTileSize(node) {
  const { width, height } = loadPreviewPanelSize(node);
  const tileWidth = Math.max(0, width - LOAD_PREVIEW_INSET * 2);
  const tileHeight = Math.max(0, height - LOAD_PREVIEW_INSET - 34);
  return Math.min(600, Math.max(80, Math.floor(Math.min(tileWidth, tileHeight))));
}

function renderLoadPreview(node, item) {
  const state = ensureLoadPreviewOverlay(node);
  state.previewItem = item;
  if (isCompactLoadPreview(node)) {
    state.previewMode = "hidden";
    replaceLoadPreviewMessage(node, "Preview hidden");
    return;
  }
  state.previewMode = "tile";
  state.body.replaceChildren(renderGtstStandaloneTile(node, item, loadPreviewTileSize(node)));
}

function replaceLoadPreviewMessage(node, message) {
  const state = ensureLoadPreviewOverlay(node);
  const element = document.createElement("div");
  element.className = "gtst-load-preview-message";
  element.textContent = message;
  state.body.replaceChildren(element);
}

function renderLoadPreviewMessage(node, message) {
  const state = ensureLoadPreviewOverlay(node);
  state.previewItem = null;
  state.previewMode = "message";
  replaceLoadPreviewMessage(node, message);
}

function syncLoadPreviewCompactMode(node) {
  const state = ensureLoadPreviewOverlay(node);
  if (!state.previewItem) {
    return;
  }
  if (isCompactLoadPreview(node)) {
    if (state.previewMode !== "hidden") {
      state.previewMode = "hidden";
      replaceLoadPreviewMessage(node, "Preview hidden");
    }
    return;
  }
  if (state.previewMode !== "tile") {
    state.previewMode = "tile";
    state.body.replaceChildren(
      renderGtstStandaloneTile(node, state.previewItem, loadPreviewTileSize(node))
    );
  }
}

async function refreshLoadPreview(node) {
  if (!isLoadPreviewNode(node)) {
    return;
  }
  const state = ensureLoadPreviewOverlay(node);
  const requestId = ++state.requestId;
  state.resultController?.abort();
  const controller = new AbortController();
  state.resultController = controller;
  state.status.textContent = "Loading preview...";

  const values = loadPreviewValues(node);
  if (!values) {
    state.status.textContent = "Connect GTST Asset Ref";
    state.previewItem = null;
    state.previewMode = null;
    state.body.replaceChildren();
    if (state.resultController === controller) {
      state.resultController = null;
    }
    return;
  }

  try {
    const payload = await previewAssetPayload(values, controller.signal);
    if (requestId !== state.requestId) {
      return;
    }
    if (!payload.ok || !payload.item) {
      state.status.textContent = payload.error || "No preview";
      state.previewItem = null;
      state.previewMode = null;
      state.body.replaceChildren();
      return;
    }
    const expected = expectedLoadPreviewMediaType(node);
    const actual = payload.item.media_type ?? "file";
    if (expected && actual !== expected) {
      state.status.textContent = payload.item.subtitle ?? "";
      renderLoadPreviewMessage(node, `Expected ${expected}, got ${actual}`);
      return;
    }
    state.status.textContent = payload.item.subtitle ?? "";
    renderLoadPreview(node, payload.item);
  } catch (error) {
    if (error?.name === "AbortError") {
      return;
    }
    if (requestId !== state.requestId) {
      return;
    }
    state.previewItem = null;
    state.previewMode = null;
    state.status.textContent = String(error);
    state.body.replaceChildren();
  } finally {
    if (state.resultController === controller) {
      state.resultController = null;
    }
  }
}

function scheduleRefreshLoadPreview(node) {
  const state = ensureLoadPreviewOverlay(node);
  window.clearTimeout(state.refreshTimer);
  state.refreshTimer = window.setTimeout(() => {
    refreshLoadPreview(node);
  }, 0);
}

function scheduleRefreshAllLoadPreviews() {
  for (const node of loadPreviewNodes) {
    scheduleRefreshLoadPreview(node);
  }
}

function updateGridSelection(node) {
  const state = ensureOverlay(node);
  const selected = selectedPath(node);
  for (const tile of state.items.querySelectorAll(".gtst-browser-tile")) {
    tile.dataset.selected = String(tile.dataset.path === selected);
  }
  updateSelectionStatus(node);
}

async function refreshBrowser(node) {
  if (!isBrowserNode(node)) {
    return;
  }
  const state = ensureOverlay(node);
  const requestId = ++state.requestId;
  state.resultController?.abort();
  const controller = new AbortController();
  state.resultController = controller;
  setResultStatus(node, "Loading previews...");
  updateSelectionStatus(node);

  try {
    const response = await api.fetchApi(await browserUrl(node), {
      signal: controller.signal,
    });
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
    if (error?.name === "AbortError") {
      return;
    }
    if (requestId !== state.requestId) {
      return;
    }
    state.payloadItems = [];
    setResultStatus(node, String(error));
    renderGrid(node);
  } finally {
    if (state.resultController === controller) {
      state.resultController = null;
    }
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

function scheduleRefreshAllBrowsers() {
  window.clearTimeout(executionRefreshTimer);
  executionRefreshTimer = window.setTimeout(() => {
    for (const node of browserNodes) {
      scheduleRefreshBrowser(node);
    }
  }, 100);
}

function installExecutionRefresh() {
  api.addEventListener?.("executing", (event) => {
    if (event.detail === null || event.detail?.node === null) {
      scheduleRefreshAllBrowsers();
      scheduleRefreshAllLoadPreviews();
    }
  });
  api.addEventListener?.("execution_success", () => {
    scheduleRefreshAllBrowsers();
    scheduleRefreshAllLoadPreviews();
  });
  api.addEventListener?.("execution_error", () => {
    scheduleRefreshAllBrowsers();
    scheduleRefreshAllLoadPreviews();
  });
  api.addEventListener?.("execution_interrupted", () => {
    scheduleRefreshAllBrowsers();
    scheduleRefreshAllLoadPreviews();
  });
  api.addEventListener?.("status", (event) => {
    const remaining = Number(event.detail?.exec_info?.queue_remaining ?? 0);
    if (remaining === 0) {
      scheduleRefreshAllBrowsers();
      scheduleRefreshAllLoadPreviews();
    }
  });
}

function installActionMenuDismissal() {
  const dismissOnOutsidePress = (event) => {
    if (!activeActionMenu) {
      return;
    }
    const menu = actionMenuElement();
    const path = event.composedPath?.() ?? [];
    if (
      path.includes(menu) ||
      path.includes(activeActionMenu.button) ||
      menu.contains(event.target) ||
      activeActionMenu.button?.contains(event.target)
    ) {
      return;
    }
    hideActionMenu();
  };

  document.addEventListener("pointerdown", dismissOnOutsidePress, true);
  document.addEventListener("mousedown", dismissOnOutsidePress, true);
  document.addEventListener("contextmenu", dismissOnOutsidePress, true);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideActionMenu();
    }
  });

  document.addEventListener(
    "scroll",
    () => {
      hideActionMenu();
    },
    true
  );
}

function positionOverlay(node) {
  const state = ensureOverlay(node);
  syncNodeDisabledState(state.element, node);
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

function positionLoadPreviewOverlay(node) {
  const state = ensureLoadPreviewOverlay(node);
  syncNodeDisabledState(state.element, node);
  if (!node.graph || node.flags?.collapsed) {
    state.element.style.display = "none";
    return;
  }

  const top = loadPreviewTop(node);
  const { x, y, scale } = graphToClient(
    node.pos[0] + LOAD_PREVIEW_INSET,
    node.pos[1] + top
  );
  const { width, height } = loadPreviewPanelSize(node);
  state.element.style.display = "flex";
  state.element.style.left = `${x}px`;
  state.element.style.top = `${y}px`;
  state.element.style.width = `${width}px`;
  state.element.style.height = `${height}px`;
  state.element.style.transform = `scale(${scale})`;
  state.element.style.transformOrigin = "top left";
  syncLoadPreviewCompactMode(node);
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
    for (const node of loadPreviewNodes) {
      positionLoadPreviewOverlay(node);
    }
    window.requestAnimationFrame(tick);
  };
  window.requestAnimationFrame(tick);
}

function wrapBrowserWidgets(node) {
  const selected = node.widgets?.find((widget) => widget.name === "selected_file_path");
  hideWidget(selected);

  const mode = modeWidget(node);
  sanitizeModeWidget(node, mode);
  if (mode && !mode.gtstBrowserWrapped) {
    mode.gtstBrowserWrapped = true;
    const original = mode.callback;
    mode.callback = function () {
      const result = original?.apply(this, arguments);
      refreshBrowser(node);
      return result;
    };
  }

  const tagFilterMode = tagFilterModeWidget(node);
  sanitizeTagFilterModeWidget(node, tagFilterMode);
  if (tagFilterMode && !tagFilterMode.gtstBrowserWrapped) {
    tagFilterMode.gtstBrowserWrapped = true;
    const original = tagFilterMode.callback;
    tagFilterMode.callback = function () {
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

function sanitizeComboWidget(node, widget, values, fallback) {
  if (!widget) {
    return;
  }
  widget.options ??= {};
  widget.options.values = values;
  widget.options.serialize = true;
  if (Array.isArray(widget.values)) {
    widget.values = values;
  }
  if (!values.includes(String(widget.value ?? ""))) {
    widget.value = fallback;
    widget.callback?.(fallback, app.canvas, node, app.canvas?.graph_mouse, {});
    node.setDirtyCanvas?.(true, true);
  }
}

function sanitizeModeWidget(node, mode) {
  sanitizeComboWidget(node, mode, browserModes, "current");
}

function sanitizeTagFilterModeWidget(node, mode) {
  sanitizeComboWidget(node, mode, tagFilterModes, "OR");
}

window.addEventListener("gtst:browser-input-committed", (event) => {
  const node = event.detail?.node;
  if (isBrowserNode(node)) {
    refreshBrowser(node);
  }
});

window.addEventListener("gtst:asset-ref-input-committed", (event) => {
  const node = event.detail?.node;
  for (const loadNode of loadPreviewNodes) {
    if (linkedOriginNode(loadNode) === node) {
      scheduleRefreshLoadPreview(loadNode);
    }
  }
});

app.registerExtension({
  name: "gtst.browserGrid",

  setup() {
    ensureStyles();
    loadSchema();
    startOverlayLoop();
    installExecutionRefresh();
    installActionMenuDismissal();
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    await loadSchema();
    if (nodeData.name === "BrowseGTST") {
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
      return;
    }

    if (!["LoadGTSTImage", "LoadGTSTVideo"].includes(nodeData.name)) {
      return;
    }

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalOnNodeCreated?.apply(this, arguments);
      this.size = [
        Math.max(this.size?.[0] ?? 0, LOAD_PREVIEW_MIN_SIZE[0]),
        Math.max(this.size?.[1] ?? 0, LOAD_PREVIEW_MIN_SIZE[1]),
      ];
      loadPreviewNodes.add(this);
      ensureLoadPreviewOverlay(this);
      scheduleRefreshLoadPreview(this);
    };

    const originalOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = originalOnConfigure?.apply(this, arguments);
      loadPreviewNodes.add(this);
      ensureLoadPreviewOverlay(this);
      scheduleRefreshLoadPreview(this);
      return result;
    };

    const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
      const result = originalOnConnectionsChange?.apply(this, arguments);
      scheduleRefreshLoadPreview(this);
      return result;
    };

    const originalOnRemoved = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function () {
      loadPreviewNodes.delete(this);
      this.gtstLoadPreview?.element?.remove();
      return originalOnRemoved?.apply(this, arguments);
    };
  },
});
