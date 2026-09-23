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

function createLiveTurn(pending, context) {
  pending.loading.remove();
  const details = document.createElement('details');
  details.className = 'trace';
  details.open = true;
  const summary = document.createElement('summary');
  summary.textContent = 'Reasoning & context';
  const body = document.createElement('div');
  body.className = 'trace-body';
  const trace = document.createElement('div');
  trace.className = 'trace-content';
  const contextLine = document.createElement('p');
  contextLine.className = 'trace-line';
  contextLine.textContent = `${context.model_kind === 'qwen' ? 'Qwen native tools' : 'Needle'} · ${context.declared_tool_schemas} dynamic tools · up to ${context.max_steps} steps`;
  trace.appendChild(contextLine);
  body.appendChild(trace);
  details.append(summary, body);
  pending.turn.appendChild(details);
  const reply = document.createElement('p');
  reply.className = 'result';
  pending.turn.appendChild(reply);
  return {turn: pending.turn, details, trace, reply, draft: ''};
}

function appendTrace(state, value) {
  const line = document.createElement('p');
  line.className = 'trace-line';
  line.textContent = value;
  state.trace.appendChild(line);
  scrollConversation();
}

function moveDraftToTrace(state) {
  if (!state.draft) return;
  appendTrace(state, `Model: ${state.draft}`);
  state.reply.remove();
  state.reply = document.createElement('p');
  state.reply.className = 'result';
  state.turn.appendChild(state.reply);
  state.draft = '';
}

function appendToolResult(state, result) {
  if (result.event === 'tools.list') {
    state.turn.appendChild(toolTable(result.data.tools || []));
    return;
  }
  const message = document.createElement('p');
  message.className = result.ok ? 'result' : 'error';
  message.textContent = result.message;
  state.turn.appendChild(message);
}

function handleAgentEvent(state, event) {
  if (event.type === 'text_delta') {
    state.draft += event.text;
    state.reply.textContent += event.text;
  } else if (event.type === 'tool_call') {
    moveDraftToTrace(state);
    appendTrace(state, `Step ${event.step} · ${event.call.name}(${JSON.stringify(event.call.arguments)})`);
  } else if (event.type === 'tool_result') {
    appendTrace(state, `Step ${event.step} · result`);
    appendToolResult(state, event.result);
  } else if (event.type === 'limit') {
    appendTrace(state, event.message);
  } else if (event.type === 'error') {
    const message = document.createElement('p');
    message.className = 'error';
    message.textContent = event.message;
    state.turn.appendChild(message);
  } else if (event.type === 'done') {
    const stats = document.createElement('p');
    stats.className = 'stats';
    stats.textContent = `${event.stats.elapsed_seconds.toFixed(2)}s · ${event.context.feedback_steps} step${event.context.feedback_steps === 1 ? '' : 's'}`;
    state.turn.appendChild(stats);
    setTimeout(() => collapseTrace(state.details), 260);
  }
  scrollConversation();
}

async function streamTurn(pending, text) {
  const response = await fetch('/api/chat/stream', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text})});
  if (!response.ok || !response.body) throw new Error('请求失败');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let state;
  while (true) {
    const {value, done} = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const type = block.match(/^event: (.+)$/m)?.[1];
      const data = block.match(/^data: (.+)$/m)?.[1];
      if (!type || !data) continue;
      const event = JSON.parse(data);
      if (event.type === 'turn_start') state = createLiveTurn(pending, event.context);
      else if (state) handleAgentEvent(state, event);
    }
    if (done) break;
  }
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
    await streamTurn(pending, text);
  } catch (error) {
    pending.loading.remove();
    const message = document.createElement('p');
    message.className = 'error';
    message.textContent = error.message;
    pending.turn.appendChild(message);
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
const modelList = document.getElementById('model-list');
const modelDownloads = document.getElementById('model-downloads');
let toolsTimer;
let modelsTimer;
let modelState;
document.getElementById('settings').addEventListener('click', async () => {
  const [response, toolsResponse, modelsResponse] = await Promise.all([fetch('/api/settings'), fetch('/api/tools'), fetch('/api/models')]);
  const [settings, tools, models] = await Promise.all([response.json(), toolsResponse.json(), modelsResponse.json()]);
  const location = settings.location;
  document.getElementById('city').value = location.city;
  document.getElementById('latitude').value = location.latitude;
  document.getElementById('longitude').value = location.longitude;
  modelState = models;
  renderModels();
  renderSettingsTools(tools);
  showSettingsTab('general');
  dialog.showModal();
  clearInterval(toolsTimer);
  clearInterval(modelsTimer);
  toolsTimer = setInterval(loadSettingsTools, 1500);
  modelsTimer = setInterval(loadModels, 800);
});

document.getElementById('close-settings').addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => { clearInterval(toolsTimer); clearInterval(modelsTimer); });
for (const tab of document.querySelectorAll('.settings-tab')) tab.addEventListener('click', () => showSettingsTab(tab.dataset.tab));

