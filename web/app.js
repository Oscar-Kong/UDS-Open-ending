const thread = document.getElementById("thread");
const empty = document.getElementById("empty");
const starters = document.getElementById("starters");
const message = document.getElementById("message");
const send = document.getElementById("send");
const hint = document.getElementById("hint");
const chatModel = document.getElementById("chat-model");

const messages = [];
let currentId = null;
let viewToken = 0;
let latestModel = { has_key: false, model: "", base_url: "" };
let libraryName = "";
let modelNames = [];
let listError = "";
let modelSynced = false;
let evalCatalog = null;
let evalRunning = false;
let evalSamples = [];
let evalModels = [];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function setView(name) {
  document.querySelectorAll(".nav").forEach((button) => {
    button.classList.toggle("is-on", button.dataset.view === name);
  });
  document.getElementById("chat").hidden = name !== "chat";
  document.getElementById("library").hidden = name !== "library";
  document.getElementById("evaluate").hidden = name !== "evaluate";
  if (name === "library") loadLibrary();
  if (name === "evaluate") loadEvaluation();
}

document.querySelectorAll(".nav").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

document.getElementById("new-chat").addEventListener("click", () => {
  viewToken += 1;
  currentId = null;
  messages.length = 0;
  thread.querySelectorAll(".turn").forEach((node) => node.remove());
  empty.hidden = false;
  starters.hidden = false;
  syncFrame();
  setView("chat");
  loadHistory();
  message.focus();
});

document.getElementById("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  ask(message.value);
});

message.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    ask(message.value);
  }
});

message.addEventListener("input", () => {
  message.style.height = "auto";
  message.style.height = Math.min(message.scrollHeight, 160) + "px";
});

chatModel.addEventListener("change", () => {
  applyHint();
  if (chatModel.value) saveSettings({ model: chatModel.value }, { silent: true });
});

starters.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) ask(button.textContent);
});

async function ask(text) {
  const question = text.trim();
  if (!question || send.disabled) return;
  const token = viewToken;
  const requestChat = currentId;
  const chosenModel = chatModel.value;
  message.value = "";
  message.style.height = "auto";
  empty.hidden = true;
  starters.hidden = true;
  messages.push({ role: "user", content: question });
  addTurn("user", question);
  const pending = addPending();
  send.disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question, model: chosenModel, chat_id: requestChat }),
    });
    const payload = await response.json();
    if (token !== viewToken) return;
    pending.remove();
    if (!response.ok) {
      addTurn("assistant", payload.error || "The question did not go through.");
      return;
    }
    currentId = payload.chat_id;
    messages.push({ role: "assistant", content: payload.text });
    addTurn("assistant", payload.text, payload.quotes || [], payload.accuracy, payload.findings || [], payload.dashboard, payload.model, payload.source, { stream: true, token });
  } catch (error) {
    if (token !== viewToken) return;
    pending.remove();
    addTurn("assistant", "The server did not answer. Check that it is still running.");
  } finally {
    send.disabled = false;
    loadHistory();
    if (token === viewToken) message.focus();
  }
}

function addPending() {
  const turn = el("div", "turn assistant has-facts pending");
  turn.append(factsShell("Reading…"));
  const reply = el("div", "reply");
  reply.append(el("div", "bubble", "Reading the filtered comments…"));
  turn.append(reply);
  thread.append(turn);
  followThread(true);
  syncFrame();
  return turn;
}

