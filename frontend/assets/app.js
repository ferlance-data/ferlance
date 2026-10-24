const state = { token: null, businessId: null, user: null, datasets: [], lastAnalytics: null, conversationId: null, page: location.hash.slice(1) || 'dashboard' };
const pages = {
  dashboard: { title: 'Business dashboard', description: 'A clear view of the records your business has accepted and the signals they support.' },
  data: { title: 'Your data', description: 'Upload, inspect, and understand the processing history behind your numbers.' },
  insights: { title: 'Business insights', description: 'Deterministic observations and fixed questions grounded in the selected dataset.' },
  profile: { title: 'Profile and access', description: 'Keep your workspace identity current and manage access when you have administrator privileges.' },
  'ask-lance': { title: 'Ask Lance', description: 'A grounded business conversation based on accepted records and calculated metrics.' },
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const cell = (tag, text) => { const element = document.createElement(tag); element.textContent = text; return element; };
const money = (value, currency = state.currency || 'GHS') => new Intl.NumberFormat(currency === 'USD' ? 'en-US' : 'en-GH', { style: 'currency', currency, currencyDisplay: 'narrowSymbol', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value));
const status = (selector, message, error = false) => { const element = $(selector); element.textContent = message; element.className = `${element.className.replace(' error', '')}${error ? ' error' : ''}`; };

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let response = await fetch(path, { ...options, credentials: 'same-origin', headers });
  if (response.status === 401 && !path.startsWith('/api/auth/')) {
    const refresh = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' });
    if (refresh.ok) { state.token = (await refresh.json()).access_token; headers.Authorization = `Bearer ${state.token}`; response = await fetch(path, { ...options, credentials: 'same-origin', headers }); }
    else { window.location.replace('/'); throw new Error('Your session has expired. Please sign in again.'); }
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'Request failed.');
  return body;
}

function renderTable(target, headers, rows) {
  target.replaceChildren();
  target.append(createTable(headers, rows));
}

function createTable(headers, rows) {
  if (!rows.length) return cell('p', 'No data for this period.');
  const table = document.createElement('table'); table.className = 'data-table';
  const head = document.createElement('tr'); headers.forEach((header) => { const heading = cell('th', header); heading.scope = 'col'; head.append(heading); });
  const thead = document.createElement('thead'); thead.append(head); const tbody = document.createElement('tbody');
  rows.forEach((row) => { const line = document.createElement('tr'); row.forEach((value) => line.append(cell('td', value))); tbody.append(line); });
  table.append(thead, tbody);
  return table;
}

function renderChart(items, valueKey = 'revenue') {
  const target = $('#trend'); target.replaceChildren();
  if (!items.length) { target.append(cell('p', 'No data for this period.')); return; }
  const max = Math.max(...items.map((item) => item[valueKey])); const chart = document.createElement('div'); chart.className = 'chart';
  items.forEach((item) => { const value = item[valueKey]; const row = document.createElement('div'); row.className = 'bar-row'; row.append(cell('span', item.period)); const track = document.createElement('div'); track.className = 'bar-track'; const bar = document.createElement('div'); bar.className = 'bar'; bar.style.width = `${max ? value / max * 100 : 0}%`; track.append(bar); row.append(track, cell('span', money(value))); chart.append(row); }); target.append(chart);
}

function renderProducts(products) {
  const target = $('#products'); target.replaceChildren();
  if (!products.available) { target.append(cell('p', products.reason)); return; }
  const ranking = $('#product-ranking').value; const items = products.rankings[ranking] || [];
  if (!items.length) { target.append(cell('p', ranking === 'profit' || ranking === 'loss' ? 'Profit rankings need cost data on every product record.' : 'No products match this ranking.')); return; }
  const rows = items.map((item) => [item.product, money(item.metric_value ?? item.revenue), item.transactions, item.units_sold ?? 'Unavailable', products.profit_available ? money(item.gross_profit) : 'Unavailable']);
  target.append(createTable(['Product', products.metric_label || 'Revenue', 'Transactions', 'Units', 'Gross profit'], rows));
}

