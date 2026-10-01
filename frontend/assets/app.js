const state = { token: null, businessId: null, datasets: [], page: location.hash.slice(1) || 'dashboard' };
const pages = {
  dashboard: { title: 'Business dashboard', description: 'A clear view of the records your business has accepted and the signals they support.' },
  data: { title: 'Your data', description: 'Upload, inspect, and understand the processing history behind your numbers.' },
  insights: { title: 'Business insights', description: 'Deterministic observations and fixed questions grounded in the selected dataset.' },
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const cell = (tag, text) => { const element = document.createElement(tag); element.textContent = text; return element; };
const money = (value) => Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

function renderChart(items) {
  const target = $('#trend'); target.replaceChildren();
  if (!items.length) { target.append(cell('p', 'No data for this period.')); return; }
  const max = Math.max(...items.map((item) => item.revenue)); const chart = document.createElement('div'); chart.className = 'chart';
  items.forEach((item) => { const row = document.createElement('div'); row.className = 'bar-row'; row.append(cell('span', item.period)); const track = document.createElement('div'); track.className = 'bar-track'; const bar = document.createElement('div'); bar.className = 'bar'; bar.style.width = `${max ? item.revenue / max * 100 : 0}%`; track.append(bar); row.append(track, cell('span', money(item.revenue))); chart.append(row); }); target.append(chart);
}

function renderProducts(products) {
  const target = $('#products'); target.replaceChildren();
  if (!products.available) { target.append(cell('p', products.reason)); return; }
  target.append(cell('h3', 'Best sellers'), createTable(['Product', 'Revenue', 'Units'], products.best_sellers.map((item) => [item.product, money(item.revenue), item.units_sold ?? 'Unavailable'])));
  target.append(cell('h3', 'Worst sellers'), createTable(['Product', 'Revenue', 'Units'], products.worst_sellers.map((item) => [item.product, money(item.revenue), item.units_sold ?? 'Unavailable'])));
}

function selectedDataset() { return $('#dataset-select').value; }
function filterParams() {
  const params = new URLSearchParams({ dataset_id: selectedDataset() }); const preset = $('#date-preset').value; const today = new Date(); const iso = (value) => value.toISOString().slice(0, 10);
  if (preset === 'today') { params.set('from', iso(today)); params.set('to', iso(today)); }
  if (preset === '7' || preset === '30') { const start = new Date(today); start.setDate(start.getDate() - Number(preset) + 1); params.set('from', iso(start)); params.set('to', iso(today)); }
  if (preset === 'quarter') { params.set('from', iso(new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1))); params.set('to', iso(today)); }
  if (preset === 'custom') { if ($('#from-date').value) params.set('from', $('#from-date').value); if ($('#to-date').value) params.set('to', $('#to-date').value); }
  return params;
}

async function loadDashboard() {
  if (!selectedDataset()) { status('#dashboard-status', 'Upload a processed dataset to activate analytics.'); return; }
  status('#dashboard-status', 'Calculating metrics...');
  const result = await request(`/api/businesses/${state.businessId}/analytics?${filterParams()}`);
  status('#dashboard-status', `${result.dataset.filename} · ${result.period.from || 'all dates'} to ${result.period.to || 'all dates'}`);
  $('#summary').replaceChildren(cell('p', result.summary)); $('#dashboard-warnings').replaceChildren(...result.warnings.map((warning) => { const item = cell('div', warning); item.className = 'warning'; return item; }));
  $('#kpis').replaceChildren(...[['Total revenue', money(result.kpis.total_revenue)], ['Transactions', result.kpis.transactions], ['Average sale', money(result.kpis.average_sale)], ['Top product', result.kpis.top_product || 'Unavailable']].map(([label, value]) => { const card = document.createElement('div'); card.className = 'kpi'; card.append(cell('span', label), cell('strong', value)); return card; }));
  renderChart(result.trend.daily); renderProducts(result.products);
  if (result.customers.available) renderTable($('#customers'), ['Customer', 'Revenue', 'Transactions'], result.customers.top_customers.map((item) => [item.customer, money(item.revenue), item.transactions])); else $('#customers').replaceChildren(cell('p', result.customers.reason));
  $('#conditional').replaceChildren(cell('p', result.profit.reason), cell('p', result.inventory.reason));
}