function addTurn(role, text, quotes, accuracy, findings, dashboard, modelName, source, options) {
  const turn = el("div", `turn ${role}`);
  const counts = (findings || []).filter((block) => block.agent === "Scope" || block.agent === "Stance" || block.agent === "Reasons");
  const host = counts.length ? el("div", "reply") : turn;
  if (counts.length) {
    turn.classList.add("has-facts");
    turn.append(factsPanel(findings));
  }
  if (dashboard && (dashboard.kind === "bars" || dashboard.kind === "table")) host.append(dashboardPanel(dashboard));
  const stream = Boolean(options && options.stream) && role === "assistant";
  const bubble = el("div", stream ? "bubble is-streaming" : "bubble", stream ? "" : text);
  if (stream) bubble.setAttribute("aria-busy", "true");
  if (role === "assistant" && counts.length) {
    const summary = el("div", "summary");
    summary.append(el("p", "accuracy-title", "Summary"));
    summary.append(bubble);
    host.append(summary);
  } else {
    host.append(bubble);
  }
  const later = [];
  if (quotes && quotes.length) {
    const list = el("div", "quotes");
    quotes.forEach((quote) => {
      const block = document.createElement("blockquote");
      const bits = [`ID ${quote.id}`];
      if (quote.year) bits.push(String(quote.year));
      if (quote.college) bits.push(quote.college);
      block.append(el("footer", "", bits.join(" · ")));
      block.append(el("p", "", quote.text));
      list.append(block);
    });
    later.push(list);
  }
  const evidence = (findings || []).find((block) => block.agent === "Evidence");
  if (evidence && evidence.lines && evidence.lines.length) later.push(el("p", "evidence-line", evidence.lines[0]));
  if (accuracy && accuracy.checks) later.push(accuracyPanel(accuracy));
  if (role === "assistant" && modelName) {
    const label = source && source !== "model" ? `${modelName} · filtered summary` : modelName;
    later.push(el("p", "turn-model", label));
  }
  later.forEach((node) => {
    if (stream) node.hidden = true;
    host.append(node);
  });
  if (host !== turn) turn.append(host);
  thread.append(turn);
  followThread(true);
  syncFrame();
  if (stream) writeGradually(bubble, text || "", options.token).then(() => {
    const gap = thread.scrollHeight - thread.scrollTop - thread.clientHeight;
    later.forEach((node) => { node.hidden = false; });
    if (gap < 140) thread.scrollTop = thread.scrollHeight;
  });
  return turn;
}

function syncFrame() {
  document.getElementById("chat").classList.toggle("is-open", thread.querySelector(".turn") != null);
}

function followThread(force) {
  const gap = thread.scrollHeight - thread.scrollTop - thread.clientHeight;
  if (force || gap < 140) thread.scrollTop = thread.scrollHeight;
}

function writeGradually(node, text, token) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || text.length < 12) {
    node.textContent = text;
    node.classList.remove("is-streaming");
    node.removeAttribute("aria-busy");
    return Promise.resolve();
  }
  const words = text.split(/(\s+)/);
  let index = 0;
  return new Promise((resolve) => {
    const step = () => {
      if (!node.isConnected || token !== viewToken) {
        resolve();
        return;
      }
      let added = 0;
      while (index < words.length && added < 1) {
        node.textContent += words[index];
        if (words[index].trim()) added += 1;
        index += 1;
      }
      followThread(false);
      if (index >= words.length) {
        node.classList.remove("is-streaming");
        node.removeAttribute("aria-busy");
        resolve();
        return;
      }
      window.setTimeout(step, 28);
    };
    step();
  });
}

function factsShell(wait) {
  const side = el("aside", "facts");
  side.setAttribute("aria-label", "Scope, stance, and reasons");
  ["Scope", "Stance", "Reasons"].forEach((name) => {
    const section = el("section", "fact");
    section.append(el("h3", "", name));
    section.append(factTable([{ label: wait, value: "" }]));
    side.append(section);
  });
  return side;
}

function factsPanel(findings) {
  const side = el("aside", "facts");
  side.setAttribute("aria-label", "Scope, stance, and reasons");
  const groups = new Map();
  (findings || []).forEach((block) => {
    if (block.agent !== "Scope" && block.agent !== "Stance" && block.agent !== "Reasons") return;
    const key = block.label || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(block);
  });
  const named = [...groups.keys()].filter((label) => label && label !== "All respondents" && label !== "All slices");
  groups.forEach((blocks, label) => {
    if (named.length > 1 && named.includes(label)) side.append(el("p", "fact-slice", label));
    blocks.forEach((block) => {
      const section = el("section", "fact");
      section.append(el("h3", "", block.agent));
      const rows = (block.lines || []).flatMap((line) => factRows(block.agent, line));
      section.append(factTable(rows.length ? rows : [{ label: block.lines[0] || "", value: "" }]));
      side.append(section);
    });
  });
  return side;
}

