const state = { token: null, businessId: null, business: null, user: null, datasets: [], lastAnalytics: null, lastInsights: null, marketResearch: null, researching: false, braveSearchConfigured: false, positionReport: null, inventory: null, inventoryMovements: [], editingInventoryProduct: null, conversationId: null, trendPeriod: 'weekly', page: location.hash.slice(1) || 'dashboard' };
const positionCategories = {
  cash: ['assets', 'Cash on hand'],
  bank: ['assets', 'Cash at bank'],
  receivables: ['assets', 'Accounts receivable'],
  inventory: ['assets', 'Inventory at recorded cost'],
  fixed_assets: ['assets', 'Fixed assets'],
  other_assets: ['assets', 'Other assets'],
  payables: ['liabilities', 'Accounts payable'],
  loans: ['liabilities', 'Loans and borrowings'],
  other_liabilities: ['liabilities', 'Other liabilities'],
  owner_capital: ['equity', 'Owner capital'],
  retained_earnings: ['equity', 'Retained earnings / accumulated loss'],
  other_equity: ['equity', 'Other equity'],
};
const pages = {
  dashboard: { title: 'Business dashboard', description: 'A clear view of the records your business has accepted and the signals they support.' },
  catalogue: { title: 'Product catalogue', description: 'Browse every distinct product found in the selected dataset.' },
  inventory: { title: 'Inventory management', description: 'Track products, stock levels, purchases, sales, and stocktakes in an auditable ledger.' },
  'financial-position': { title: 'Financial position', description: 'Build and print a dated assets, liabilities, and equity statement from recorded account balances.' },
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
  const max = Math.max(...items.map((item) => Math.abs(item[valueKey]))); const chart = document.createElement('div'); chart.className = 'chart';
  items.forEach((item) => { const value = item[valueKey]; const row = document.createElement('div'); row.className = 'bar-row'; row.append(cell('span', item.period)); const track = document.createElement('div'); track.className = 'bar-track'; const bar = document.createElement('div'); bar.className = 'bar'; bar.style.width = `${max ? Math.abs(value) / max * 100 : 0}%`; track.append(bar); row.append(track, cell('span', money(value))); chart.append(row); }); target.append(chart);
}

function renderProducts(products) {
  const target = $('#products'); target.replaceChildren();
  if (!products.available) { target.append(cell('p', products.reason)); return; }
  const items = products.items || [];
  if (!items.length) { target.append(cell('p', 'No product records in this period.')); return; }
  const rows = items.slice(0, 5).map((item) => [item.product, money(item.revenue), products.profit_available ? money(item.gross_profit) : 'Unavailable', item.roi_pct === undefined || item.roi_pct === null ? 'Unavailable' : `${item.roi_pct.toFixed(2)}%`]);
  target.append(createTable(['Product', 'Revenue', 'Profit / loss', 'ROI'], rows));
}

function configureDomainView(result) {
  const isCost = result.profile?.domain === 'cost';
  $('#trend-title').textContent = isCost ? 'Cost trend' : 'Revenue trend';
  $('#products-title').textContent = isCost ? 'Project / item rankings' : 'Product rankings';
  $('#customers-title').textContent = isCost ? 'Vendors / providers' : 'Customers';
  if (isCost) $('#products-title').textContent = 'Project / cost-item summary';
}

function renderDashboardTrend() {
  if (!state.lastAnalytics) return;
  const period = state.trendPeriod;
  const isCost = state.lastAnalytics.profile?.domain === 'cost';
  const trend = state.lastAnalytics.trend[isCost ? `cost_${period}` : period] || [];
  renderChart(trend, isCost ? 'cost' : 'revenue');
}

function selectedDataset() { return $('#dataset-select').value; }
function selectedDatasetDetails() { return state.datasets.find((item) => item.id === selectedDataset()); }
function filterParams() {
  const params = new URLSearchParams(); const selected = selectedDataset(); if (selected) params.set('dataset_id', selected); const preset = $('#date-preset').value; const bounds = state.datasetBounds || {}; const end = bounds.to ? new Date(`${bounds.to}T00:00:00`) : new Date(); const iso = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
  if (preset === 'today') { params.set('from', iso(end)); params.set('to', iso(end)); }
  if (preset === '7' || preset === '30') { const start = new Date(end); start.setDate(start.getDate() - Number(preset) + 1); params.set('from', iso(start)); params.set('to', iso(end)); }
  if (preset === 'week') { const start = new Date(end); start.setDate(start.getDate() - (start.getDay() + 6) % 7); params.set('from', iso(start)); params.set('to', iso(end)); }
  if (preset === 'month') { params.set('from', iso(new Date(end.getFullYear(), end.getMonth(), 1))); params.set('to', iso(end)); }
  if (preset === 'quarter') { params.set('from', iso(new Date(end.getFullYear(), Math.floor(end.getMonth() / 3) * 3, 1))); params.set('to', iso(end)); }
  if (preset === 'year') { params.set('from', iso(new Date(end.getFullYear(), 0, 1))); params.set('to', iso(end)); }
  if (preset === 'custom') { if ($('#from-date').value) params.set('from', $('#from-date').value); if ($('#to-date').value) params.set('to', $('#to-date').value); }
  return params;
}

async function loadDashboard() {
  if (!selectedDataset()) { state.lastAnalytics = null; $('#print-report-button').disabled = true; status('#dashboard-status', 'Upload a processed dataset to activate analytics.'); return; }
  state.lastAnalytics = null;
  $('#print-report-button').disabled = true;
  status('#dashboard-status', 'Calculating metrics...');
  const result = await request(`/api/businesses/${state.businessId}/analytics?${filterParams()}`);
  state.lastAnalytics = result;
  $('#print-report-button').disabled = false;
  state.currency = result.currency || 'GHS';
  state.datasetBounds = result.available_period;
  configureDomainView(result);
  status('#dashboard-status', `${result.dataset.filename} · ${result.period.from || 'all dates'} to ${result.period.to || 'all dates'}`);
  $('#summary').replaceChildren(cell('p', result.summary)); $('#dashboard-warnings').replaceChildren(...result.warnings.map((warning) => { const item = cell('div', warning); item.className = 'warning'; return item; }));
  const isCost = result.profile?.domain === 'cost'; const primaryLabel = result.kpis.primary_label || 'Total revenue'; const primaryValue = result.kpis.primary_value ?? result.kpis.total_revenue; const cards = [[primaryLabel, money(primaryValue)], ['Records', result.kpis.transactions], [isCost ? 'Average cost record' : 'Average sale', money(isCost ? (result.kpis.total_cost / (result.kpis.transactions || 1)) : result.kpis.average_sale)], ['Top project / item', result.kpis.top_product || 'Unavailable']];
  if (result.profit.available) {
    cards.push(['Profit / loss after costs', money(result.profit.gross_profit)]);
    cards.push(['Return on recorded cost', result.profit.cost > 0 ? `${(result.profit.gross_profit / result.profit.cost * 100).toFixed(2)}%` : 'Unavailable']);
  }
  $('#kpis').replaceChildren(...cards.map(([label, value]) => { const card = document.createElement('div'); card.className = 'kpi'; card.append(cell('span', label), cell('strong', value)); return card; }));
  renderDashboardTrend(); renderProducts(result.products);
  if (result.customers.available) renderTable($('#customers'), ['Customer', result.profile?.domain === 'cost' ? 'Cost' : 'Revenue', 'Records'], result.customers.top_customers.map((item) => [item.customer, money(item.metric_value ?? item.revenue), item.transactions])); else $('#customers').replaceChildren(cell('p', result.customers.reason));
  $('#conditional').replaceChildren(cell('p', result.profit.available ? `Profit after recorded costs is ${money(result.profit.gross_profit)} after ${money(result.profit.cost)} in costs.` : result.profile?.domain === 'cost' ? `Recorded costs total ${money(result.kpis.total_cost)}. Revenue is not present in this dataset, so profit cannot be calculated.` : result.profit.reason), cell('p', 'Inventory quantities are maintained separately in the Inventory workspace and are not inferred from this report.'));
}