async function loadInsights() {
  if (!selectedDataset()) return; const result = await request(`/api/businesses/${state.businessId}/insights?${filterParams()}`); status('#insight-status', `${result.dataset.filename} · ${result.period.from || 'all dates'} to ${result.period.to || 'all dates'} · grounded in accepted records.`);
  const list = $('#insights-list'); list.replaceChildren(); if (!result.insights.length) list.append(cell('p', 'There are not enough accepted records to generate an insight for this period.'));
  result.insights.forEach((item) => { const card = cell('div', `${item.title}: ${item.message}`); card.className = 'insight'; card.append(document.createElement('br'), cell('small', `Evidence: ${JSON.stringify(item.supporting_metric)}${item.limitations.length ? ` Limitation: ${item.limitations.join(' ')}` : ''}`)); list.append(card); });
}

async function refreshViews() {
  $('#question-result').hidden = true; $('#question-result').textContent = '';
  try { await loadDashboard(); await loadInsights(); }
  catch (error) { status('#dashboard-status', error.message, true); status('#insight-status', error.message, true); }
}

async function loadHistory() {
  state.datasets = await request(`/api/businesses/${state.businessId}/datasets`); const select = $('#dataset-select'); select.replaceChildren(); state.datasets.filter((item) => item.status !== 'failed').forEach((item) => { const option = cell('option', `${item.filename} · ${item.status}`); option.value = item.id; select.append(option); });
  const history = $('#history'); history.replaceChildren(); if (!state.datasets.length) { history.append(cell('p', 'No datasets yet. Upload a CSV or Excel file to begin.')); return; }
  state.datasets.forEach((item) => { const row = document.createElement('div'); row.className = 'dataset'; row.append(cell('span', `${item.filename} · ${item.status} · ${item.accepted_rows} accepted · ${item.rejected_rows} rejected`), cell('span', new Date(item.created_at).toLocaleDateString())); history.append(row); });
  if (selectedDataset()) { await loadDashboard(); await loadInsights(); }
}

function navigate(page) { state.page = pages[page] ? page : 'dashboard'; location.hash = state.page; $$('.page-view').forEach((view) => { view.hidden = view.dataset.view !== state.page; }); $('#page-title').textContent = pages[state.page].title; $('#page-description').textContent = pages[state.page].description; $$('.nav-link').forEach((link) => link.classList.toggle('active', link.dataset.page === state.page)); }

async function bootstrap() {
  try {
    const refresh = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' }); if (!refresh.ok) throw new Error('signed out'); state.token = (await refresh.json()).access_token;
    const identity = await request('/api/auth/me'); state.businessId = identity.business.id; $('#business-name').textContent = identity.business.name; $('#user-email').textContent = identity.user.email; $('#user-avatar').textContent = identity.business.name.slice(0, 1).toUpperCase(); $('#app-root').hidden = false; $('#loading-state').hidden = true; navigate(state.page); await loadHistory();
  } catch { window.location.replace('/'); }
}

$('#logout').addEventListener('click', async () => { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }); window.location.replace('/'); });
$$('.nav-link').forEach((link) => link.addEventListener('click', () => navigate(link.dataset.page)));
$('#dataset-select').addEventListener('change', refreshViews);
$('#refresh-dashboard').addEventListener('click', refreshViews);
$('#date-preset').addEventListener('change', async (event) => { const custom = event.target.value === 'custom'; $('#from-date').disabled = !custom; $('#to-date').disabled = !custom; await refreshViews(); });
$('#upload-form').addEventListener('submit', async (event) => { event.preventDefault(); const submit = event.target.querySelector('button[type="submit"]'); submit.disabled = true; status('#upload-status', 'Processing your file...'); const body = new FormData(); body.append('file', $('#dataset-file').files[0]); try { const result = await request(`/api/businesses/${state.businessId}/datasets`, { method: 'POST', body }); status('#upload-status', `${result.status}: ${result.accepted_rows} accepted, ${result.rejected_rows} rejected.`); await loadHistory(); navigate('dashboard'); } catch (error) { status('#upload-status', error.message, true); } finally { submit.disabled = false; } });
$('#question-grid').addEventListener('click', async (event) => { if (!event.target.dataset.question || !selectedDataset()) return; try { const result = await request(`/api/businesses/${state.businessId}/questions/${event.target.dataset.question}?${filterParams()}`); const output = $('#question-result'); output.hidden = false; output.textContent = JSON.stringify(result.answer, null, 2); } catch (error) { status('#insight-status', error.message, true); } });
window.addEventListener('hashchange', () => navigate(location.hash.slice(1)));
bootstrap();