function configureDomainView(result) {
  const isCost = result.profile?.domain === 'cost';
  $('#trend-title').textContent = isCost ? 'Cost trend' : 'Revenue trend';
  $('#products-title').textContent = isCost ? 'Project / item rankings' : 'Product rankings';
  $('#customers-title').textContent = isCost ? 'Vendors / providers' : 'Customers';
  const ranking = $('#product-ranking');
  ranking.querySelector('option[value="revenue"]').textContent = isCost ? 'Most cost' : 'Most revenue';
  ranking.querySelector('option[value="transactions"]').textContent = isCost ? 'Most records' : 'Most transactions';
}

function renderDashboardTrend() {
  if (!state.lastAnalytics) return;
  const period = $('#trend-period').value;
  const isCost = state.lastAnalytics.profile?.domain === 'cost';
  const trend = state.lastAnalytics.trend[isCost ? `cost_${period}` : period] || [];
  renderChart(trend, isCost ? 'cost' : 'revenue');
}

function selectedDataset() { return $('#dataset-select').value; }
function filterParams() {
  const params = new URLSearchParams(); const selected = selectedDataset(); if (selected) params.set('dataset_id', selected); const preset = $('#date-preset').value; const bounds = state.datasetBounds || {}; const end = bounds.to ? new Date(`${bounds.to}T00:00:00`) : new Date(); const iso = (value) => value.toISOString().slice(0, 10);
  if (preset === 'today') { params.set('from', iso(end)); params.set('to', iso(end)); }
  if (preset === '7' || preset === '30') { const start = new Date(end); start.setDate(start.getDate() - Number(preset) + 1); params.set('from', iso(start)); params.set('to', iso(end)); }
  if (preset === 'quarter') { params.set('from', iso(new Date(end.getFullYear(), Math.floor(end.getMonth() / 3) * 3, 1))); params.set('to', iso(end)); }
  if (preset === 'custom') { if ($('#from-date').value) params.set('from', $('#from-date').value); if ($('#to-date').value) params.set('to', $('#to-date').value); }
  return params;
}

async function loadDashboard() {
  if (!selectedDataset()) { status('#dashboard-status', 'Upload a processed dataset to activate analytics.'); return; }
  status('#dashboard-status', 'Calculating metrics...');
  const result = await request(`/api/businesses/${state.businessId}/analytics?${filterParams()}`);
  state.lastAnalytics = result;
  state.currency = result.currency || 'GHS';
  state.datasetBounds = result.available_period;
  configureDomainView(result);
  status('#dashboard-status', `${result.dataset.filename} · ${result.period.from || 'all dates'} to ${result.period.to || 'all dates'}`);
  $('#summary').replaceChildren(cell('p', result.summary)); $('#dashboard-warnings').replaceChildren(...result.warnings.map((warning) => { const item = cell('div', warning); item.className = 'warning'; return item; }));
  const isCost = result.profile?.domain === 'cost'; const primaryLabel = result.kpis.primary_label || 'Total revenue'; const primaryValue = result.kpis.primary_value ?? result.kpis.total_revenue; const cards = [[primaryLabel, money(primaryValue)], ['Records', result.kpis.transactions], [isCost ? 'Average cost record' : 'Average sale', money(isCost ? (result.kpis.total_cost / (result.kpis.transactions || 1)) : result.kpis.average_sale)], ['Top project / item', result.kpis.top_product || 'Unavailable']];
  $('#kpis').replaceChildren(...cards.map(([label, value]) => { const card = document.createElement('div'); card.className = 'kpi'; card.append(cell('span', label), cell('strong', value)); return card; }));
  renderDashboardTrend(); renderProducts(result.products);
  if (result.customers.available) renderTable($('#customers'), ['Customer', result.profile?.domain === 'cost' ? 'Cost' : 'Revenue', 'Records'], result.customers.top_customers.map((item) => [item.customer, money(item.metric_value ?? item.revenue), item.transactions])); else $('#customers').replaceChildren(cell('p', result.customers.reason));
  $('#conditional').replaceChildren(cell('p', result.profit.available ? `Gross profit is ${money(result.profit.gross_profit)} after ${money(result.profit.cost)} in costs.` : result.profile?.domain === 'cost' ? `Recorded costs total ${money(result.kpis.total_cost)}. Revenue is not present in this dataset, so profit cannot be calculated.` : result.profit.reason), cell('p', result.inventory.reason));
}

