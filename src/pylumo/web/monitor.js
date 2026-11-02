"use strict";
const $ = (id) => document.getElementById(id);
let apiKey = sessionStorage.getItem("lumo.monitor.key") || "";
let records = [];
let selected = null;

const secs = (n) => (typeof n === "number" ? n.toFixed(2) + " s" : "—");
const rate = (n) => (typeof n === "number" ? n.toFixed(1) : "—");
const pct = (n) => (typeof n === "number" ? n.toFixed(1) + "%" : "—");

async function api(path) {
  const headers = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
  const response = await fetch(path, { cache: "no-store", headers });
  if (response.status === 401) {
    $("auth").style.display = "block";
    throw new Error("Invalid API key.");
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function notice(message) {
  const el = $("error");
  el.style.display = message ? "block" : "none";
  el.textContent = message || "";
}

function showDetail() {
  const r = records.find((x) => x.id === selected);
  if (!r) return;
  const t = r.timings || {};
  const u = r.usage || {};
  $("detail").innerHTML =
    `<b>${r.id}</b><div class="small">${r.model} · POST ${r.path} · ${r.state}</div>` +
    `<div class="facts">` +
    `<div class="fact"><span class="label">Prompt</span><b>${u.prompt_tokens ?? "—"}</b></div>` +
    `<div class="fact"><span class="label">Completion</span><b>${u.completion_tokens ?? "—"}</b></div>` +
    `<div class="fact"><span class="label">First token</span><b>${secs(t.ttft_s)}</b></div>` +
    `<div class="fact"><span class="label">Wall-clock</span><b>${secs(t.wall_s)}</b></div>` +
    `<div class="fact"><span class="label">Decode</span><b>${rate(t.decode_tokens_s)} t/s</b></div>` +
    `<div class="fact"><span class="label">Prefill</span><b>${rate(t.prefill_tokens_s)} t/s</b></div>` +
    `</div>`;
}

function list() {
  const box = $("requests");
  box.replaceChildren();
  if (!records.length) {
    const empty = document.createElement("div");
    empty.className = "small";
    empty.style.padding = "14px";
    empty.textContent = "No requests yet. API calls will appear here automatically.";
    box.append(empty);
    return;
  }
  for (const r of records) {
    const b = document.createElement("button");
    b.className = "request" + (r.id === selected ? " selected" : "");
    const time = new Date(r.started_at).toLocaleTimeString();
    const speed = rate(r.timings?.decode_tokens_s);
    b.innerHTML =
      `<span>${time} · ${r.model}</span>` +
      `<span class="tag ${r.state}">${r.state}</span>` +
      `<div class="small">${r.id} · ${secs(r.timings?.wall_s)} · ${speed} tokens/s</div>`;
    b.onclick = () => { selected = r.id; list(); showDetail(); };
    box.append(b);
  }
}

async function refresh() {
  try {
    const [status, history] = await Promise.all([
      api("/api/status"),
      api("/api/requests"),
    ]);
    records = history.requests;
    notice("");
    const models = status.models || [];
    const activeModel = records[0]?.model ?? null;
    const mbox = $("model");
    mbox.replaceChildren();
    models.forEach((m, i) => {
      if (i) mbox.append(document.createTextNode(" · "));
      const s = document.createElement("span");
      s.textContent = m;
      if (m === activeModel) s.className = "active";
      mbox.append(s);
    });
    if (!models.length) mbox.textContent = "—";
    $("inflight").textContent = `${status.in_flight} in flight`;
    $("model-sub").textContent = status.model;
    $("count").textContent = status.requests;
    const last = status.last;
    $("wall").textContent = secs(last?.timings?.wall_s);
    $("speed").textContent = `${rate(last?.timings?.decode_tokens_s)} t/s`;
    $("prefill").textContent = `${rate(last?.timings?.prefill_tokens_s)} t/s`;
    const s = status.system || {};
    $("cpu").textContent = pct(s.cpu_percent);
    $("mem").textContent = pct(s.memory_percent);
    $("gpu").textContent = pct(s.gpu_percent);
    $("gpu-note").textContent =
      s.gpu_percent == null
        ? "Needs the privileged sampler"
        : `Updated ${new Date(s.gpu_updated_at * 1000).toLocaleTimeString()}`;
    $("updated").textContent = `Live · updated ${new Date().toLocaleTimeString()}`;
    list();
    showDetail();
  } catch (error) {
    notice(error.message);
    $("updated").textContent = "Disconnected · retrying";
  }
}

$("auth").onsubmit = (event) => {
  event.preventDefault();
  apiKey = $("apikey").value.trim();
  sessionStorage.setItem("lumo.monitor.key", apiKey);
  $("auth").style.display = "none";
  refresh();
};

refresh();
setInterval(refresh, 2000);
