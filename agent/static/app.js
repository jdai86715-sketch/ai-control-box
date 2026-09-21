const conversation = document.getElementById('conversation');
const input = document.getElementById('text');
const form = document.getElementById('chat');
const send = document.getElementById('send');

function createPendingTurn(text) {
  const turn = document.createElement('article');
  turn.innerHTML = `<p class="query">${escapeHtml(text)}</p>`;
  const loading = document.createElement('div');
  loading.className = 'loading';
  loading.setAttribute('aria-label', '正在处理');
  loading.innerHTML = '<i></i><i></i><i></i>';
  turn.appendChild(loading);
  conversation.querySelector('.empty')?.remove();
  conversation.appendChild(turn);
  scrollConversation();
  return {turn, loading};
}

async function playTurn(pending, data) {
  pending.loading.remove();
  const {turn} = pending;
  const trace = buildTrace(data);
  if (trace) {
    turn.appendChild(trace.details);
    for (const line of trace.lines) await streamText(line, line.dataset.value);
    await sleep(140);
    await collapseTrace(trace.details);
  }
  if (data.calls?.length) {
    const calls = document.createElement('pre');
    turn.appendChild(calls);
    await streamText(calls, JSON.stringify(data.calls, null, 2));
  }
  for (const result of data.results || []) {
    if (result.event === 'tools.list') {
      const table = toolTable(result.data.tools || []);
      table.classList.add('stream-item');
      turn.appendChild(table);
      await reveal(table);
      continue;
    }
    const message = document.createElement('p');
    message.className = `${result.ok ? 'result' : 'error'} stream-item`;
    turn.appendChild(message);
    await streamText(message, result.message);
  }
  if (!data.calls?.length && !data.results?.length) {
    const message = document.createElement('p');
    message.className = 'error stream-item';
    turn.appendChild(message);
    await streamText(message, '没有匹配的工具。');
  }
  if (Number.isFinite(data.stats?.decode_tps)) {
    const stats = document.createElement('p');
    stats.className = 'stats stream-item';
    stats.textContent = `${data.stats.elapsed_seconds.toFixed(2)}s · ${Math.round(data.stats.decode_tps)} tok/s`;
    turn.appendChild(stats);
    await reveal(stats);
  }
  scrollConversation();
}

function buildTrace(data) {
  const trace = data.trace || [];
  const context = data.context;
  if (!trace.length && !context) return null;

  const details = document.createElement('details');
  details.className = 'trace';
  details.open = true;
  const summary = document.createElement('summary');
  summary.textContent = 'Reasoning & context';
  details.appendChild(summary);
  const body = document.createElement('div');
  body.className = 'trace-body';
  const content = document.createElement('div');
  content.className = 'trace-content';
  const lines = [];

  for (const entry of trace) {
    if (!entry.reasoning) continue;
    const line = document.createElement('p');
    line.className = 'trace-line';
    line.dataset.value = `${entry.phase}: ${entry.reasoning}`;
    content.appendChild(line);
    lines.push(line);
  }
  if (context) {
    const schemas = document.createElement('p');
    schemas.className = 'trace-line';
    schemas.dataset.value = `Context: ${context.declared_tool_schemas} tool schemas declared · Needle retrieves up to ${context.retrieval_limit} candidates`;
    content.appendChild(schemas);
    lines.push(schemas);
    const feedback = document.createElement('p');
    feedback.className = 'trace-line';
    feedback.dataset.value = `Tool-result feedback: ${context.feedback_steps} step${context.feedback_steps === 1 ? '' : 's'}`;
    content.appendChild(feedback);
    lines.push(feedback);
  }
  if (!lines.length) {
    const unavailable = document.createElement('p');
    unavailable.className = 'trace-line';
    unavailable.dataset.value = 'Needle returned no reasoning trace for this turn.';
    content.appendChild(unavailable);
    lines.push(unavailable);
  }
  body.appendChild(content);
  details.appendChild(body);
  return {details, lines};
}

async function streamText(element, text) {
  const value = String(text || '');
  element.classList.add('is-visible');
  const frames = Math.max(1, Math.min(22, Math.ceil(value.length / 8)));
  const chunk = Math.max(1, Math.ceil(value.length / frames));
  for (let index = 0; index < value.length; index += chunk) {
    element.textContent = value.slice(0, index + chunk);
    scrollConversation();
    await sleep(12);
  }
}

function reveal(element) {
  return new Promise(resolve => {
    requestAnimationFrame(() => {
      element.classList.add('is-visible');
      setTimeout(resolve, 160);
    });
  });
}