async function loadInsights() {
  if (!selectedDataset()) return; const result = await request(`/api/businesses/${state.businessId}/insights?${filterParams()}`); status('#insight-status', `${result.dataset.filename} · ${result.period.from || 'all dates'} to ${result.period.to || 'all dates'} · grounded in accepted records.`);
  const list = $('#insights-list'); list.replaceChildren(); if (!result.insights.length) list.append(cell('p', 'There are not enough accepted records to generate an insight for this period.'));
  result.insights.forEach((item) => {
    const card = document.createElement('article'); card.className = `insight insight-${item.severity || 'info'}`;
    const header = document.createElement('div'); header.className = 'insight-header'; header.append(cell('h3', item.title), cell('span', item.type));
    card.append(header, cell('p', item.message));
    const evidence = document.createElement('div'); evidence.className = 'insight-evidence'; evidence.append(cell('span', 'Based on this period'));
    Object.entries(item.supporting_metric || {}).filter(([, value]) => value !== null && value !== undefined).forEach(([key, value]) => { const metric = document.createElement('span'); metric.className = 'evidence-metric'; const displayValue = typeof value === 'number' && ['total', 'revenue', 'current', 'previous', 'average_sale'].includes(key) ? money(value) : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value); metric.append(cell('small', key.replaceAll('_', ' ')), cell('strong', displayValue)); evidence.append(metric); });
    card.append(evidence);
    if (item.limitations?.length) { const limitation = cell('small', `Note: ${item.limitations.join(' ')}`); limitation.className = 'insight-note'; card.append(limitation); }
    list.append(card);
  });
}

function renderQuestionAnswer(result) {
  const output = $('#question-result'); output.hidden = false; output.replaceChildren();
  if (typeof result.answer === 'string') { output.append(cell('p', result.answer)); return; }
  if (result.answer?.message) { output.append(cell('p', result.answer.message)); return; }
  if (Array.isArray(result.answer)) { output.append(createTable(['Product', 'Revenue', 'Transactions', 'Units', 'Gross profit'], result.answer.map((item) => [item.product, money(item.revenue), item.transactions, item.units_sold ?? 'Unavailable', item.gross_profit === undefined ? 'Unavailable' : money(item.gross_profit)]))); return; }
  output.append(cell('p', 'This answer is not available for the selected data.'));
}