function factTable(rows) {
  const table = document.createElement("table");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = row.label;
    const value = document.createElement("td");
    value.textContent = row.value;
    if (row.title) {
      label.title = row.title;
      value.title = row.title;
    }
    tr.append(label, value);
    table.append(tr);
  });
  return table;
}

function factRows(agent, line) {
  if (agent === "Scope") {
    if (line.includes("comments in this slice")) {
      const count = line.match(/^([\d,]+)/);
      return [{ label: "Comments", value: count ? count[1] : line, title: line }];
    }
    return line.replace(/\.$/, "").split(", ").map((part) => {
      const match = part.trim().match(/^([\d,]+)\s+(.+)$/);
      if (!match) return { label: part.trim(), value: "", title: line };
      const name = match[2].replace("short reasons", "Short").replace("position-only", "Position-only");
      return { label: name.charAt(0).toUpperCase() + name.slice(1), value: match[1], title: line };
    });
  }
  if (agent === "Stance") {
    const yes = line.match(/(\d+%) say yes \(([\d,]+)\)/);
    const no = line.match(/([\d,]+) say no/);
    const mixed = line.match(/([\d,]+) are mixed/);
    const unsure = line.match(/([\d,]+) are unsure/);
    const clear = line.match(/clear \(([\d,]+) comments\)/);
    const rows = [];
    if (clear) rows.push({ label: "Clear", value: clear[1], title: line });
    if (yes) rows.push({ label: "Yes", value: `${yes[2]} · ${yes[1]}`, title: line });
    if (no) rows.push({ label: "No", value: no[1], title: line });
    if (mixed) rows.push({ label: "Mixed", value: mixed[1], title: line });
    if (unsure) rows.push({ label: "Unsure", value: unsure[1], title: line });
    if (rows.length) return rows;
  }
  if (agent === "Reasons") {
    const match = line.match(/^(.+?): ([\d,]+) explanations \((\d+)% of explanations\), plus ([\d,]+) short labels\.$/);
    if (match) return [{ label: match[1], value: `${match[2]} · ${match[3]}%`, title: line }];
  }
  return [{ label: line, value: "", title: line }];
}

function dashboardPanel(dashboard) {
  const panel = el("section", "dashboard");
  panel.setAttribute("aria-label", dashboard.title || "Counts");
  panel.append(el("h3", "", dashboard.title || "Counts"));
  if (dashboard.note) panel.append(el("p", "dash-note", dashboard.note));
  if (dashboard.kind === "table") panel.append(dashboardTable(dashboard));
  else panel.append(dashboardBars(dashboard));
  return panel;
}

function dashboardBars(dashboard) {
  const rows = dashboard.rows || [];
  const max = Math.max(...rows.map((row) => Number(row.value) || 0), 1);
  const list = el("ul", "bars");
  rows.forEach((row) => {
    const item = el("li", "");
    item.append(el("span", "bar-label", row.label));
    const track = el("span", "bar-track");
    const fill = el("span", row.lead ? "bar-fill is-lead" : "bar-fill");
    const width = Math.round(((Number(row.value) || 0) / max) * 100);
    fill.style.width = `${width}%`;
    track.append(fill);
    item.append(track);
    item.append(el("span", "bar-value", row.text || String(row.value)));
    list.append(item);
  });
  return list;
}

function dashboardTable(dashboard) {
  const table = document.createElement("table");
  table.className = "dash-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  headRow.append(document.createElement("th"));
  (dashboard.columns || []).forEach((column) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = column;
    headRow.append(cell);
  });
  head.append(headRow);
  const body = document.createElement("tbody");
  (dashboard.rows || []).forEach((row) => {
    const line = document.createElement("tr");
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = row.label;
    line.append(label);
    (row.values || []).forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      line.append(cell);
    });
    body.append(line);
  });
  table.append(head, body);
  return table;
}

