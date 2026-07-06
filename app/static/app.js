// app/static/app.js
"use strict";

const $ = (id) => document.getElementById(id);

let allModels = [];       // full ModelInfo list for the current provider
let currentRunId = null;  // id of the most recently rendered run
let apiKey = "";          // UI-entered LLM key, session-only (never persisted)
const sourceKeys = {};    // UI-entered per-source keys (tavily/news), session-only

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    throw new Error("Request failed (" + res.status + "): " + url);
  }
  return res.json();
}

// ---------- Providers ----------
// Both supported providers are always selectable. The user supplies a key for
// whichever they pick (or relies on the server's .env key if left blank).
const SUPPORTED_PROVIDERS = ["openrouter", "openai"];

async function loadProviders() {
  const sel = $("provider");
  sel.innerHTML = "";
  for (const p of SUPPORTED_PROVIDERS) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    sel.appendChild(opt);
  }
  // Models are fetched from the user's API key, so wait until one is entered.
  showModelPlaceholder("Enter your API key, then click Load models");
}

// ---------- Models ----------
function modelBadge(m) {
  return m.free ? "Free" : "Paid";
}

function renderModelOptions(filterText) {
  const sel = $("model");
  const q = (filterText || "").toLowerCase();
  sel.innerHTML = "";
  const filtered = allModels.filter((m) =>
    ((m.name || m.id || "").toLowerCase()).includes(q)
  );
  if (filtered.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No models";
    sel.appendChild(opt);
    return;
  }
  for (const m of filtered) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = (m.name || m.id) + " · " + modelBadge(m);
    sel.appendChild(opt);
  }
}

function showModelPlaceholder(text) {
  allModels = [];
  const sel = $("model");
  sel.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = text;
  sel.appendChild(opt);
}

async function loadModels(provider) {
  const sel = $("model");
  if (!provider) {
    allModels = [];
    renderModelOptions("");
    return;
  }
  sel.innerHTML = "";
  const loading = document.createElement("option");
  loading.textContent = "Loading models...";
  sel.appendChild(loading);
  try {
    const url =
      "/api/models?provider=" +
      encodeURIComponent(provider) +
      (apiKey ? "&api_key=" + encodeURIComponent(apiKey) : "");
    const data = await fetchJSON(url);
    allModels = data.models || [];
    renderModelOptions($("model-filter").value);
    // Backend returns {"models": [], "error": "..."} (HTTP 200) when a
    // provider key is invalid; surface that instead of a bare "No models".
    if (data.error) {
      showError("Could not load models: " + data.error);
    }
  } catch (err) {
    allModels = [];
    renderModelOptions("");
    showError("Could not load models: " + err.message);
  }
}

// ---------- History ----------
async function loadHistory() {
  const box = $("history");
  try {
    const data = await fetchJSON("/api/history");
    const runs = data.runs || [];
    box.innerHTML = "";
    if (runs.length === 0) {
      box.innerHTML =
        '<p class="text-sm text-slate-400 p-2">No runs yet.</p>';
      return;
    }
    for (const r of runs) {
      const item = document.createElement("button");
      item.className =
        "block w-full text-left p-2 rounded hover:bg-slate-700 text-sm truncate";
      item.textContent = r.query;
      item.title = r.model + " / " + r.provider + " (" + r.status + ")";
      item.addEventListener("click", () => openRun(r.id));
      box.appendChild(item);
    }
  } catch (err) {
    box.innerHTML =
      '<p class="text-sm text-red-400 p-2">Could not load history.</p>';
  }
}

async function openRun(runId) {
  try {
    const run = await fetchJSON("/api/history/" + runId);
    currentRunId = run.id;
    resetTimeline();
    addTimelineItem("Loaded run #" + run.id);
    renderReport(run.report_markdown || "");
    wireExports(run.id);
  } catch (err) {
    showError("Could not load run: " + err.message);
  }
}

// ---------- Timeline / report / exports ----------
function resetTimeline() {
  $("timeline").innerHTML = "";
}

function addTimelineItem(text) {
  const li = document.createElement("li");
  li.className =
    "px-3 py-1 border-l-2 border-sky-500 text-sm text-slate-300";
  li.textContent = text;
  $("timeline").appendChild(li);
}

