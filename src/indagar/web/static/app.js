const state = {
  status: null,
  jobId: null,
  runId: null,
  run: null,
  eventSource: null,
  selectedSource: 0,
  eventKeys: new Set(),
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function showError(message) {
  const element = $("error-output");
  if (!message) {
    element.hidden = true;
    element.textContent = "";
    return;
  }
  element.hidden = false;
  element.textContent = message;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText || `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Keep the HTTP status text.
    }
    throw new Error(detail);
  }
  return response.json();
}

function badges(items, ok = false) {
  if (!items || !items.length) {
    return '<span class="badge">none</span>';
  }
  return items
    .map((item) => `<span class="badge ${ok ? "ok" : ""}">${escapeHtml(item)}</span>`)
    .join("");
}

function configRow(label, value) {
  const row = document.createElement("div");
  row.className = "config-row";
  row.innerHTML = `<span>${escapeHtml(label)}</span><span>${value}</span>`;
  return row;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function renderStatus(status) {
  state.status = status;
  const search = status.search_providers || [];
  const chip = $("status-chip");
  chip.className = "chip";
  if (!search.length) {
    chip.classList.add("warn");
    chip.textContent = "No search provider";
  } else if (!status.llm_provider) {
    chip.textContent = `${search.length} search · retrieval only`;
  } else {
    chip.textContent = `${search.length} search · ${status.llm_provider}`;
  }

  const config = $("config");
  config.innerHTML = "";
  config.append(configRow("Search", badges(search, search.length > 0)));

  if (status.llm_provider) {
    const models = Object.entries(status.llm_models || {})
      .filter(([, model]) => Boolean(model))
      .map(([role, model]) => `${role}:${model}`);
    config.append(
      configRow(
        "LLM",
        `<span class="badge ok">${escapeHtml(status.llm_provider)}</span>` +
          (models.length ? badges(models) : ""),
      ),
    );
  } else {
    config.append(configRow("LLM", '<span class="badge">not configured</span>'));
  }

  const budgets = status.budgets || {};
  config.append(
    configRow(
      "Budgets",
      `<span class="badge">${budgets.max_sources} sources</span>` +
        `<span class="badge">${budgets.max_seconds}s</span>` +
        `<span class="badge">depth ${budgets.max_depth}</span>`,
    ),
  );
}

async function loadStatus() {
  try {
    renderStatus(await fetchJson("/api/status"));
  } catch (error) {
    const chip = $("status-chip");
    chip.className = "chip bad";
    chip.textContent = "Offline";
    throw error;
  }
}

async function loadHistory() {
  const data = await fetchJson("/api/runs");
  const history = $("history");
  history.innerHTML = "";
  const items = [
    ...(data.active || []).map((job) => ({ kind: "job", ...job })),
    ...(data.resumable || []).map((state) => ({ kind: "resume", ...state })),
    ...(data.saved || []).map((run) => ({ kind: "run", ...run })),
  ];
  if (!items.length) {
    history.innerHTML = '<p class="note">No runs yet.</p>';
    return data;
  }

  for (const item of items.slice(0, 30)) {
    const button = document.createElement("button");
    button.className = "history-item";
    button.type = "button";
    const question = item.question || "Untitled run";
    const meta =
      item.kind === "job"
        ? `${item.status} · ${item.max_sources || "default"} sources`
        : item.kind === "resume"
          ? `paused · ${item.sources || 0} sources · ${item.citations || 0} citations`
          : `${item.sources || 0} sources · ${item.citations || 0} citations`;
    button.innerHTML = `<strong>${escapeHtml(question)}</strong><small>${escapeHtml(
      formatDate(item.created_at),
    )} · ${escapeHtml(meta)}</small>`;
    button.addEventListener("click", () => {
      if (item.kind === "job") {
        attachToJob(item.job_id);
      } else if (item.kind === "resume" && item.run_id) {
        resumeRun(item.run_id);
      } else if (item.run_id) {
        loadRun(item.run_id);
      }
    });
    history.append(button);
  }
  return data;
}

async function requestEstimate() {
  const question = $("question").value.trim();
  if (!question) {
    showError("Enter a question first.");
    return;
  }
  showError("");
  const params = new URLSearchParams({
    question,
    llm: String($("use-llm").checked),
    depth: $("depth").value,
    max_sources: $("max-sources").value,
  });
  try {
    const result = await fetchJson(`/api/estimate?${params.toString()}`);
    $("estimate-output").textContent = result.line;
  } catch (error) {
    showError(error.message);
  }
}

function setBusy(running) {
  $("start-button").disabled = running;
  $("estimate-button").disabled = running;
  $("cancel-button").hidden = !running;
}

function clearProgress() {
  $("progress").innerHTML = "";
  state.eventKeys.clear();
}

function clearResult() {
  state.run = null;
  state.runId = null;
  state.selectedSource = 0;
  $("result").hidden = true;
  $("exports").hidden = true;
  $("report").innerHTML = "";
  $("sources").innerHTML = "";
  $("source-detail").textContent = "Select a source to inspect it.";
  $("citations").innerHTML = "";
  $("run-details").innerHTML = "";
  $("usage").innerHTML = "";
}

function appendEvent(event) {
  const key = `${event.at || ""}|${event.type || ""}|${event.message || ""}`;
  if (state.eventKeys.has(key)) return;
  state.eventKeys.add(key);
  const progress = $("progress");
  const item = document.createElement("div");
  item.className = `event ${event.type || "status"}`;
  const time = new Date(event.at || Date.now());
  const label = (event.type || "event").replaceAll("_", " ");
  item.innerHTML =
    `<span class="event-type">${escapeHtml(label)}</span>` +
    `<span class="event-message">${escapeHtml(event.message || "")}</span>` +
    `<span class="event-time">${escapeHtml(
      Number.isNaN(time.getTime()) ? "" : time.toLocaleTimeString(),
    )}</span>`;
  progress.append(item);
  while (progress.children.length > 300) {
    progress.removeChild(progress.firstChild);
  }
}

function closeEvents() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
}

function handleEvent(event) {
  if (event.type === "completed") {
    closeEvents();
    setBusy(false);
    const runId = event.data && event.data.run_id;
    if (runId) {
      state.runId = runId;
      loadRun(runId).catch((error) => showError(error.message));
    }
    loadHistory().catch(() => {});
    return;
  }
  if (event.type === "error") {
    closeEvents();
    setBusy(false);
    $("workspace-title").textContent = "Run failed";
    showError(event.message || "The run failed.");
    loadHistory().catch(() => {});
    return;
  }
  if (event.type === "cancelled") {
    closeEvents();
    setBusy(false);
    $("workspace-title").textContent = "Run cancelled";
    loadHistory().catch(() => {});
  }
}

function attachToJob(jobId) {
  closeEvents();
  clearProgress();
  clearResult();
  showError("");
  state.jobId = jobId;
  setBusy(true);
  $("workspace-title").textContent = "Running";
  $("workspace-subtitle").textContent = "Waiting for the planner…";

  const source = new EventSource(`/api/runs/${encodeURIComponent(jobId)}/events`);
  state.eventSource = source;
  source.onmessage = (message) => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch {
      return;
    }
    appendEvent(event);
    handleEvent(event);
  };
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) {
      closeEvents();
      setBusy(false);
    }
  };
}

async function startResearch() {
  const question = $("question").value.trim();
  if (!question) {
    showError("Enter a question first.");
    return;
  }
  const body = {
    question,
    llm: $("use-llm").checked,
    depth: Number($("depth").value),
    max_sources: Number($("max-sources").value),
  };
  showError("");
  clearProgress();
  clearResult();
  setBusy(true);
  $("workspace-title").textContent = "Starting";
  $("workspace-subtitle").textContent = question;
  try {
    const job = await fetchJson("/api/runs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    state.jobId = job.job_id;
    attachToJob(job.job_id);
  } catch (error) {
    setBusy(false);
    $("workspace-title").textContent = "Ready";
    showError(error.message);
  }
}

async function resumeRun(runId) {
  showError("");
  clearProgress();
  clearResult();
  setBusy(true);
  $("workspace-title").textContent = "Resuming";
  $("workspace-subtitle").textContent = "Continuing from the saved checkpoint…";
  try {
    const job = await fetchJson(
      `/api/runs/${encodeURIComponent(runId)}/resume`,
      { method: "POST" },
    );
    state.jobId = job.job_id;
    attachToJob(job.job_id);
  } catch (error) {
    setBusy(false);
    $("workspace-title").textContent = "Ready";
    showError(error.message);
  }
}

async function cancelResearch() {
  if (!state.jobId) return;
  try {
    await fetchJson(`/api/runs/${encodeURIComponent(state.jobId)}/cancel`, {
      method: "POST",
    });
    $("workspace-title").textContent = "Stopping…";
  } catch (error) {
    showError(error.message);
  }
}

async function loadRun(runId) {
  const data = await fetchJson(`/api/runs/${encodeURIComponent(runId)}`);
  if (data.kind === "job") {
    if (data.run_id) return loadRun(data.run_id);
    throw new Error(data.error || `Job is ${data.status}`);
  }
  renderRun(data.run);
}

function renderRun(run) {
  state.run = run;
  state.runId = run.id;
  state.selectedSource = 0;
  closeEvents();
  setBusy(false);
  showError("");

  const citations = run.citations || [];
  const sources = run.sources || [];
  const reads = run.reads || [];
  const usage = run.usage || [];
  const calls = usage.reduce((sum, item) => sum + (item.calls || 0), 0);
  const inputTokens = usage.reduce((sum, item) => sum + (item.input_tokens || 0), 0);
  const outputTokens = usage.reduce((sum, item) => sum + (item.output_tokens || 0), 0);

  $("workspace-title").textContent = run.question || "Research report";
  $("workspace-subtitle").textContent = `${run.plan?.planner || "unknown"} planner · ${
    sources.length
  } sources · ${citations.length} citations`;
  $("exports").hidden = false;
  $("export-md").href = `/api/runs/${encodeURIComponent(run.id)}/export.md`;
  $("export-json").href = `/api/runs/${encodeURIComponent(run.id)}/export.json`;
  $("export-docx").href = `/api/runs/${encodeURIComponent(run.id)}/export.docx`;
  $("export-pdf").href = `/api/runs/${encodeURIComponent(run.id)}/export.pdf`;

  const summary = $("result-summary");
  summary.innerHTML = "";
  [
    ["Planner", run.plan?.planner || "—"],
    ["Sources", sources.length],
    ["Citations", citations.length],
    ["Read", reads.length],
    ["LLM calls", calls],
    ["Tokens", `${inputTokens} / ${outputTokens}`],
  ].forEach(([label, value]) => {
    const stat = document.createElement("span");
    stat.className = "stat";
    stat.innerHTML = `<strong>${escapeHtml(value)}</strong> ${escapeHtml(label)}`;
    summary.append(stat);
  });

  $("report").innerHTML = renderMarkdown(reportNarrative(run.report || ""));
  renderSources(run);
  renderCitations(run);
  renderRunDetails(run);
  renderUsage(run);
  $("result").hidden = false;
}

function reportNarrative(markdown) {
  const text = String(markdown || "");
  const cut = text.indexOf("\n## Sources");
  return cut >= 0 ? text.slice(0, cut) : text;
}

function renderRunDetails(run) {
  const container = $("run-details");
  const attempts = run.attempts || [];
  const reads = run.reads || [];

  const attemptRows = attempts
    .map(
      (attempt) =>
        `<tr><td>${escapeHtml(attempt.provider)}</td>` +
        `<td>${escapeHtml(attempt.status)}</td>` +
        `<td>${attempt.count}</td><td>${attempt.latency_ms}ms</td>` +
        `<td>${escapeHtml(attempt.error || "")}</td></tr>`,
    )
    .join("");
  const readRows = reads
    .map(
      (read) =>
        `<tr><td>${escapeHtml(read.url)}</td>` +
        `<td>${escapeHtml(read.status)}</td><td>${read.chars}</td>` +
        `<td>${read.claims}</td><td>${read.latency_ms}ms</td>` +
        `<td>${escapeHtml(read.error || "")}</td></tr>`,
    )
    .join("");

  container.innerHTML =
    "<h4>Search attempts</h4>" +
    (attempts.length
      ? '<div class="table-wrap"><table><thead><tr><th>Provider</th><th>Status</th><th>Count</th><th>Latency</th><th>Error</th></tr></thead>' +
        `<tbody>${attemptRows}</tbody></table></div>`
      : '<p class="note">No search attempts recorded.</p>') +
    "<h4>Sources read</h4>" +
    (reads.length
      ? '<div class="table-wrap"><table><thead><tr><th>URL</th><th>Status</th><th>Chars</th><th>Claims</th><th>Latency</th><th>Error</th></tr></thead>' +
        `<tbody>${readRows}</tbody></table></div>`
      : '<p class="note">No source reads recorded.</p>');
}

function renderSources(run) {
  const container = $("sources");
  const sources = run.sources || [];
  container.innerHTML = "";
  if (!sources.length) {
    container.innerHTML = '<p class="note">No sources were collected.</p>';
    return;
  }
  const citations = run.citations || [];
  sources.forEach((source, index) => {
    const count = citations.filter(
      (citation) => citation.source_url === source.url,
    ).length;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `source-card ${index === state.selectedSource ? "active" : ""}`;
    button.innerHTML =
      `<strong>${escapeHtml(source.title || source.url)}</strong>` +
      `<small>${escapeHtml(source.domain || "")} · ${escapeHtml(
        source.provider || "unknown",
      )} · ${escapeHtml(source.source_type || "web")} · ${escapeHtml(
        source.confidence || "low",
      )}${count ? ` · ${count} citations` : ""}</small>`;
    button.addEventListener("click", () => selectSource(index));
    container.append(button);
  });
  if (sources.length) selectSource(state.selectedSource);
}

function selectSource(index) {
  const run = state.run;
  if (!run || !run.sources || !run.sources[index]) return;
  state.selectedSource = index;
  const cards = $("sources").querySelectorAll(".source-card");
  cards.forEach((card, cardIndex) => {
    card.classList.toggle("active", cardIndex === index);
  });

  const source = run.sources[index];
  const citations = (run.citations || []).filter(
    (citation) => citation.source_url === source.url,
  );
  const detail = $("source-detail");
  detail.innerHTML =
    `<h4>${escapeHtml(source.title || source.url)}</h4>` +
    `<p>${escapeHtml(source.domain || "")} · ${escapeHtml(
      source.provider || "unknown",
    )} · ${escapeHtml(source.source_type || "web")} · ${escapeHtml(
      source.confidence || "low",
    )} confidence</p>` +
    `<p><a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">Open source</a></p>` +
    (source.sub_question
      ? `<p><strong>Sub-question:</strong> ${escapeHtml(source.sub_question)}</p>`
      : "") +
    (source.snippet ? `<p>${escapeHtml(source.snippet)}</p>` : "") +
    (citations.length
      ? citations
          .map(
            (citation) =>
              `<div class="citation-card"><strong>${escapeHtml(citation.id)}</strong>` +
              `<q>${escapeHtml(citation.quote)}</q>` +
              (citation.locator
                ? `<p>${escapeHtml(citation.locator)}</p>`
                : "") +
              `</div>`,
          )
          .join("")
      : '<p class="note">No extracted citations for this source.</p>');
}

function renderCitations(run) {
  const citations = run.citations || [];
  const container = $("citations");
  if (!citations.length) {
    container.innerHTML = '<p class="note">No grounded citations.</p>';
    return;
  }
  const rows = citations
    .map(
      (citation) =>
        `<tr><td>${escapeHtml(citation.id)}</td>` +
        `<td><a href="${escapeHtml(citation.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(
          citation.title || citation.source_url,
        )}</a></td>` +
        `<td>${escapeHtml(citation.source_type || "web")}</td>` +
        `<td>${escapeHtml(citation.confidence || "low")}</td>` +
        `<td>${escapeHtml(citation.quote)}</td>` +
        `<td>${escapeHtml(citation.locator || "")}</td>` +
        `<td>${escapeHtml(citation.sub_question || "")}</td></tr>`,
    )
    .join("");
  container.innerHTML =
    '<div class="table-wrap"><table><thead><tr>' +
    "<th>ID</th><th>Source</th><th>Type</th><th>Confidence</th><th>Quote</th><th>Locator</th><th>Sub-question</th>" +
    `</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderUsage(run) {
  const usage = run.usage || [];
  const container = $("usage");
  if (!usage.length) {
    container.innerHTML = '<p class="note">No LLM calls were recorded.</p>';
    return;
  }
  const rows = usage
    .map(
      (item) =>
        `<tr><td>${escapeHtml(item.provider)}</td><td>${escapeHtml(item.model)}</td>` +
        `<td>${item.calls}</td><td>${item.input_tokens}</td><td>${item.output_tokens}</td></tr>`,
    )
    .join("");
  container.innerHTML =
    '<div class="table-wrap"><table><thead><tr>' +
    "<th>Provider</th><th>Model</th><th>Calls</th><th>Input</th><th>Output</th>" +
    `</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function inlineMarkdown(value) {
  let text = escapeHtml(value);
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  text = text.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, url) => {
    const safe = /^https?:\/\//i.test(url) ? url : "#";
    return `<a href="${safe}" target="_blank" rel="noreferrer">${label}</a>`;
  });
  return text;
}

