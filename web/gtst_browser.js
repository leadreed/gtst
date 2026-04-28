import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

const STYLE_ID = "gtst-browser-style";
const RESULT_LIMIT = 200;
const DEFAULT_NODE_SIZE = [420, 520];
const WIDGET_ROW_HEIGHT = 20;

const browserNodes = new Set();
let suggestionWidgets = ["version", "tag"];
let browserModes = ["current", "latest only", "all versions"];
let schemaPromise = null;
let animationStarted = false;
let executionRefreshTimer = null;
let activeActionMenu = null;

function isBrowserNode(node) {
  return node?.comfyClass === "BrowseGTST" || node?.type === "BrowseGTST";
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

function normalizedMode(node) {
  const mode = modeWidget(node);
  sanitizeModeWidget(node, mode);
  return browserModes.includes(String(mode?.value ?? ""))
    ? String(mode.value)
    : "current";
}

function browserValues(node) {
  return Object.fromEntries(
    suggestionWidgets.map((name) => [name, widgetValue(node, name)])
  );
}

function selectedPath(node) {
  return widgetValue(node, "selected_file_path");
}

function tileSize(node) {
  const value = Number(widgetValue(node, "preview_item_size"));
  return Math.min(240, Math.max(80, Number.isFinite(value) ? value : 140));
}

async function browserUrl(node) {
  await loadSchema();
  const params = new URLSearchParams({
    mode: normalizedMode(node),
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
  setResultStatus(node, message);
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

function startAssetRefPlacement(browserNode, node, event) {
  setResultStatus(browserNode, "Click to place Asset Ref");
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
    setResultStatus(browserNode, "Asset Ref created");
  };
  const cancel = (keyEvent) => {
    if (keyEvent.key !== "Escape") {
      return;
    }
    app.graph.remove?.(node);
    cleanup();
    setResultStatus(browserNode, "Asset Ref creation canceled");
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

function createAssetRefNode(browserNode, item, event) {
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
  startAssetRefPlacement(browserNode, created, event);
  return created;
}

async function runTileAction(node, item, action, event) {
  try {
    if (action === "create-asset-ref") {
      createAssetRefNode(node, item, event);
      return;
    }
    if (action === "copy") {
      await copyText(item.file_path);
      setResultStatus(node, "Copied path");
      return;
    }
    if (action === "set-ready") {
      await postJson("/gtst/set_ready", { path: item.file_path });
      await refreshBrowser(node);
      return;
    }
    if (action === "add-tag") {
      const tag = promptForTag(item);
      if (!tag) {
        return;
      }
      await postJson("/gtst/add_tag", { path: item.file_path, tag });
      await refreshBrowser(node);
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

function renderTile(node, item) {
  const button = document.createElement("div");
  button.className = "gtst-browser-tile";
  button.dataset.path = item.file_path ?? "";
  button.dataset.selected = String(item.file_path === selectedPath(node));
  button.role = "button";
  button.tabIndex = 0;

  const menuButton = document.createElement("button");
  menuButton.type = "button";
  menuButton.className = "gtst-browser-tile-menu-button";
  menuButton.title = "GTST actions";
  menuButton.textContent = "⋯";

  const label = document.createElement("div");
  label.className = "gtst-browser-label";

  const title = document.createElement("span");
  title.className = "gtst-browser-title";
  title.textContent = item.label ?? item.version ?? "GTST asset";

  const subtitle = document.createElement("span");
  subtitle.className = "gtst-browser-subtitle";
  subtitle.textContent = item.subtitle ?? item.file_path ?? "";

  label.append(title, subtitle);
  button.append(renderPreview(item), menuButton, label);
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
  menuButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    showTileActionMenu(node, item, menuButton);
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
  state.items.style.gridAutoRows = `${size + 38}px`;
  state.items.replaceChildren(
    ...state.payloadItems.map((item) => renderTile(node, item))
  );
  state.items.scrollTop = scrollTop;
  updateSelectionStatus(node);
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
  setResultStatus(node, "Loading previews...");
  updateSelectionStatus(node);

  try {
    const response = await api.fetchApi(await browserUrl(node));
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
    }
  });
  api.addEventListener?.("execution_success", scheduleRefreshAllBrowsers);
  api.addEventListener?.("execution_error", scheduleRefreshAllBrowsers);
  api.addEventListener?.("execution_interrupted", scheduleRefreshAllBrowsers);
  api.addEventListener?.("status", (event) => {
    const remaining = Number(event.detail?.exec_info?.queue_remaining ?? 0);
    if (remaining === 0) {
      scheduleRefreshAllBrowsers();
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

function sanitizeModeWidget(node, mode) {
  if (!mode) {
    return;
  }
  mode.options ??= {};
  mode.options.values = browserModes;
  mode.options.serialize = true;
  if (Array.isArray(mode.values)) {
    mode.values = browserModes;
  }
  if (!browserModes.includes(String(mode.value ?? ""))) {
    mode.value = "current";
    mode.callback?.("current", app.canvas, node, app.canvas?.graph_mouse, {});
    node.setDirtyCanvas?.(true, true);
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
    loadSchema();
    startOverlayLoop();
    installExecutionRefresh();
    installActionMenuDismissal();
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    await loadSchema();
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