function renderInsightCards(target, items) {
  target.replaceChildren();
  if (!items.length) { target.append(cell('p', 'There are not enough accepted records to generate an insight for this period.')); return; }
  items.forEach((item) => {
    const card = document.createElement('article'); card.className = `insight insight-${item.severity || 'info'}`;
    const header = document.createElement('div'); header.className = 'insight-header'; header.append(cell('h3', item.title), cell('span', item.type));
    card.append(header, cell('p', item.message));
    const evidence = document.createElement('div'); evidence.className = 'insight-evidence'; evidence.append(cell('span', 'Based on this period'));
    Object.entries(item.supporting_metric || {}).filter(([, value]) => value !== null && value !== undefined).forEach(([key, value]) => { const metric = document.createElement('span'); metric.className = 'evidence-metric'; const displayValue = typeof value === 'number' && ['total', 'revenue', 'current', 'previous', 'average_sale', 'gross_profit', 'cost'].includes(key) ? money(value) : key.endsWith('_pct') ? `${value.toFixed(2)}%` : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value); metric.append(cell('small', key.replaceAll('_', ' ')), cell('strong', displayValue)); evidence.append(metric); });
    card.append(evidence);
    if (item.limitations?.length) { const limitation = cell('small', `Note: ${item.limitations.join(' ')}`); limitation.className = 'insight-note'; card.append(limitation); }
    target.append(card);
  });
}

async function loadInsights() {
  state.lastInsights = null;
  if (!selectedDataset()) { state.lastInsights = null; status('#insight-status', 'Upload a processed dataset to generate insights.'); renderInsightCards($('#insights-list'), []); renderInsightCards($('#dashboard-insights'), []); return; }
  const result = await request(`/api/businesses/${state.businessId}/insights?${filterParams()}`); status('#insight-status', `${result.dataset.filename} · ${result.period.from || 'all dates'} to ${result.period.to || 'all dates'} · grounded in accepted records.`);
  state.lastInsights = result;
  renderInsightCards($('#insights-list'), result.insights); renderInsightCards($('#dashboard-insights'), result.insights);
}

async function loadBraveSearchStatus() {
  const result = await request(`/api/businesses/${state.businessId}/integrations/brave-search`);
  state.braveSearchConfigured = result.configured;
  $('#remove-brave-key').disabled = !result.configured;
  $('#run-performance-research').disabled = !result.configured || !selectedDataset();
  status(
    '#research-settings-status',
    result.configured
      ? `Brave Search connected${result.updated_at ? ` · updated ${new Date(result.updated_at).toLocaleDateString()}` : ''}. The key is stored encrypted and never displayed again.`
      : 'Connect a Brave Search API key to enable external research.',
  );
}

function localDateString(value = new Date()) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}

function initializePositionControls() {
  const today = localDateString();
  $('#position-report-date').value = today;
  $('#position-entry-date').value = today;
  const select = $('#position-category');
  select.replaceChildren();
  Object.entries(positionCategories).forEach(([key, [group, label]]) => {
    const option = cell('option', `${group.toUpperCase()} · ${label}`);
    option.value = key;
    select.append(option);
  });
}

function renderPositionGroup(target, title, items) {
  const section = document.createElement('section');
  section.className = 'position-group';
  section.append(cell('h3', title));
  const rows = items.map((item) => [
    item.account_name,
    money(item.amount),
    item.as_of_date,
    item.note || '—',
  ]);
  const tableScroll = document.createElement('div');
  tableScroll.className = 'table-scroll';
  tableScroll.append(createTable(['Account', 'Balance', 'Balance date', 'Note'], rows));
  section.append(tableScroll);
  target.append(section);
}

function renderFinancialPosition(result) {
  state.positionReport = result;
  const totals = result.totals;
  const summary = [
    ['Assets', money(totals.assets)],
    ['Liabilities', money(totals.liabilities)],
    ['Equity', money(totals.equity)],
    [totals.complete ? 'Assets − liabilities − equity' : 'Known balance difference (partial)', money(totals.balance_difference)],
  ];
  $('#position-summary').replaceChildren(...summary.map(([label, amount]) => {
    const card = document.createElement('div');
    card.className = 'kpi';
    card.append(cell('span', label), cell('strong', amount));
    return card;
  }));
  const warnings = result.warnings.map((message) => {
    const item = cell('div', message);
    item.className = 'warning';
    return item;
  });
  if (result.missing_categories.length) {
    warnings.unshift(cell('div', `Missing balance categories: ${result.missing_categories.map((item) => item.label).join(', ')}. Record each balance, including zero, for a complete statement.`));
    warnings[0].className = 'warning';
  }
  if (result.stale_balances.length) {
    warnings.push(cell('div', `${result.stale_balances.length} account balance(s) are carried forward from earlier dates.`));
    warnings[warnings.length - 1].className = 'warning';
  }
  $('#position-warnings').replaceChildren(...warnings);
  const groups = $('#position-groups');
  groups.replaceChildren();
  renderPositionGroup(groups, 'Assets', result.assets);
  renderPositionGroup(groups, 'Liabilities', result.liabilities);
  renderPositionGroup(groups, 'Equity', result.equity);
  status(
    '#position-status',
    `${result.totals.complete ? (result.totals.balanced ? 'Statement balances.' : 'Statement does not balance.') : 'Partial financial position.'} As of ${result.as_of_date}.`,
    result.totals.complete && !result.totals.balanced,
  );
  $('#print-position-report').disabled = false;
}

async function loadPositionHistory() {
  const items = await request(`/api/businesses/${state.businessId}/financial-position/history`);
  const rows = items.map((item) => [
    item.as_of_date,
    positionCategories[item.category]?.[1] || item.category,
    item.account_name,
    money(item.amount),
    item.note || '—',
    item.recorded_by,
  ]);
  const target = $('#position-history');
  if (!rows.length) {
    target.replaceChildren(cell('p', 'No account balances recorded yet.'));
    return;
  }
  renderTable(target, ['Balance date', 'Category', 'Account', 'Balance', 'Note', 'Recorded by'], rows);
}

async function loadFinancialPosition() {
  const asOf = $('#position-report-date').value;
  if (!asOf) {
    status('#position-status', 'Choose a report date.', true);
    return;
  }
  status('#position-status', 'Calculating dated balances...');
  $('#print-position-report').disabled = true;
  try {
    const [result] = await Promise.all([
      request(`/api/businesses/${state.businessId}/financial-position?as_of=${encodeURIComponent(asOf)}`),
      loadPositionHistory(),
    ]);
    renderFinancialPosition(result);
  } catch (error) {
    status('#position-status', error.message, true);
  }
}