function splitRow(line) {
  let value = String(line).trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);
  const cells = [];
  let current = "";
  let escaped = false;
  for (const char of value) {
    if (escaped) {
      current += char;
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === "|") {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current.trim());
  return cells;
}

function isTableSeparator(line) {
  const cells = splitRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function renderTable(rows) {
  const header = splitRow(rows[0]);
  const body = rows.slice(2).map(splitRow);
  const head = header.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("");
  const bodyRows = body
    .map(
      (row) =>
        `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`,
    )
    .join("");
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${bodyRows}</tbody></table></div>`;
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const output = [];
  let paragraph = [];
  let list = null;
  let index = 0;

  function flushParagraph() {
    if (paragraph.length) {
      output.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  }

  function closeList() {
    if (list) {
      output.push(`</${list}>`);
      list = null;
    }
  }

  while (index < lines.length) {
    const raw = lines[index];
    const line = raw.trim();

    if (!line) {
      flushParagraph();
      closeList();
      index += 1;
      continue;
    }

    if (
      line.startsWith("|") &&
      index + 1 < lines.length &&
      isTableSeparator(lines[index + 1])
    ) {
      flushParagraph();
      closeList();
      const rows = [];
      let cursor = index;
      while (cursor < lines.length && lines[cursor].trim().startsWith("|")) {
        rows.push(lines[cursor]);
        cursor += 1;
      }
      output.push(renderTable(rows));
      index = cursor;
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      flushParagraph();
      closeList();
      const level = heading[1].length;
      output.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (line.startsWith("> ")) {
      flushParagraph();
      closeList();
      output.push(`<blockquote>${inlineMarkdown(line.slice(2))}</blockquote>`);
      index += 1;
      continue;
    }

    if (line.startsWith("- ")) {
      flushParagraph();
      if (list !== "ul") {
        closeList();
        output.push("<ul>");
        list = "ul";
      }
      output.push(`<li>${inlineMarkdown(line.slice(2))}</li>`);
      index += 1;
      continue;
    }

    const ordered = /^\d+\.\s+(.*)$/.exec(line);
    if (ordered) {
      flushParagraph();
      if (list !== "ol") {
        closeList();
        output.push("<ol>");
        list = "ol";
      }
      output.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
      index += 1;
      continue;
    }

    paragraph.push(line);
    index += 1;
  }

  flushParagraph();
  closeList();
  return output.join("\n");
}

function boot() {
  $("estimate-button").addEventListener("click", requestEstimate);
  $("start-button").addEventListener("click", startResearch);
  $("cancel-button").addEventListener("click", cancelResearch);
  $("question").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      startResearch();
    }
  });

  loadStatus().catch((error) => showError(error.message));
  loadHistory()
    .then((data) => {
      if (data?.saved?.length && !state.runId) {
        loadRun(data.saved[0].run_id).catch(() => {});
      }
    })
    .catch((error) => showError(error.message));
}

document.addEventListener("DOMContentLoaded", boot);