function accuracyPanel(accuracy) {
  const panel = el("section", "accuracy");
  const title = accuracy.ok ? "Pass" : "Check failed";
  panel.append(el("p", "accuracy-title", `Accuracy · ${title} · ${accuracy.source}`));
  if (accuracy.note) panel.append(el("p", "accuracy-note", accuracy.note));
  const list = el("ul", "");
  accuracy.checks.forEach((check) => {
    const item = el("li", check.ok ? "ok" : "bad", `${check.ok ? "Pass" : "Fail"} · ${check.label}. ${check.detail}`);
    list.append(item);
  });
  panel.append(list);
  return panel;
}

async function loadLibrary() {
  const response = await fetch("/api/library");
  const payload = await response.json();
  libraryName = payload.name;
  latestModel = payload.model;
  renderLibrary(payload);
  renderModel(payload.model, !modelSynced);
  modelSynced = true;
}

function renderLibrary(payload) {
  const card = document.getElementById("file-card");
  card.replaceChildren();
  card.append(el("h3", "", payload.name));
  card.append(el("p", "meta", `${payload.n.toLocaleString()} comments · ${payload.question}`));
  const counts = el("div", "counts");
  Object.entries(payload.bucket_labels).forEach(([key, label]) => {
    counts.append(el("span", "", `${label} ${(payload.buckets[key] || 0).toLocaleString()}`));
  });
  card.append(counts);
  const preview = el("div", "preview");
  payload.preview.forEach((row) => {
    const item = document.createElement("article");
    item.append(el("div", "meta", `${row.bucket_label} · ${row.year || "year not recorded"} · ${row.college} · ID ${row.id}`));
    item.append(el("p", "", row.text));
    preview.append(item);
  });
  card.append(preview);
  sideStatus();
  applyHint();
}

function renderModel(model, syncChat) {
  document.getElementById("base-url").value = model.base_url;
  document.getElementById("model-name").value = model.model;
  document.getElementById("api-key").value = "";
  document.getElementById("api-key").placeholder = model.has_key ? "Key saved — paste a new one to replace it" : "sk-…";
  if (syncChat) setChatModel(model.model);
}

function setChatModel(name) {
  if (!name) return;
  if (![...chatModel.options].some((option) => option.value === name)) {
    chatModel.add(new Option(name, name));
  }
  chatModel.value = name;
}

function applyHint() {
  if (!latestModel.has_key) {
    hint.textContent = "Answers use the filtered counts until an LLM key is saved in Library.";
    return;
  }
  hint.textContent = listError ? "Live model list unavailable. Showing the saved names." : "";
}

function sideStatus() {
  document.getElementById("side-status").textContent = latestModel.has_key
    ? `${libraryName} · ${latestModel.model}`
    : `${libraryName} · add an LLM key when you want generated summaries`;
}

async function loadModels() {
  const payload = await fetch("/api/models").then((item) => item.json());
  listError = payload.error || "";
  modelNames = payload.models || [];
  const current = chatModel.value || payload.model;
  chatModel.replaceChildren();
  modelNames.forEach((name) => chatModel.add(new Option(name, name)));
  setChatModel(current || payload.model);
  applyHint();
}

function formatWhen(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

async function loadHistory() {
  const payload = await fetch("/api/chats").then((item) => item.json());
  const list = document.getElementById("history-list");
  list.replaceChildren();
  const chats = payload.chats || [];
  if (!chats.length) {
    list.append(el("p", "history-empty", "No saved chats yet."));
    return;
  }
  chats.forEach((chat) => {
    const row = el("div", "history-row");
    const button = el("button", chat.id === currentId ? "history-item is-on" : "history-item");
    button.type = "button";
    button.append(el("span", "history-title", chat.title));
    const meta = [chat.model, formatWhen(chat.updated)].filter(Boolean).join(" · ");
    if (meta) button.append(el("span", "history-meta", meta));
    button.addEventListener("click", () => openChat(chat.id));
    const remove = el("button", "history-delete");
    remove.type = "button";
    remove.setAttribute("aria-label", `Delete ${chat.title}`);
    remove.append(icon("M6 6l12 12M18 6L6 18"));
    remove.addEventListener("click", () => deleteChat(chat));
    row.append(button, remove);
    list.append(row);
  });
}

function icon(path) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
  node.setAttribute("d", path);
  svg.append(node);
  return svg;
}