async function savePositionBalance(event) {
  event.preventDefault();
  const submit = $('#position-balance-form button[type="submit"]');
  submit.disabled = true;
  try {
    const result = await request(`/api/businesses/${state.businessId}/financial-position/balances`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        as_of_date: $('#position-entry-date').value,
        category: $('#position-category').value,
        account_name: $('#position-account-name').value,
        amount: Number($('#position-amount').value),
        note: $('#position-note').value,
      }),
    });
    $('#position-account-name').value = '';
    $('#position-amount').value = '';
    $('#position-note').value = '';
    $('#position-report-date').value = result.as_of_date;
    await loadFinancialPosition();
    status('#position-status', `Saved ${positionCategories[result.category][1]} balance for ${result.as_of_date}.`);
  } catch (error) {
    status('#position-status', error.message, true);
  } finally {
    submit.disabled = false;
  }
}

function buildFinancialPositionReport() {
  const result = state.positionReport;
  if (!result) throw new Error('Generate a financial position before printing.');
  const report = $('#print-report');
  report.replaceChildren();
  report.hidden = false;
  const header = document.createElement('header');
  header.className = 'print-report-header';
  header.append(cell('p', 'FERLANCE · FINANCIAL POSITION'), cell('h1', 'Statement of financial position'));
  header.append(cell('p', `${state.business?.name || 'Business workspace'} · As of ${result.as_of_date}`));
  header.append(cell('p', `Prepared ${new Date().toLocaleString()} · ${state.user?.email || ''}`));
  report.append(header);
  renderPositionGroup(report, 'Assets', result.assets);
  renderPositionGroup(report, 'Liabilities', result.liabilities);
  renderPositionGroup(report, 'Equity', result.equity);
  appendReportSection(report, 'Position totals', [
    ['Total assets', money(result.totals.assets)],
    ['Total liabilities', money(result.totals.liabilities)],
    ['Total equity', money(result.totals.equity)],
    ['Liabilities and equity', money(result.totals.liabilities_and_equity)],
    ['Balance difference', money(result.totals.balance_difference)],
    ['Completeness', result.totals.complete ? 'All required balance categories have entries' : 'Partial — see missing categories'],
    ['Accounting equation', result.totals.balanced ? 'Balances' : 'Not verified as balanced'],
  ]);
  if (result.missing_categories.length) {
    appendReportSection(report, 'Missing balance categories', result.missing_categories.map((item) => [item.label, item.group]));
  }
  if (result.stale_balances.length) {
    appendReportSection(report, 'Carried-forward balances', result.stale_balances.map((item) => [
      item.account_name,
      positionCategories[item.category]?.[1] || item.category,
      item.as_of_date,
    ]), ['Account', 'Category', 'Last balance date']);
  }
  report.append(cell('p', 'Balances use the latest entry for each account on or before the report date. Missing balances are not assumed to be zero. This operational statement is not a substitute for a complete general ledger or accountant-reviewed financial statements.'));
}

function printFinancialPosition() {
  try {
    buildFinancialPositionReport();
    window.print();
  } catch (error) {
    status('#position-status', error.message, true);
  }
}

function renderMarketResearch(result) {
  const target = $('#research-results');
  target.replaceChildren();
  if (result.analysis_error) {
    const warning = cell('p', `Automated source analysis is unavailable: ${result.analysis_error}`);
    warning.className = 'warning';
    target.append(warning);
  }
  if (!result.findings.length) {
    target.append(cell('p', result.analysis || 'No losses or material declines were detected for the selected report period.'));
    (result.limitations || []).forEach((limitation) => {
      const note = cell('p', limitation);
      note.className = 'research-limitation';
      target.append(note);
    });
    return;
  }
  if (result.analysis) target.append(cell('p', result.analysis));
  result.findings.forEach((finding) => {
    const section = document.createElement('section');
    section.className = 'research-finding';
    section.append(cell('h3', `${finding.finding} · ${finding.product}`));
    const metric = finding.metric || finding.observed_metric || {};
    if (metric.percent !== null && metric.percent !== undefined) {
      section.append(cell('p', `Measured change: ${metric.percent}% for ${finding.period?.from || result.period?.from || ''} to ${finding.period?.to || result.period?.to || ''}.`));
    } else if (metric.gross_profit !== undefined) {
      section.append(cell('p', `Recorded item profit/loss: ${money(metric.gross_profit)}.`));
    }
    const sources = result.sources.filter((source) => source.product === finding.product);
    if (!sources.length) section.append(cell('p', 'No matching external sources were returned.'));
    sources.forEach((source) => {
      const card = document.createElement('article');
      card.className = 'research-source';
      const link = cell('a', `[${source.id}] ${source.title}`);
      link.href = source.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      card.append(link, cell('p', source.description));
      if (source.age) card.append(cell('small', `Source date: ${source.age}`));
      section.append(card);
    });
    target.append(section);
  });
  (result.limitations || []).forEach((limitation) => {
    const note = cell('p', limitation);
    note.className = 'research-limitation';
    target.append(note);
  });
}

async function runPerformanceResearch() {
  const button = $('#run-performance-research');
  if (state.researching) return;
  const datasetId = selectedDataset();
  if (!datasetId) {
    status('#research-status', 'Select a processed dataset before researching performance.', true);
    return;
  }
  const filterKey = filterParams().toString();
  state.researching = true;
  button.disabled = true;
  state.marketResearch = null;
  status('#research-status', 'Checking report signals and searching the web for Ghana seasonal, environmental, festive, and market context...');
  try {
    const result = await request(`/api/businesses/${state.businessId}/performance-research?${filterKey}`, { method: 'POST' });
    const stillCurrent = selectedDataset() === datasetId && filterParams().toString() === filterKey;
    if (stillCurrent) {
      state.marketResearch = { ...result, dataset_id: datasetId, filter_key: filterKey };
      renderMarketResearch(result);
      status('#research-status', `${result.findings.length} report finding(s) reviewed · ${result.sources?.length || 0} source(s) retrieved · ${result.market}.`);
    }
  } catch (error) {
    status('#research-status', error.message, true);
  } finally {
    state.researching = false;
    button.disabled = !state.braveSearchConfigured || !selectedDataset();
    maybeRunPerformanceResearch();
  }
}

function maybeRunPerformanceResearch() {
  const filterKey = filterParams().toString();
  if (
    state.braveSearchConfigured
    && selectedDataset()
    && (state.marketResearch?.dataset_id !== selectedDataset() || state.marketResearch?.filter_key !== filterKey)
  ) {
    runPerformanceResearch();
  }
}

