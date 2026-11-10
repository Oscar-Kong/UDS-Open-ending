const thread = document.getElementById("thread");
const empty = document.getElementById("empty");
const starters = document.getElementById("starters");
const message = document.getElementById("message");
const send = document.getElementById("send");
const hint = document.getElementById("hint");

const messages = [];

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
  if (name === "library") loadLibrary();
}

document.querySelectorAll(".nav").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

document.getElementById("new-chat").addEventListener("click", () => {
  messages.length = 0;
  thread.querySelectorAll(".turn").forEach((node) => node.remove());
  empty.hidden = false;
  starters.hidden = false;
  setView("chat");
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

starters.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) ask(button.textContent);
});

async function ask(text) {
  const question = text.trim();
  if (!question || send.disabled) return;
  message.value = "";
  message.style.height = "auto";
  empty.hidden = true;
  starters.hidden = true;
  messages.push({ role: "user", content: question });
  addTurn("user", question);
  const pending = addTurn("assistant", "Reading the filtered comments…");
  pending.classList.add("pending");
  send.disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });
    const payload = await response.json();
    pending.remove();
    if (!response.ok) {
      addTurn("assistant", payload.error || "The question did not go through.");
      return;
    }
    messages.push({ role: "assistant", content: payload.text });
    addTurn("assistant", payload.text, payload.quotes || []);
  } catch (error) {
    pending.remove();
    addTurn("assistant", "The server did not answer. Check that it is still running.");
  } finally {
    send.disabled = false;
    message.focus();
  }
}

function addTurn(role, text, quotes) {
  const turn = el("div", `turn ${role}`);
  const bubble = el("div", "bubble", text);
  turn.append(bubble);
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
    turn.append(list);
  }
  thread.append(turn);
  thread.scrollTop = thread.scrollHeight;
  return turn;
}

async function loadLibrary() {
  const response = await fetch("/api/library");
  const payload = await response.json();
  renderLibrary(payload);
  renderModel(payload.model);
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
  document.getElementById("side-status").textContent = payload.model.has_key
    ? `${payload.name} · model connected`
    : `${payload.name} · add a model key when you want generated summaries`;
  document.getElementById("hint").textContent = payload.model.has_key
    ? "Answers are short summaries from the connected model, using the filtered comments."
    : "Answers use the filtered counts and quotations until a model key is saved in Library.";
}

function renderModel(model) {
  document.getElementById("base-url").value = model.base_url;
  document.getElementById("model-name").value = model.model;
  document.getElementById("api-key").value = "";
  document.getElementById("api-key").placeholder = model.has_key ? "Key saved — paste a new one to replace it" : "sk-…";
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
  renderLibrary(payload);
  renderModel(payload.model);
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

async function saveSettings(body) {
  const status = document.getElementById("settings-status");
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  status.textContent = payload.has_key ? "Model key saved." : "Model key removed. Chat will use the filtered counts.";
  document.getElementById("api-key").value = "";
  renderModel(payload);
  const library = await fetch("/api/library").then((item) => item.json());
  document.getElementById("side-status").textContent = payload.has_key
    ? `${library.name} · model connected`
    : `${library.name} · add a model key when you want generated summaries`;
  document.getElementById("hint").textContent = payload.has_key
    ? "Answers are short summaries from the connected model, using the filtered comments."
    : "Answers use the filtered counts and quotations until a model key is saved in Library.";
}

loadLibrary();