async function openChat(id) {
  viewToken += 1;
  const response = await fetch(`/api/chats?id=${encodeURIComponent(id)}`);
  const chat = await response.json();
  if (!response.ok) return;
  currentId = chat.id;
  messages.length = 0;
  thread.querySelectorAll(".turn").forEach((node) => node.remove());
  const turns = chat.messages || [];
  empty.hidden = turns.length > 0;
  starters.hidden = turns.length > 0;
  turns.forEach((turn) => {
    messages.push(turn);
    if (turn.role === "user") addTurn("user", turn.content);
    else addTurn("assistant", turn.content, turn.quotes, turn.accuracy, turn.findings, turn.dashboard, turn.model, turn.source);
  });
  if (chat.model) setChatModel(chat.model);
  syncFrame();
  setView("chat");
  loadHistory();
  message.focus();
}

async function deleteChat(chat) {
  if (!window.confirm(`Delete “${chat.title}”?`)) return;
  const response = await fetch("/api/chats", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "delete", id: chat.id }),
  });
  if (!response.ok) return;
  if (currentId === chat.id) {
    viewToken += 1;
    currentId = null;
    messages.length = 0;
    thread.querySelectorAll(".turn").forEach((node) => node.remove());
    empty.hidden = false;
    starters.hidden = false;
    syncFrame();
  }
  loadHistory();
}

async function loadEvaluation() {
  const [catalog, models] = await Promise.all([
    fetch("/api/evals").then((item) => item.json()),
    fetch("/api/models").then((item) => item.json()),
  ]);
  evalCatalog = catalog;
  modelNames = models.models || modelNames;
  listError = models.error || "";
  renderEvalIntro(catalog);
  if (!evalRunning) fillEvalModels();
  renderSavedRuns(catalog.runs || []);
  applyHint();
}

function renderEvalIntro(catalog) {
  const scorers = document.getElementById("eval-scorers");
  const questions = document.getElementById("eval-questions");
  if (!scorers.childElementCount) {
    (catalog.scorers || []).forEach((scorer) => {
      scorers.append(el("li", "", `${scorer.label}. ${scorer.detail}`));
    });
  }
  if (!questions.childElementCount) {
    (catalog.scenarios || []).forEach((scenario) => questions.append(el("li", "", scenario.input)));
  }
}

function fillEvalModels() {
  const box = document.getElementById("eval-model-list");
  const previously = new Set([...box.querySelectorAll("input:checked")].map((input) => input.value));
  const first = box.childElementCount === 0;
  box.replaceChildren();
  box.append(modelChoice("Filtered counts", false, first || previously.has("Filtered counts"), false));
  const current = chatModel.value || latestModel.model;
  modelNames.forEach((name) => {
    const checked = latestModel.has_key && (first ? name === current : previously.has(name));
    box.append(modelChoice(name, true, checked, !latestModel.has_key));
  });
}

function modelChoice(name, useModel, checked, disabled) {
  const label = el("label", "check");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.value = name;
  input.dataset.useModel = useModel ? "1" : "0";
  input.checked = checked && !disabled;
  input.disabled = disabled;
  label.append(input, document.createTextNode(name));
  return label;
}

document.getElementById("eval-form").addEventListener("submit", (event) => {
  event.preventDefault();
  runEvaluation();
});