function renderCatalogue() {
  const analytics = state.catalogueAnalytics;
  const target = $('#catalogue-list');
  const query = $('#catalogue-search').value.trim().toLocaleLowerCase();
  const isCost = analytics?.profile?.domain === 'cost';
  const items = (analytics?.products?.items || []).filter((item) => item.product.toLocaleLowerCase().includes(query));
  const sort = $('#catalogue-sort').value;
  items.sort((first, second) => {
    if (sort === 'revenue') return second.revenue - first.revenue || first.product.localeCompare(second.product);
    if (sort === 'profit') return (second.gross_profit ?? Number.NEGATIVE_INFINITY) - (first.gross_profit ?? Number.NEGATIVE_INFINITY) || first.product.localeCompare(second.product);
    return first.product.localeCompare(second.product);
  });
  $('#catalogue-summary').textContent = `${items.length} of ${analytics?.products?.items?.length || 0} products`;
  target.replaceChildren();
  if (!analytics?.products?.available) {
    target.append(cell('p', analytics?.products?.reason || 'No processed dataset selected.'));
    return;
  }
  if (!items.length) {
    target.append(cell('p', query ? 'No products match your search.' : 'No product records are present in this dataset.'));
    return;
  }
  const list = document.createElement('div');
  list.className = 'catalogue-rows';
  items.forEach((item) => {
    const row = document.createElement('article');
    row.className = 'catalogue-row';
    const identity = document.createElement('div');
    identity.className = 'catalogue-product-identity';
    identity.append(cell('strong', item.product), cell('small', `${item.transactions.toLocaleString()} records${item.units_sold === undefined ? '' : ` · ${item.units_sold.toLocaleString()} units`}`));
    const stats = document.createElement('div');
    stats.className = 'catalogue-product-stats';
    stats.append(cell('span', `${isCost ? 'Recorded cost' : 'Revenue'} · ${money(isCost ? item.cost ?? item.revenue : item.revenue)}`));
    if (item.cost !== undefined && !isCost) stats.append(cell('span', `Recorded cost · ${money(item.cost)}`));
    stats.append(cell('span', `Profit / loss · ${item.gross_profit === undefined ? 'Unavailable' : money(item.gross_profit)}`));
    stats.append(cell('span', `ROI · ${item.roi_pct === undefined || item.roi_pct === null ? 'Unavailable' : `${item.roi_pct.toFixed(2)}%`}`));
    row.append(identity, stats);
    list.append(row);
  });
  target.append(list);
}

async function loadCatalogue() {
  const dataset = selectedDatasetDetails();
  state.catalogueAnalytics = null;
  if (!dataset) {
    $('#catalogue-source').textContent = 'Upload or select a processed dataset to build its product list.';
    $('#catalogue-summary').textContent = '';
    renderCatalogue();
    return;
  }
  $('#catalogue-source').textContent = `Complete dataset · ${dataset.filename} · all available dates`;
  $('#catalogue-summary').textContent = 'Loading catalogue...';
  const result = await request(`/api/businesses/${state.businessId}/analytics?dataset_id=${encodeURIComponent(dataset.id)}`);
  state.catalogueAnalytics = result;
  state.currency = result.currency || 'GHS';
  renderCatalogue();
}

function quantity(value) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function renderInventorySummary(target, summary) {
  const value = summary.inventory_value_complete ? money(summary.inventory_value) : 'Incomplete cost data';
  const cards = [
    ['Active products', summary.product_count.toLocaleString()],
    ['Units on hand', quantity(summary.units_on_hand)],
    ['At / below reorder level', summary.low_stock_count.toLocaleString()],
    ['Stock value', value],
  ];
  target.replaceChildren(...cards.map(([label, amount]) => {
    const card = document.createElement('div');
    card.className = 'kpi';
    card.append(cell('span', label), cell('strong', amount));
    return card;
  }));
}

function renderInventoryDashboard() {
  const target = $('#inventory-dashboard-summary');
  if (!state.inventory) {
    target.replaceChildren(cell('p', 'Inventory data is unavailable.'));
    return;
  }
  renderInventorySummary(target, state.inventory.summary);
  const statusText = state.inventory.summary.low_stock_count
    ? `${state.inventory.summary.low_stock_count} product(s) are at or below their reorder level.`
    : 'No products are currently at or below their reorder level.';
  status('#inventory-dashboard-status', statusText);
}

function renderInventoryProducts() {
  const target = $('#inventory-products');
  const query = $('#inventory-search').value.trim().toLocaleLowerCase();
  const includeArchived = $('#inventory-include-archived').checked;
  const items = (state.inventory?.items || []).filter((item) =>
    (includeArchived || item.active) &&
    `${item.name} ${item.sku || ''}`.toLocaleLowerCase().includes(query));
  const table = document.createElement('table');
  table.className = 'data-table inventory-table';
  const head = document.createElement('tr');
  ['Product', 'SKU', 'On hand', 'Unit cost', 'Stock value', 'Status', 'Actions'].forEach((label) => {
    const header = cell('th', label);
    header.scope = 'col';
    head.append(header);
  });
  const thead = document.createElement('thead');
  thead.append(head);
  const tbody = document.createElement('tbody');
  items.forEach((item) => {
    const row = document.createElement('tr');
    [
      `${item.name} · ${item.unit}`,
      item.sku || '—',
      quantity(item.quantity_on_hand),
      item.unit_cost === null ? 'Not set' : money(item.unit_cost),
      item.stock_value === null ? 'Unavailable' : money(item.stock_value),
      item.active ? (item.low_stock ? 'Low stock' : 'In stock') : 'Archived',
    ].forEach((text, index) => {
      const value = cell(index === 5 && item.low_stock && item.active ? 'strong' : 'td', text);
      if (index === 5 && item.low_stock && item.active) value.className = 'inventory-low-stock';
      if (value.tagName !== 'TD') {
        const wrapper = cell('td', '');
        wrapper.append(value);
        row.append(wrapper);
      } else {
        row.append(value);
      }
    });
    const actions = cell('td', '');
    const edit = cell('button', 'Edit');
    edit.type = 'button';
    edit.className = 'secondary inventory-row-action';
    edit.addEventListener('click', () => editInventoryProduct(item));
    actions.append(edit);
    const archive = cell('button', item.active ? 'Archive' : 'Restore');
    archive.type = 'button';
    archive.className = 'secondary inventory-row-action';
    archive.addEventListener('click', () => setInventoryProductActive(item, !item.active));
    actions.append(archive);
    row.append(actions);
    tbody.append(row);
  });
  table.append(thead, tbody);
  target.replaceChildren();
  if (!items.length) target.append(cell('p', query ? 'No products match your search.' : 'Add a product or import your first stocktake to get started.'));
  else target.append(table);
}

function renderInventoryMovements() {
  const rows = state.inventoryMovements.map((movement) => [
    new Date(movement.created_at).toLocaleString(),
    movement.product_name,
    movement.movement_type.replaceAll('_', ' '),
    `${movement.quantity_delta > 0 ? '+' : ''}${quantity(movement.quantity_delta)} ${movement.unit}`,
    movement.note || '—',
    movement.source === 'manual' ? movement.recorded_by : 'CSV stocktake',
  ]);
  const target = $('#inventory-movements');
  if (!rows.length) {
    target.replaceChildren(cell('p', 'No stock movements have been recorded.'));
    return;
  }
  renderTable(target, ['Date', 'Product', 'Type', 'Change', 'Note', 'Recorded by'], rows);
}

function renderInventoryMovementOptions() {
  const select = $('#inventory-movement-product');
  const previous = select.value;
  select.replaceChildren();
  (state.inventory?.items || []).filter((item) => item.active).forEach((item) => {
    const option = cell('option', `${item.name} · ${quantity(item.quantity_on_hand)} ${item.unit} on hand`);
    option.value = item.id;
    select.append(option);
  });
  if ([...select.options].some((option) => option.value === previous)) select.value = previous;
  $('#inventory-movement-submit').disabled = !select.value;
}

