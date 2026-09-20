const conversation = document.getElementById('conversation');
const input = document.getElementById('text');
const form = document.getElementById('chat');
const send = document.getElementById('send');

function addTurn(text, data) {
  const turn = document.createElement('article');
  turn.innerHTML = `<p class="query">${escapeHtml(text)}</p>${data.calls?.length ? `<pre>${escapeHtml(JSON.stringify(data.calls, null, 2))}</pre>` : ''}`;
  for (const result of data.results || []) {
    if (result.event === 'tools.list') {
      turn.appendChild(toolTable(result.data.tools || []));
      continue;
    }
    const message = document.createElement('p');
    message.className = result.ok ? 'result' : 'error';
    message.textContent = result.message;
    turn.appendChild(message);
  }
  if (Number.isFinite(data.stats?.decode_tps)) {
    const stats = document.createElement('p');
    stats.className = 'stats';
    stats.textContent = `${data.stats.elapsed_seconds.toFixed(2)}s · ${Math.round(data.stats.decode_tps)} tok/s`;
    turn.appendChild(stats);
  }
  if (!data.calls?.length) {
    const message = document.createElement('p');
    message.className = 'error';
    message.textContent = '没有匹配的工具。';
    turn.appendChild(message);
  }
  conversation.querySelector('.empty')?.remove();
  conversation.appendChild(turn);
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
  input.disabled = send.disabled = true;
  try {
    const response = await fetch('/api/chat', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '请求失败');
    addTurn(text, data);
    input.value = '';
  } catch (error) {
    addTurn(text, {calls: [], results: [{ok: false, message: error.message}]});
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
document.getElementById('settings').addEventListener('click', async () => {
  const response = await fetch('/api/settings');
  const settings = await response.json();
  const location = settings.location;
  document.getElementById('city').value = location.city;
  document.getElementById('latitude').value = location.latitude;
  document.getElementById('longitude').value = location.longitude;
  dialog.showModal();
});

document.getElementById('close-settings').addEventListener('click', () => dialog.close());
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