function collapseTrace(details) {
  return new Promise(resolve => {
    details.classList.add('is-collapsing');
    setTimeout(() => {
      details.open = false;
      details.classList.remove('is-collapsing');
      resolve();
    }, 220);
  });
}

function sleep(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

function scrollConversation() {
  conversation.scrollTop = conversation.scrollHeight;
}

function toolTable(tools) {
  const table = document.createElement('table');
  table.className = 'tool-table';
  table.innerHTML = '<thead><tr><th>Tool</th><th>Description</th></tr></thead>';
  const body = document.createElement('tbody');
  for (const tool of tools) {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${escapeHtml(tool.name)}</td><td>${escapeHtml(tool.description)}</td>`;
    body.appendChild(row);
  }
  table.appendChild(body);
  return table;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  const pending = createPendingTurn(text);
  input.disabled = send.disabled = true;
  input.value = '';
  try {
    const response = await fetch('/api/chat', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '请求失败');
    await playTurn(pending, data);
  } catch (error) {
    await playTurn(pending, {calls: [], results: [{ok: false, message: error.message}]});
  } finally {
    input.disabled = send.disabled = false;
    input.focus();
  }
});

document.getElementById('reset').addEventListener('click', async () => {
  await fetch('/api/reset', {method: 'POST'});
  conversation.innerHTML = '<p class="empty">输入指令</p>';
  input.focus();
});

const dialog = document.getElementById('settings-dialog');
const settingsForm = document.getElementById('settings-form');
const settingsTools = document.getElementById('settings-tools');
const pluginFolder = document.getElementById('plugin-folder');
const pluginMessage = document.getElementById('plugin-message');
let toolsTimer;
document.getElementById('settings').addEventListener('click', async () => {
  const [response, toolsResponse, modelResponse] = await Promise.all([fetch('/api/settings'), fetch('/api/tools'), fetch('/api/model-settings')]);
  const [settings, tools, model] = await Promise.all([response.json(), toolsResponse.json(), modelResponse.json()]);
  const location = settings.location;
  document.getElementById('city').value = location.city;
  document.getElementById('latitude').value = location.latitude;
  document.getElementById('longitude').value = location.longitude;
  document.getElementById('active-model').value = model.active_model;
  document.getElementById('llama-server-url').value = model.qwen.llama_server_url;
  document.getElementById('embedding-server-url').value = model.qwen.embedding_server_url;
  renderSettingsTools(tools);
  dialog.showModal();
  clearInterval(toolsTimer);
  toolsTimer = setInterval(loadSettingsTools, 1500);
});

document.getElementById('close-settings').addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => clearInterval(toolsTimer));
settingsForm.addEventListener('submit', async event => {
  event.preventDefault();
  const location = {
    city: document.getElementById('city').value,
    latitude: document.getElementById('latitude').value,
    longitude: document.getElementById('longitude').value,
  };
  const response = await fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({location})});
  const model = {active_model: document.getElementById('active-model').value, qwen: {llama_server_url: document.getElementById('llama-server-url').value, embedding_server_url: document.getElementById('embedding-server-url').value}};
  const modelResponse = await fetch('/api/model-settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(model)});
  if (!response.ok || !modelResponse.ok) return;
  dialog.close();
});

async function loadSettingsTools() {
  if (!dialog.open) return;
  const response = await fetch('/api/tools');
  if (response.ok) renderSettingsTools(await response.json());
}

function renderSettingsTools(data) {
  settingsTools.replaceChildren();
  for (const tool of data.tools || []) {
    const row = document.createElement('div');
    row.className = 'settings-tool';
    const name = document.createElement('span');
    name.textContent = tool.name;
    const description = document.createElement('small');
    description.textContent = String(tool.description_zh).replace(/[。.]$/, '');
    row.append(name, description);
    settingsTools.appendChild(row);
  }
  for (const error of data.errors || []) {
    const row = document.createElement('p');
    row.className = 'plugin-error';
    row.textContent = `${error.plugin}: ${error.message}`;
    settingsTools.appendChild(row);
  }
}

pluginFolder.addEventListener('change', async () => {
  const selected = [...pluginFolder.files];
  if (!selected.length) return;
  pluginMessage.textContent = '正在安装…';
  pluginFolder.disabled = true;
  try {
    const files = await Promise.all(selected.map(async file => ({path: file.webkitRelativePath || file.name, content: await file.text()})));
    const response = await fetch('/api/plugins/install', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({files})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '安装失败');
    renderSettingsTools(data.tools);
    pluginMessage.textContent = `已安装 ${data.plugin_id}`;
  } catch (error) {
    pluginMessage.textContent = error.message;
  } finally {
    pluginFolder.value = '';
    pluginFolder.disabled = false;
  }
});