async function runEvaluation() {
  if (evalRunning) return;
  const selected = [...document.querySelectorAll("#eval-model-list input:checked")].map((input) => ({
    name: input.value,
    use_model: input.dataset.useModel === "1",
  }));
  const status = document.getElementById("eval-status");
  if (!selected.length) {
    status.textContent = "Choose at least one model.";
    return;
  }
  evalRunning = true;
  document.getElementById("eval-run").disabled = true;
  evalSamples = [];
  evalModels = selected.map((item) => item.name);
  renderEvalTable();
  try {
    const started = await postEval({ action: "start", models: selected });
    const scenarios = evalCatalog.scenarios || [];
    const total = scenarios.length * selected.length;
    let index = 0;
    for (const model of selected) {
      for (const scenario of scenarios) {
        index += 1;
        status.textContent = `${index} of ${total} · ${model.name}`;
        const payload = await postEval({
          action: "sample",
          id: started.id,
          scenario: scenario.id,
          model: model.name,
          use_model: model.use_model,
        });
        evalSamples.push(payload.sample);
        renderEvalTable();
      }
    }
    status.textContent = "Evaluation saved.";
    const catalog = await fetch("/api/evals").then((item) => item.json());
    evalCatalog = catalog;
    renderSavedRuns(catalog.runs || []);
  } catch (error) {
    status.textContent = error.message || "The evaluation stopped.";
    const catalog = await fetch("/api/evals").then((item) => item.json());
    renderSavedRuns(catalog.runs || []);
  } finally {
    evalRunning = false;
    document.getElementById("eval-run").disabled = false;
  }
}

async function postEval(body) {
  const response = await fetch("/api/evals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "The evaluation stopped.");
  return payload;
}

function renderEvalTable() {
  const host = document.getElementById("eval-results");
  const previous = document.getElementById("eval-detail");
  const openId = previous && previous.dataset.sampleId;
  host.replaceChildren();
  if (!evalModels.length) return;
  const scenarios = (evalCatalog && evalCatalog.scenarios) || [];
  const metrics = evalModels.map((name) => {
    const group = evalSamples.filter((sample) => sample.output && sample.output.model === name);
    const correct = group.filter((sample) => sample.ok).length;
    return `${name} ${correct}/${scenarios.length}`;
  }).join(" · ");
  host.append(el("p", "eval-metrics", metrics));
  const scroll = el("div", "eval-scroll");
  const table = document.createElement("table");
  table.className = "dash-table eval-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  const corner = document.createElement("th");
  corner.textContent = "Question";
  headRow.append(corner);
  evalModels.forEach((name) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = name;
    headRow.append(cell);
  });
  head.append(headRow);
  const body = document.createElement("tbody");
  scenarios.forEach((scenario) => {
    const line = document.createElement("tr");
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = scenario.input;
    line.append(label);
    evalModels.forEach((name) => {
      const cell = document.createElement("td");
      const sample = evalSamples.find((item) => item.metadata && item.metadata.scenario === scenario.id && item.output && item.output.model === name);
      if (!sample) {
        cell.textContent = "—";
      } else {
        const button = el("button", sample.ok ? "score-cell pass" : "score-cell fail", sample.ok ? "Pass" : "Fail");
        button.type = "button";
        button.addEventListener("click", () => showSample(sample));
        cell.append(button);
      }
      line.append(cell);
    });
    body.append(line);
  });
  table.append(head, body);
  scroll.append(table);
  const detail = el("div", "eval-detail");
  detail.id = "eval-detail";
  host.append(scroll, detail);
  if (openId) {
    const sample = evalSamples.find((item) => item.id === openId);
    if (sample) showSample(sample);
  }
}

function showSample(sample) {
  const detail = document.getElementById("eval-detail");
  if (!detail) return;
  detail.dataset.sampleId = sample.id;
  detail.replaceChildren();
  detail.append(el("h3", "", sample.output.model));
  detail.append(el("p", "eval-target", `Target · ${sample.target}`));
  detail.append(el("p", "", sample.output.completion));
  const list = el("ul", "");
  Object.entries(sample.scores || {}).forEach(([name, score]) => {
    const ok = score.value === "C";
    const label = name.charAt(0).toUpperCase() + name.slice(1);
    list.append(el("li", ok ? "ok" : "bad", `${ok ? "Pass" : "Fail"} · ${label}. ${score.explanation}`));
  });
  detail.append(list);
  if (sample.error) detail.append(el("p", "accuracy-note", sample.error));
}