function showSettingsTab(name) {
  for (const tab of document.querySelectorAll('.settings-tab')) tab.classList.toggle('is-active', tab.dataset.tab === name);
  for (const page of document.querySelectorAll('.settings-page')) page.classList.toggle('is-active', page.dataset.page === name);
}

settingsForm.addEventListener('submit', async event => {
  event.preventDefault();
  const location = {
    city: document.getElementById('city').value,
    latitude: document.getElementById('latitude').value,
    longitude: document.getElementById('longitude').value,
  };
  const response = await fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({location})});
  if (!response.ok) return;
  dialog.close();
});

async function loadModels() {
  if (!dialog.open) return;
  const response = await fetch('/api/models');
  if (!response.ok) return;
  modelState = await response.json();
  renderModels();
}

function renderModels() {
  if (!modelState) return;
  modelList.replaceChildren();
  modelDownloads.replaceChildren();
  const needle = modelRow('Needle', modelState.active_model === 'needle' ? '已启用' : '');
  needle.addEventListener('click', () => selectModel('needle'));
  modelList.appendChild(needle);
  for (const model of modelState.models || []) {
    const state = model.installed ? (modelState.active_model === 'qwen' && modelState.selected_id === model.id ? '已启用' : '已安装') : '未安装';
    const row = modelRow(model.name, state, model.installed && modelState.active_model === 'qwen' && modelState.selected_id === model.id);
    row.addEventListener('click', () => model.installed ? selectModel('qwen', model.id) : showSettingsTab('downloads'));
    modelList.appendChild(row);

    const download = document.createElement('div');
    download.className = 'model-row';
    download.append(document.createTextNode(model.name));
    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'download-action';
    action.textContent = model.installed ? (modelState.runtime_ready ? '已安装' : '下载依赖') : model.downloading ? downloadLabel(modelState.download) : '下载';
    action.disabled = (model.installed && modelState.runtime_ready) || model.downloading || modelState.download?.state === 'downloading';
    action.addEventListener('click', () => downloadModel(model));
    download.appendChild(action);
    modelDownloads.appendChild(download);
  }
}

function modelRow(name, state, selected = false) {
  const row = document.createElement('button');
  row.type = 'button';
  row.className = `model-row${selected ? ' is-selected' : ''}`;
  const label = document.createElement('span');
  label.textContent = name;
  const status = document.createElement('span');
  status.className = 'model-state';
  status.textContent = state;
  row.append(label, status);
  return row;
}

function downloadLabel(download) {
  if (!download || !download.total) return '下载中';
  return `${Math.min(100, Math.floor((download.received || 0) / download.total * 100))}%`;
}

async function selectModel(active_model, model_id) {
  const body = {active_model, qwen: model_id ? {model_id} : {}};
  const response = await fetch('/api/model-settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (response.ok) await loadModels();
}

async function downloadModel(model) {
  const includeRuntime = !modelState.runtime_ready;
  if (includeRuntime && !confirm('使用 Qwen 需要 llama-server，是否下载依赖？')) return;
  const response = await fetch('/api/models/download', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: model.id, include_runtime: includeRuntime})});
  if (response.ok) await loadModels();
}

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