function renderInventory() {
  if (!state.inventory) return;
  renderInventorySummary($('#inventory-summary'), state.inventory.summary);
  renderInventoryProducts();
  renderInventoryMovementOptions();
  renderInventoryMovements();
  const archived = $('#inventory-include-archived').checked;
  status('#inventory-status', `${state.inventory.summary.product_count} active products${archived ? ' · archived products included' : ''}. Units and valuation include archived stock; low-stock alerts cover active products. Stock value is withheld when any stock has no recorded unit cost.`);
}

async function loadInventory() {
  const [result, movements] = await Promise.all([
    request(`/api/businesses/${state.businessId}/inventory?include_archived=true`),
    request(`/api/businesses/${state.businessId}/inventory/movements?limit=100`),
  ]);
  state.inventory = result;
  state.inventoryMovements = movements;
  renderInventory();
  renderInventoryDashboard();
}

async function loadInventorySnapshot() {
  state.inventory = null;
  try {
    state.inventory = await request(`/api/businesses/${state.businessId}/inventory`);
    renderInventoryDashboard();
  } catch (error) {
    status('#inventory-dashboard-status', error.message, true);
  }
}

function resetInventoryProductForm() {
  state.editingInventoryProduct = null;
  $('#inventory-product-form').reset();
  $('#inventory-product-unit').value = 'unit';
  $('#inventory-product-reorder').value = '0';
  $('#inventory-product-opening').value = '0';
  $('#inventory-opening-field').hidden = false;
  $('#inventory-product-form-title').textContent = 'Add a product';
  $('#inventory-product-submit').textContent = 'Add product';
  $('#inventory-product-reset').hidden = true;
}

function editInventoryProduct(item) {
  state.editingInventoryProduct = item.id;
  $('#inventory-product-name').value = item.name;
  $('#inventory-product-sku').value = item.sku || '';
  $('#inventory-product-unit').value = item.unit;
  $('#inventory-product-cost').value = item.unit_cost ?? '';
  $('#inventory-product-reorder').value = item.reorder_level;
  $('#inventory-opening-field').hidden = true;
  $('#inventory-product-form-title').textContent = `Edit ${item.name}`;
  $('#inventory-product-submit').textContent = 'Save product';
  $('#inventory-product-reset').hidden = false;
  $('#inventory-product-name').focus();
}