function renderSavedRuns(runs) {
  const host = document.getElementById("eval-saved");
  host.replaceChildren();
  if (!runs.length) {
    host.append(el("p", "lede", "No evaluation is saved yet."));
    return;
  }
  runs.forEach((run) => {
    const button = el("button", "saved-run");
    button.type = "button";
    button.append(el("span", "history-title", (run.models || []).join(", ") || "Evaluation"));
    const scores = run.results && run.results.by_model
      ? Object.entries(run.results.by_model).map(([name, item]) => `${name} ${item.correct}/${item.n}`).join(" · ")
      : run.status;
    button.append(el("span", "history-meta", [formatWhen(run.created), scores].filter(Boolean).join(" · ")));
    button.addEventListener("click", () => openRun(run.id));
    host.append(button);
  });
}

async function openRun(id) {
  const response = await fetch(`/api/evals?id=${encodeURIComponent(id)}`);
  const run = await response.json();
  if (!response.ok) {
    document.getElementById("eval-status").textContent = run.error || "That evaluation is not saved.";
    return;
  }
  evalSamples = run.samples || [];
  evalModels = (run.eval && run.eval.model) || [];
  renderEvalTable();
  document.getElementById("eval-status").textContent = run.status === "success" ? "Saved run." : "This run is still incomplete.";
  document.getElementById("eval-results").scrollIntoView({ block: "nearest" });
}

const fileInput = document.getElementById("file");
const drop = document.getElementById("drop");

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) importFile(fileInput.files[0]);
});

["dragover", "dragleave", "drop"].forEach((name) => {
  drop.addEventListener(name, (event) => {
    event.preventDefault();
    drop.classList.toggle("is-over", name === "dragover");
    if (name === "drop" && event.dataTransfer.files[0]) importFile(event.dataTransfer.files[0]);
  });
});

async function importFile(file) {
  const status = document.getElementById("import-status");
  status.textContent = `Reading ${file.name}…`;
  const csv = await file.text();
  const response = await fetch("/api/library", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: file.name, csv }),
  });
  const payload = await response.json();
  if (!response.ok) {
    status.textContent = payload.error || "That file could not be imported.";
    return;
  }
  status.textContent = `${file.name} is the file chat will use.`;
  libraryName = payload.name;
  latestModel = payload.model;
  renderLibrary(payload);
  renderModel(payload.model, false);
}

document.getElementById("settings").addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveSettings({
    api_key: document.getElementById("api-key").value,
    base_url: document.getElementById("base-url").value,
    model: document.getElementById("model-name").value,
  });
});

document.getElementById("clear-key").addEventListener("click", () => saveSettings({ clear_key: true }));

async function saveSettings(body, options) {
  const silent = options && options.silent;
  const status = document.getElementById("settings-status");
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  latestModel = { ...latestModel, ...payload };
  if (!silent) {
    status.textContent = payload.has_key ? "LLM key saved." : "LLM key removed. Chat will use the filtered counts.";
    document.getElementById("api-key").value = "";
    renderModel(payload, false);
  } else {
    document.getElementById("model-name").value = payload.model;
  }
  setChatModel(payload.model);
  const library = await fetch("/api/library").then((item) => item.json());
  libraryName = library.name;
  latestModel = library.model;
  sideStatus();
  applyHint();
  if (!silent) loadModels();
}

function setGreeting() {
  const hour = new Date().getHours();
  const part = hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
  const greeting = document.getElementById("greeting");
  if (greeting) greeting.textContent = `Good ${part}`;
}

setGreeting();

loadLibrary().then(loadModels).then(loadHistory).catch(() => {
  hint.textContent = "The page could not finish loading. Check that the server is running.";
});