function renderReport(markdown) {
  const target = $("report");
  if (window.marked && typeof marked.parse === "function") {
    target.innerHTML = marked.parse(markdown);
  } else {
    target.textContent = markdown;
  }
}

function wireExports(runId) {
  const md = $("export-md");
  const pdf = $("export-pdf");
  if (runId == null) {
    md.classList.add("hidden");
    pdf.classList.add("hidden");
    return;
  }
  md.href = "/api/export/" + runId + "?format=md";
  pdf.href = "/api/export/" + runId + "?format=pdf";
  md.classList.remove("hidden");
  pdf.classList.remove("hidden");
}

function showError(msg) {
  addTimelineItem("Error: " + msg);
}

// ---------- Source keys (session-only; each gates its source checkbox) ----------
function wireSourceKey(name, inputId, checkboxId) {
  const input = $(inputId);
  const cb = $(checkboxId);
  input.addEventListener("input", (e) => {
    const val = e.target.value.trim();
    if (val) {
      sourceKeys[name] = val;
      cb.disabled = false;
    } else {
      delete sourceKeys[name];
      cb.disabled = true;
      cb.checked = false;
    }
  });
}

// ---------- Research streaming ----------
function selectedSources() {
  const names = ["tavily", "wikipedia", "news", "web"];
  const chosen = [];
  for (const n of names) {
    const cb = document.getElementById("src-" + n);
    if (cb && cb.checked) chosen.push(n);
  }
  return chosen;
}

function handleFrame(frame) {
  const line = frame.split("\n").find((l) => l.startsWith("data:"));
  if (!line) return;
  let event;
  try {
    event = JSON.parse(line.slice(5).trim());
  } catch (e) {
    return;
  }
  if (event.type === "node") {
    addTimelineItem(event.node + (event.detail ? " — " + event.detail : ""));
  } else if (event.type === "report") {
    currentRunId = event.run_id;
    renderReport(event.markdown || "");
    wireExports(event.run_id);
  } else if (event.type === "error") {
    showError(event.message || "Unknown error");
  } else if (event.type === "done") {
    addTimelineItem("Done.");
  }
}

async function runResearch() {
  const query = $("query").value.trim();
  if (!query) {
    resetTimeline();
    showError("Please enter a query.");
    return;
  }
  const runBtn = $("run");
  runBtn.disabled = true;
  const originalLabel = runBtn.textContent;
  runBtn.textContent = "Researching...";
  resetTimeline();
  $("report").innerHTML = "";
  wireExports(null);

  const body = {
    query: query,
    provider: $("provider").value || null,
    model: $("model").value || null,
  };
  if (apiKey) body.api_key = apiKey;
  body.source_keys = sourceKeys; // gate which sources the agent may use
  const sources = selectedSources();
  if (sources.length > 0) body.sources = sources;

  try {
    const res = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      throw new Error("Research request failed: " + res.status);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop();  // keep last (possibly partial) frame
      for (const frame of frames) {
        handleFrame(frame);
      }
    }
    if (buffer.trim()) handleFrame(buffer);
  } catch (err) {
    showError(err.message);
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = originalLabel;
    loadHistory();
  }
}

// ---------- Init ----------
function init() {
  $("provider").addEventListener("change", (e) => {
    if (apiKey) loadModels(e.target.value);
    else showModelPlaceholder("Enter your API key, then click Load models");
  });
  $("model-filter").addEventListener("input", (e) =>
    renderModelOptions(e.target.value)
  );
  $("api-key").addEventListener("input", (e) => {
    apiKey = e.target.value.trim();
  });
  // Fetch the model list from the entered key when the field loses focus / Enter.
  $("api-key").addEventListener("change", () => {
    if (apiKey) loadModels($("provider").value);
    else showModelPlaceholder("Enter your API key, then click Load models");
  });
  $("load-models").addEventListener("click", () => {
    if (apiKey) loadModels($("provider").value);
    else showError("Enter an API key first, then click Load models.");
  });
  wireSourceKey("tavily", "tavily-key", "src-tavily");
  wireSourceKey("news", "newsapi-key", "src-news");
  $("run").addEventListener("click", runResearch);
  wireExports(null);
  loadProviders();
  loadHistory();
}

document.addEventListener("DOMContentLoaded", init);