async function setInventoryProductActive(item, active) {
  try {
    await request(`/api/businesses/${state.businessId}/inventory/products/${item.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active }),
    });
    await loadInventory();
  } catch (error) {
    status('#inventory-status', error.message, true);
  }
}

function buildInventoryReport() {
  if (!state.inventory) throw new Error('Load inventory before printing its report.');
  const report = $('#print-report');
  report.replaceChildren();
  report.hidden = false;
  const heading = document.createElement('header');
  heading.className = 'print-report-header';
  heading.append(cell('p', 'FERLANCE · INVENTORY'), cell('h1', 'Inventory report'));
  heading.append(cell('p', `Prepared ${new Date().toLocaleString()} · ${state.user?.email || ''}`));
  report.append(heading);
  appendReportSection(report, 'Stock overview', [
    ['Active products', state.inventory.summary.product_count.toLocaleString()],
    ['Units on hand', quantity(state.inventory.summary.units_on_hand)],
    ['At or below reorder level', state.inventory.summary.low_stock_count.toLocaleString()],
    ['Stock value', state.inventory.summary.inventory_value_complete ? money(state.inventory.summary.inventory_value) : 'Unavailable — one or more on-hand products have no unit cost'],
  ]);
  appendReportSection(
    report,
    'Product quantities',
    state.inventory.items.map((item) => [
      item.name,
      item.sku || '—',
      item.quantity_on_hand,
      item.unit,
      item.unit_cost === null ? 'Not set' : money(item.unit_cost),
      !item.active ? 'Archived' : item.low_stock ? 'At / below reorder level' : 'In stock',
    ]),
    ['Product', 'SKU', 'On hand', 'Unit', 'Unit cost', 'Status'],
  );
  appendReportSection(
    report,
    'Recent stock movements',
    state.inventoryMovements.map((item) => [
      new Date(item.created_at).toLocaleString(),
      item.product_name,
      item.movement_type,
      `${item.quantity_delta > 0 ? '+' : ''}${quantity(item.quantity_delta)} ${item.unit}`,
      item.note || '—',
      item.source === 'manual' ? item.recorded_by : 'CSV stocktake',
    ]),
    ['Date', 'Product', 'Type', 'Change', 'Note', 'Recorded by'],
  );
  report.append(cell('p', 'Inventory levels reflect the recorded opening stock, stocktakes, purchases, sales, and adjustments only. Verify physical quantities before relying on this report.'));
}

function printInventoryReport() {
  try {
    buildInventoryReport();
    window.print();
  } catch (error) {
    status('#inventory-status', error.message, true);
  }
}

function appendReportSection(report, title, rows, headers = ['Metric', 'Value']) {
  const section = document.createElement('section');
  section.className = 'print-report-section';
  section.append(cell('h2', title));
  section.append(createTable(headers, rows));
  report.append(section);
}

function buildFinancialReport() {
  const analytics = state.lastAnalytics;
  if (!analytics) throw new Error('Load a financial report before printing.');
  const dataset = analytics.dataset;
  const report = $('#print-report');
  report.replaceChildren();
  report.hidden = false;

  const header = document.createElement('header');
  header.className = 'print-report-header';
  header.append(cell('p', 'FERLANCE · FINANCIAL REPORT'), cell('h1', state.business?.name || $('#business-name').textContent));
  header.append(cell('p', `Source dataset: ${dataset.filename}`));
  header.append(cell('p', `Reporting period: ${analytics.period.from || 'All available dates'} to ${analytics.period.to || 'All available dates'}`));
  header.append(cell('p', 'Scope: this report covers the selected dataset and does not combine separate uploads.'));
  header.append(cell('p', `Generated: ${new Date().toLocaleString()}`));
  report.append(header);

  const summary = document.createElement('section');
  summary.className = 'print-report-section';
  summary.append(cell('h2', 'Executive summary'), cell('p', analytics.summary));
  report.append(summary);

  const profit = analytics.profit;
  const financialRows = [
    ['Sales revenue', money(analytics.revenue.total)],
    ['Recorded costs', money(analytics.kpis.total_cost)],
    ['Profit / loss after recorded costs', profit.available ? money(profit.gross_profit) : 'Unavailable — ' + profit.reason],
    ['Return on recorded costs', profit.available && profit.cost > 0 ? `${(profit.gross_profit / profit.cost * 100).toFixed(2)}%` : 'Unavailable'],
    ['Average sale', money(analytics.revenue.average_sale)],
    ['Transactions / records', analytics.revenue.transactions.toLocaleString()],
  ];
  appendReportSection(report, 'Financial summary', financialRows);
  const caveat = cell('p', 'Profit and return use only the costs recorded in this dataset; they are not formal net-income or accounting statements. Unassigned overheads, taxes, financing, and currency conversion are not included.');
  caveat.className = 'print-report-note';
  report.lastElementChild.append(caveat);

  const trendPeriod = state.trendPeriod;
  const isCost = analytics.profile?.domain === 'cost';
  const trend = analytics.trend[isCost ? `cost_${trendPeriod}` : trendPeriod] || [];
  const periodLabel = { daily: 'day', weekly: 'week', monthly: 'month', quarterly: 'quarter', yearly: 'year' }[trendPeriod];
  appendReportSection(
    report,
    `${isCost ? 'Cost' : 'Revenue'} by ${periodLabel} (selected view)`,
    trend.map((item) => [item.period, money(item[isCost ? 'cost' : 'revenue']), item.transactions.toLocaleString()]),
    ['Period', isCost ? 'Recorded costs' : 'Revenue', 'Records'],
  );

  const products = analytics.products;
  appendReportSection(
    report,
    'Item performance',
    products.available ? products.items.map((item) => [
      item.product,
      money(item.revenue),
      item.cost === undefined ? 'Unavailable' : money(item.cost),
      item.gross_profit === undefined ? 'Unavailable' : money(item.gross_profit),
      item.margin_pct === undefined ? 'Unavailable' : `${item.margin_pct.toFixed(2)}%`,
      item.roi_pct === undefined || item.roi_pct === null ? 'Unavailable' : `${item.roi_pct.toFixed(2)}%`,
      item.units_sold ?? 'Unavailable',
      item.transactions.toLocaleString(),
    ]) : [],
    ['Item', 'Revenue', 'Recorded cost', 'Profit / loss', 'Margin', 'ROI', 'Units', 'Records'],
  );
  if (!products.available) report.lastElementChild.append(cell('p', products.reason));

  const customers = analytics.customers;
  appendReportSection(
    report,
    isCost ? 'Vendors and providers' : 'Customer performance',
    customers.available ? customers.top_customers.map((item) => [
      item.customer,
      money(item.metric_value ?? item.revenue),
      item.transactions.toLocaleString(),
    ]) : [],
    [isCost ? 'Vendor / provider' : 'Customer', isCost ? 'Recorded costs' : 'Revenue', 'Records'],
  );
  if (!customers.available) report.lastElementChild.append(cell('p', customers.reason));

  const insights = state.lastInsights?.insights || [];
  const insightRows = insights.map((item) => [item.title, item.message, (item.limitations || []).join(' ') || 'None noted']);
  appendReportSection(report, 'Automatic business insights', insightRows, ['Insight', 'Finding', 'Limitations']);
  const matchingResearch = state.marketResearch
    && state.marketResearch.dataset_id === dataset.id
    && state.marketResearch.filter_key === filterParams().toString()
    ? state.marketResearch
    : null;
  if (matchingResearch) {
    appendReportSection(
      report,
      'External market research · contextual leads, not proven causes',
      matchingResearch.findings.map((finding) => [
        finding.product,
        finding.finding,
        matchingResearch.sources.filter((source) => source.product === finding.product).map((source) => `[${source.id}] ${source.title} — ${source.url}`).join('\n') || 'No matching web sources',
      ]),
      ['Product / scope', 'Measured signal', 'Potential context sources'],
    );
    if (matchingResearch.analysis) {
      const researchSummary = cell('p', matchingResearch.analysis);
      const section = document.createElement('section');
      section.className = 'print-report-section';
      section.append(cell('h2', 'Research assessment'), researchSummary);
      matchingResearch.limitations.forEach((limitation) => section.append(cell('p', limitation)));
      report.append(section);
    }
  }

  const qualityRows = [
    ['Upload status', dataset.status],
    ['Accepted records in source', dataset.accepted_rows.toLocaleString()],
    ['Rejected records in source', dataset.rejected_rows.toLocaleString()],
    ['Cost completeness', profit.available ? 'Complete for this report period' : profit.reason],
    ['Inventory', analytics.inventory.available ? 'Available' : analytics.inventory.reason],
  ];
  appendReportSection(report, 'Data quality and scope', qualityRows);
  const notes = [...(analytics.warnings || []), ...(dataset.warnings || [])];
  if (notes.length) {
    const noteList = document.createElement('ul');
    notes.forEach((note) => noteList.append(cell('li', note)));
    const section = document.createElement('section');
    section.className = 'print-report-section';
    section.append(cell('h2', 'Warnings and limitations'), noteList);
    report.append(section);
  }
  report.append(cell('p', 'Prepared from accepted records in Ferlance. Verify source data and consult a qualified accountant before using this report for statutory or tax filings.'));
  return report;
}

function printFinancialReport() {
  try {
    buildFinancialReport();
    window.print();
  } catch (error) {
    status('#dashboard-status', error.message, true);
  }

}
window.addEventListener('afterprint', () => { $('#print-report').hidden = true; });

function renderQuestionAnswer(result) {
  const output = $('#question-result'); output.hidden = false; output.replaceChildren();
  if (typeof result.answer === 'string') { output.append(cell('p', result.answer)); return; }
  if (result.answer?.message) { output.append(cell('p', result.answer.message)); return; }
  if (Array.isArray(result.answer)) { output.append(createTable(['Product', 'Revenue', 'Transactions', 'Units', 'Profit / loss', 'ROI'], result.answer.map((item) => [item.product, money(item.revenue), item.transactions, item.units_sold ?? 'Unavailable', item.gross_profit === undefined ? 'Unavailable' : money(item.gross_profit), item.roi_pct === undefined || item.roi_pct === null ? 'Unavailable' : `${item.roi_pct.toFixed(2)}%`]))); return; }
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
  state.marketResearch = null;
  $('#research-results').replaceChildren();
  status('#research-status', '');
  $('#run-performance-research').disabled = !state.braveSearchConfigured || !selectedDataset();
  try { await loadDashboard(); await loadInsights(); }
  catch (error) { status('#dashboard-status', error.message, true); status('#insight-status', error.message, true); }
  await loadInventorySnapshot();
  maybeRunPerformanceResearch();
}

async function loadHistory() {
  const previousDataset = selectedDataset();
  state.datasets = await request(`/api/businesses/${state.businessId}/datasets`);
  await loadFolderImports();
  const acceptedDatasets = state.datasets.filter((item) => item.status !== 'failed');
  const select = $('#dataset-select');
  select.replaceChildren();
  acceptedDatasets.forEach((item) => {
    const option = cell('option', `${item.filename} · ${item.status}`);
    option.value = item.id;
    option.selected = item.id === previousDataset;
    select.append(option);
  });
  if (!acceptedDatasets.some((item) => item.id === previousDataset) && acceptedDatasets.length) select.value = acceptedDatasets[0].id;
  const history = $('#history');
  history.replaceChildren();
  if (!state.datasets.length) { history.append(cell('p', 'No datasets yet. Upload a CSV or Excel file to begin.')); return; }
  const historyRows = state.datasets.map((item) => [
    item.filename,
    item.status,
    item.source_rows.toLocaleString(),
    item.accepted_rows.toLocaleString(),
    item.rejected_rows.toLocaleString(),
    new Date(item.created_at).toLocaleDateString(),
  ]);
  history.append(createTable(['File', 'Status', 'Source rows', 'Accepted', 'Rejected', 'Uploaded'], historyRows));
  if (selectedDataset()) {
    try { await loadDashboard(); await loadInsights(); }
    catch (error) { status('#dashboard-status', error.message, true); status('#insight-status', error.message, true); }
  }
}

function renderFolderImports(result) {
  status('#folder-import-status', '');
  $('#folder-import-path').textContent = result.folder;
  const target = $('#folder-import-history');
  target.replaceChildren();
  if (!result.imports.length) {
    target.append(cell('p', 'No Excel files have been imported from this folder yet.'));
    return;
  }
  const rows = result.imports.map((item) => [
    item.filename,
    item.status,
    item.error || '—',
    new Date(item.updated_at).toLocaleString(),
  ]);
  target.append(createTable(['File', 'Status', 'Details', 'Last checked'], rows));
}

async function loadFolderImports() {
  renderFolderImports(await request(`/api/businesses/${state.businessId}/folder-imports`));
}

async function checkFolderImports() {
  try {
    const result = await request(`/api/businesses/${state.businessId}/folder-imports`);
    const hasNewDataset = result.imports.some((item) => item.dataset_id && !state.datasets.some((dataset) => dataset.id === item.dataset_id));
    if (hasNewDataset) await loadHistory();
    else renderFolderImports(result);
  } catch (error) {
    status('#folder-import-status', error.message, true);
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

function navigate(page) { state.page = pages[page] ? page : 'dashboard'; location.hash = state.page; $$('.page-view').forEach((view) => { view.hidden = view.dataset.view !== state.page; }); $('#page-title').textContent = pages[state.page].title; $('#page-description').textContent = pages[state.page].description; $('#print-report-button').hidden = state.page !== 'dashboard'; $$('.nav-link').forEach((link) => link.classList.toggle('active', link.dataset.page === state.page)); }

async function bootstrap() {
  try {
    const refresh = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' }); if (!refresh.ok) throw new Error('signed out'); state.token = (await refresh.json()).access_token;
    const identity = await request('/api/auth/me'); state.user = identity.user; state.business = identity.business; state.businessId = identity.business?.id; $('#business-name').textContent = identity.business?.name || 'Workspace'; $('#user-email').textContent = identity.user.email; $('#user-avatar').textContent = (identity.business?.name || identity.user.email).slice(0, 1).toUpperCase(); $('#app-root').hidden = false; $('#loading-state').hidden = true; navigate(state.page);
  } catch { window.location.replace('/'); return; }
  try {
    await loadHistory();
    await loadInventorySnapshot();
    await loadBraveSearchStatus();
    maybeRunPerformanceResearch();
    if (state.page === 'ask-lance') await loadConversations();
    if (state.page === 'catalogue') await loadCatalogue();
    if (state.page === 'inventory') await loadInventory();
    if (state.page === 'financial-position') await loadFinancialPosition();
    if (state.page === 'insights') loadBraveSearchStatus().catch((error) => status('#research-settings-status', error.message, true));
  } catch (error) { status('#dashboard-status', error.message, true); }
}

initializePositionControls();
window.setInterval(() => {
  if (state.token && state.businessId) checkFolderImports();
}, 10000);
$('#logout').addEventListener('click', async () => { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }); window.location.replace('/'); });
$$('.nav-link').forEach((link) => link.addEventListener('click', () => navigate(link.dataset.page)));
$('#dataset-select').addEventListener('change', async () => {
  await refreshViews();
  if (state.page === 'catalogue') await loadCatalogue();
});
$('#refresh-dashboard').addEventListener('click', refreshViews);
$('#print-report-button').addEventListener('click', printFinancialReport);
$('#run-performance-research').addEventListener('click', runPerformanceResearch);
$('#research-settings-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const apiKey = $('#brave-search-key').value;
  if (!apiKey) {
    status('#research-settings-status', 'Enter a Brave Search API key first.', true);
    return;
  }
  try {
    await request(`/api/businesses/${state.businessId}/integrations/brave-search`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    $('#brave-search-key').value = '';
    await loadBraveSearchStatus();
    status('#research-settings-status', 'Brave Search connection saved. The key is encrypted and will not be shown again.');
    maybeRunPerformanceResearch();
  } catch (error) {
    status('#research-settings-status', error.message, true);
  }
});
$('#remove-brave-key').addEventListener('click', async () => {
  try {
    await request(`/api/businesses/${state.businessId}/integrations/brave-search`, { method: 'DELETE' });
    state.marketResearch = null;
    $('#research-results').replaceChildren();
    await loadBraveSearchStatus();
    status('#research-settings-status', 'Brave Search connection removed.');
  } catch (error) {
    status('#research-settings-status', error.message, true);
  }
});
$('#refresh-position').addEventListener('click', loadFinancialPosition);
$('#position-report-date').addEventListener('change', loadFinancialPosition);
$('#position-balance-form').addEventListener('submit', savePositionBalance);
$('#position-category').addEventListener('change', (event) => {
  const isEquity = positionCategories[event.target.value]?.[0] === 'equity';
  $('#position-amount').min = isEquity ? '' : '0';
});
$('#print-position-report').addEventListener('click', printFinancialPosition);
$('#date-preset').addEventListener('change', async (event) => { const custom = event.target.value === 'custom'; $('#from-date').disabled = !custom; $('#to-date').disabled = !custom; await refreshViews(); });
$$('.period-tab').forEach((tab) => tab.addEventListener('click', () => { state.trendPeriod = tab.dataset.period; $$('.period-tab').forEach((button) => { const active = button === tab; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); }); renderDashboardTrend(); }));
$('#view-all-insights').addEventListener('click', () => navigate('insights'));
$('#manage-inventory').addEventListener('click', () => navigate('inventory'));
$('#inventory-product-reset').addEventListener('click', resetInventoryProductForm);
$('#inventory-search').addEventListener('input', renderInventoryProducts);
$('#inventory-include-archived').addEventListener('change', () => loadInventory().catch((error) => status('#inventory-status', error.message, true)));
$('#print-inventory-report').addEventListener('click', printInventoryReport);
$('#inventory-movement-type').addEventListener('change', (event) => {
  const adjustment = event.target.value === 'adjustment';
  $('#inventory-movement-quantity-label').lastElementChild.min = adjustment ? '' : '0.000001';
  $('#inventory-movement-quantity-label').lastElementChild.placeholder = adjustment ? 'Positive adds; negative removes' : 'Enter a positive quantity';
});
$('#inventory-product-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = $('#inventory-product-submit');
  submit.disabled = true;
  const unitCost = $('#inventory-product-cost').value;
  const common = {
    name: $('#inventory-product-name').value,
    sku: $('#inventory-product-sku').value || null,
    unit: $('#inventory-product-unit').value,
    unit_cost: unitCost === '' ? null : Number(unitCost),
    reorder_level: Number($('#inventory-product-reorder').value),
  };
  try {
    const editing = state.editingInventoryProduct;
    await request(
      editing
        ? `/api/businesses/${state.businessId}/inventory/products/${editing}`
        : `/api/businesses/${state.businessId}/inventory/products`,
      {
        method: editing ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editing ? common : { ...common, opening_stock: Number($('#inventory-product-opening').value) }),
      },
    );
    resetInventoryProductForm();
    await loadInventory();
    status('#inventory-status', editing ? 'Product details saved.' : 'Product added to inventory.');
  } catch (error) {
    status('#inventory-status', error.message, true);
  } finally {
    submit.disabled = false;
  }
});
$('#inventory-movement-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = $('#inventory-movement-submit');
  submit.disabled = true;
  try {
    const productId = $('#inventory-movement-product').value;
    const result = await request(`/api/businesses/${state.businessId}/inventory/products/${productId}/movements`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        movement_type: $('#inventory-movement-type').value,
        quantity: Number($('#inventory-movement-quantity').value),
        note: $('#inventory-movement-note').value,
      }),
    });
    const movementType = $('#inventory-movement-type').value;
    const selectedProduct = $('#inventory-movement-product').value;
    $('#inventory-movement-form').reset();
    $('#inventory-movement-type').value = movementType;
    $('#inventory-movement-type').dispatchEvent(new Event('change'));
    await loadInventory();
    $('#inventory-movement-product').value = selectedProduct;
    status('#inventory-status', `Stock movement recorded. ${result.name}: ${quantity(result.quantity_on_hand)} ${result.unit} on hand.`);
  } catch (error) {
    status('#inventory-status', error.message, true);
  } finally {
    submit.disabled = !$('#inventory-movement-product').value;
  }
});
$('#inventory-import-file').addEventListener('change', () => {
  $('#inventory-import-submit').disabled = !$('#inventory-import-file').files.length;
});
$('#inventory-template-download').addEventListener('click', (event) => {
  event.preventDefault();
  const blob = new Blob(['product,sku,unit,quantity_on_hand,unit_cost,reorder_level\n'], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'inventory-stocktake-template.csv';
  link.click();
  URL.revokeObjectURL(url);
});
$('#inventory-import-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = $('#inventory-import-file').files[0];
  if (!file) return;
  const submit = $('#inventory-import-submit');
  submit.disabled = true;
  status('#inventory-import-status', 'Validating and reconciling stocktake...');
  try {
    const body = new FormData();
    body.append('file', file);
    const result = await request(`/api/businesses/${state.businessId}/inventory/import`, { method: 'POST', body });
    await loadInventory();
    status('#inventory-import-status', `Stocktake imported: ${result.created} created, ${result.updated} updated, ${result.rows_imported} rows reconciled.`);
  } catch (error) {
    status('#inventory-import-status', error.message, true);
  } finally {
    submit.disabled = !$('#inventory-import-file').files.length;
  }
});
function updateSelectedFile() {
  const file = $('#dataset-file').files[0];
  $('#selected-file-name').textContent = file ? `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB` : 'No file selected';
  $('#upload-button').disabled = !file;
}

$('#dataset-file').addEventListener('change', updateSelectedFile);
$('#upload-drop-zone').addEventListener('dragover', (event) => { event.preventDefault(); event.currentTarget.classList.add('drag-over'); });
$('#upload-drop-zone').addEventListener('dragleave', (event) => { event.currentTarget.classList.remove('drag-over'); });
$('#upload-drop-zone').addEventListener('drop', (event) => {
  event.preventDefault();
  event.currentTarget.classList.remove('drag-over');
  const [file] = event.dataTransfer.files;
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  $('#dataset-file').files = transfer.files;
  updateSelectedFile();
});
$('#upload-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = $('#upload-button');
  const file = $('#dataset-file').files[0];
  if (!file) { status('#upload-status', 'Choose a CSV or Excel file first.', true); return; }
  submit.disabled = true;
  status('#upload-status', 'Checking and importing your file...');
  $('#upload-result').hidden = true;
  const body = new FormData();
  body.append('file', file);
  try {
    const result = await request(`/api/businesses/${state.businessId}/datasets`, { method: 'POST', body });
    status('#upload-status', result.status === 'failed' ? 'Import needs attention.' : 'Import complete.');
    const outcome = $('#upload-result');
    outcome.replaceChildren();
    outcome.hidden = false;
    outcome.append(cell('strong', result.status === 'processed' ? 'All rows imported' : result.status === 'partial' ? 'Import completed with rejected rows' : 'File could not be imported'));
    const counts = document.createElement('div');
    counts.className = 'upload-counts';
    [['Source rows', result.source_rows], ['Accepted', result.accepted_rows], ['Rejected', result.rejected_rows]].forEach(([label, value]) => {
      const count = document.createElement('div');
      count.append(cell('span', label), cell('strong', Number(value).toLocaleString()));
      counts.append(count);
    });
    outcome.append(counts);
    (result.errors || []).forEach((message) => {
      const note = cell('p', message);
      note.className = 'upload-warning';
      outcome.append(note);
    });
    if (result.warnings?.length) {
      const details = document.createElement('details');
      const summary = cell('summary', `Row warnings (${result.warnings.length})`);
      const warningList = document.createElement('ul');
      result.warnings.slice(0, 12).forEach((message) => warningList.append(cell('li', message)));
      if (result.warnings.length > 12) warningList.append(cell('li', `${result.warnings.length - 12} more warnings not shown here.`));
      details.append(summary, warningList);
      outcome.append(details);
    }
    await loadHistory();
    $('#dataset-select').value = result.id;
    await refreshViews();
    const dashboardLink = cell('button', 'View updated dashboard');
    dashboardLink.type = 'button';
    dashboardLink.addEventListener('click', () => navigate('dashboard'));
    outcome.append(dashboardLink);
  } catch (error) {
    status('#upload-status', error.message, true);
  } finally {
    submit.disabled = !$('#dataset-file').files.length;
  }
});
$('#profile-form').addEventListener('submit', async (event) => { event.preventDefault(); try { const identity = await request('/api/auth/profile', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ full_name: $('#profile-name').value, business_name: $('#profile-business').value }) }); state.businessId = identity.business.id; $('#business-name').textContent = identity.business.name; status('#profile-status', 'Profile saved.'); } catch (error) { status('#profile-status', error.message, true); } });
$('#question-grid').addEventListener('click', async (event) => { if (!event.target.dataset.question || !selectedDataset()) return; try { const result = await request(`/api/businesses/${state.businessId}/questions/${event.target.dataset.question}?${filterParams()}`); renderQuestionAnswer(result); } catch (error) { status('#insight-status', error.message, true); } });
$('#view-catalogue').addEventListener('click', () => navigate('catalogue'));
$('#catalogue-search').addEventListener('input', renderCatalogue);
$('#catalogue-sort').addEventListener('change', renderCatalogue);
$('#ask-form').addEventListener('submit', async (event) => { event.preventDefault(); await askLance(); });
$('#new-chat').addEventListener('click', startConversation);
window.addEventListener('hashchange', () => { navigate(location.hash.slice(1)); if (state.page === 'catalogue') loadCatalogue().catch((error) => { $('#catalogue-summary').textContent = error.message; }); if (state.page === 'inventory') loadInventory().catch((error) => status('#inventory-status', error.message, true)); if (state.page === 'financial-position') loadFinancialPosition(); if (state.page === 'insights') loadBraveSearchStatus().catch((error) => status('#research-settings-status', error.message, true)); if (state.page === 'profile') loadProfile().catch((error) => status('#profile-status', error.message, true)); if (state.page === 'ask-lance') loadConversations().catch((error) => status('#ask-status', error.message, true)); });
$$('.nav-link').forEach((link) => link.addEventListener('click', () => { if (link.dataset.page === 'profile') loadProfile().catch((error) => status('#profile-status', error.message, true)); }));
bootstrap();