async function askLance() {
  if (!state.datasets.length) { status('#ask-status', 'Upload at least one processed business file first.', true); return; }
  status('#ask-status', 'Lance is searching all business datasets and preparing an answer...');
  const question = $('#lance-question').value.trim(); if (!question) return;
  const submit = $('#ask-form button[type="submit"]'); submit.disabled = true;
  const controller = new AbortController(); const timeout = window.setTimeout(() => controller.abort(), 50000);
  try { const result = await request(`/api/businesses/${state.businessId}/ask-lance?${filterParams()}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, conversation_id: state.conversationId }), signal: controller.signal }); state.conversationId = result.conversation_id; $('#lance-question').value = ''; renderMessage({ role: 'user', content: result.question }); renderMessage({ role: 'assistant', content: result.answer }); status('#ask-status', `${result.datasets_considered} business datasets searched · saved to conversation.`); await loadConversations(); } catch (error) { status('#ask-status', error.name === 'AbortError' ? 'Lance took too long to respond. Check the model configuration or try again.' : error.message, true); } finally { window.clearTimeout(timeout); submit.disabled = false; }
}

function renderMessage(message) {
  const target = $('#chat-messages'); if (target.querySelector('.empty-chat')) target.replaceChildren();
  const bubble = document.createElement('article'); bubble.className = `chat-message chat-${message.role}`; bubble.append(cell('span', message.role === 'assistant' ? 'Lance' : 'You'), cell('p', message.content)); if (message.created_at) bubble.append(cell('time', new Date(message.created_at).toLocaleString())); target.append(bubble); target.scrollTop = target.scrollHeight;
}

function renderConversationList(conversations) {
  const target = $('#conversation-list'); target.replaceChildren();
  if (!conversations.length) { target.append(cell('p', 'No saved conversations yet.')); return; }
  conversations.forEach((conversation) => { const button = document.createElement('button'); button.type = 'button'; button.className = `conversation-item${conversation.id === state.conversationId ? ' active' : ''}`; button.append(cell('strong', conversation.title), cell('small', new Date(conversation.updated_at).toLocaleString())); button.addEventListener('click', () => loadConversation(conversation.id)); target.append(button); });
}

async function loadConversations() {
  if (!state.businessId) return; const conversations = await request(`/api/businesses/${state.businessId}/ask-lance/conversations`); renderConversationList(conversations);
}

async function loadConversation(conversationId) {
  const conversation = await request(`/api/businesses/${state.businessId}/ask-lance/conversations/${conversationId}`); state.conversationId = conversation.id; $('#chat-messages').replaceChildren(); conversation.messages.forEach(renderMessage); $('#chat-context').textContent = conversation.title; await loadConversations();
}

function startConversation() { state.conversationId = null; $('#chat-messages').replaceChildren(cell('p', 'Your conversation will appear here.')); $('#chat-messages').firstChild.className = 'empty-chat'; $('#chat-context').textContent = selectedDataset() ? 'New conversation' : 'No dataset selected'; $('#lance-question').focus(); loadConversations().catch((error) => status('#ask-status', error.message, true)); }

async function refreshViews() {
  $('#question-result').hidden = true; $('#question-result').textContent = '';
  try { await loadDashboard(); await loadInsights(); }
  catch (error) { status('#dashboard-status', error.message, true); status('#insight-status', error.message, true); }
}

async function loadHistory() {
  state.datasets = await request(`/api/businesses/${state.businessId}/datasets`); const select = $('#dataset-select'); select.replaceChildren(); state.datasets.filter((item) => item.status !== 'failed').forEach((item) => { const option = cell('option', `${item.filename} · ${item.status}`); option.value = item.id; select.append(option); });
  const history = $('#history'); history.replaceChildren(); if (!state.datasets.length) { history.append(cell('p', 'No datasets yet. Upload a CSV or Excel file to begin.')); return; }
  state.datasets.forEach((item) => { const row = document.createElement('div'); row.className = 'dataset'; row.append(cell('span', `${item.filename} · ${item.status} · ${item.accepted_rows} accepted · ${item.rejected_rows} rejected`), cell('span', new Date(item.created_at).toLocaleDateString())); history.append(row); });
  if (selectedDataset()) {
    try { await loadDashboard(); await loadInsights(); }
    catch (error) { status('#dashboard-status', error.message, true); status('#insight-status', error.message, true); }
  }
}

async function loadProfile() {
  const identity = await request('/api/auth/me');
  $('#profile-name').value = identity.user.full_name || '';
  $('#profile-email').value = identity.user.email;
  $('#profile-business').value = identity.business?.name || '';
  if (identity.user.role !== 'admin') return;
  $('#admin-panel').hidden = false;
  const users = await request('/api/admin/users');
  const target = $('#admin-users'); target.replaceChildren();
  users.forEach((item) => {
    const row = document.createElement('div'); row.className = 'admin-user'; row.append(cell('span', `${item.email}${item.full_name ? ` · ${item.full_name}` : ''}`));
    const select = document.createElement('select');
    ['owner', 'admin', 'member'].forEach((role) => { const option = cell('option', role); option.value = role; option.selected = role === item.role; select.append(option); });
    select.addEventListener('change', async () => { await request(`/api/admin/users/${item.id}/role`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: select.value }) }); });
    row.append(select); target.append(row);
  });
}

function navigate(page) { state.page = pages[page] ? page : 'dashboard'; location.hash = state.page; $$('.page-view').forEach((view) => { view.hidden = view.dataset.view !== state.page; }); $('#page-title').textContent = pages[state.page].title; $('#page-description').textContent = pages[state.page].description; $$('.nav-link').forEach((link) => link.classList.toggle('active', link.dataset.page === state.page)); }

async function bootstrap() {
  try {
    const refresh = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' }); if (!refresh.ok) throw new Error('signed out'); state.token = (await refresh.json()).access_token;
    const identity = await request('/api/auth/me'); state.user = identity.user; state.businessId = identity.business?.id; $('#business-name').textContent = identity.business?.name || 'Workspace'; $('#user-email').textContent = identity.user.email; $('#user-avatar').textContent = (identity.business?.name || identity.user.email).slice(0, 1).toUpperCase(); $('#app-root').hidden = false; $('#loading-state').hidden = true; navigate(state.page);
  } catch { window.location.replace('/'); return; }
  try {
    await loadHistory(); if (state.page === 'ask-lance') await loadConversations();
  } catch (error) { status('#dashboard-status', error.message, true); }
}

$('#logout').addEventListener('click', async () => { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }); window.location.replace('/'); });
$$('.nav-link').forEach((link) => link.addEventListener('click', () => navigate(link.dataset.page)));
$('#dataset-select').addEventListener('change', refreshViews);
$('#refresh-dashboard').addEventListener('click', refreshViews);
$('#date-preset').addEventListener('change', async (event) => { const custom = event.target.value === 'custom'; $('#from-date').disabled = !custom; $('#to-date').disabled = !custom; await refreshViews(); });
$('#trend-period').addEventListener('change', renderDashboardTrend);
$('#upload-form').addEventListener('submit', async (event) => { event.preventDefault(); const submit = event.target.querySelector('button[type="submit"]'); submit.disabled = true; status('#upload-status', 'Processing your file...'); const body = new FormData(); body.append('file', $('#dataset-file').files[0]); try { const result = await request(`/api/businesses/${state.businessId}/datasets`, { method: 'POST', body }); status('#upload-status', `${result.status}: ${result.accepted_rows} accepted, ${result.rejected_rows} rejected.`); await loadHistory(); navigate('dashboard'); } catch (error) { status('#upload-status', error.message, true); } finally { submit.disabled = false; } });
$('#profile-form').addEventListener('submit', async (event) => { event.preventDefault(); try { const identity = await request('/api/auth/profile', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ full_name: $('#profile-name').value, business_name: $('#profile-business').value }) }); state.businessId = identity.business.id; $('#business-name').textContent = identity.business.name; status('#profile-status', 'Profile saved.'); } catch (error) { status('#profile-status', error.message, true); } });
$('#question-grid').addEventListener('click', async (event) => { if (!event.target.dataset.question || !selectedDataset()) return; try { const result = await request(`/api/businesses/${state.businessId}/questions/${event.target.dataset.question}?${filterParams()}`); renderQuestionAnswer(result); } catch (error) { status('#insight-status', error.message, true); } });
$('#product-ranking').addEventListener('change', () => { if (state.lastAnalytics) renderProducts(state.lastAnalytics.products); });
$('#ask-form').addEventListener('submit', async (event) => { event.preventDefault(); await askLance(); });
$('#new-chat').addEventListener('click', startConversation);
window.addEventListener('hashchange', () => { navigate(location.hash.slice(1)); if (state.page === 'profile') loadProfile().catch((error) => status('#profile-status', error.message, true)); if (state.page === 'ask-lance') loadConversations().catch((error) => status('#ask-status', error.message, true)); });
$$('.nav-link').forEach((link) => link.addEventListener('click', () => { if (link.dataset.page === 'profile') loadProfile().catch((error) => status('#profile-status', error.message, true)); }));
bootstrap();
