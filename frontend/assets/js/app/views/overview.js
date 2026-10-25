// Overview: KPIs with period comparison, trend, attention list, rankings, insights, stock.

import { request } from '../api.js';
import { renderBarChart } from '../chart.js';
import { $, $$, delta, emptyState, h, icon, kpi, money, mount, number, plainPercent, plural, pressGroup, setCurrency, skeletonRows } from '../dom.js';
import { printFinancialReport } from '../reports.js';
import { analysableDatasets, businessPath, scopeHasData, resolveRange, scopeParams, state } from '../state.js';
import { attentionItem, insightCard, rankList } from './shared.js';

const PERIOD_LABEL = { daily: 'day', weekly: 'week', monthly: 'month', quarterly: 'quarter', yearly: 'year' };
let trendPeriod = 'weekly';
let latest = { analytics: null, insights: null };
let requestId = 0;

export const view = {
  title: 'Overview',
  description: 'How the business is doing for the data and dates you choose, compared with the period before.',
  scoped: true,
  actions: () => [
    h('button', { class: 'btn btn-secondary', type: 'button', id: 'print-financial', disabled: !latest.analytics, onclick: () => printFinancialReport(latest.analytics, latest.insights) }, icon('printer'), h('span', { class: 'btn-label' }, 'Print report')),
  ],
  init() {
    pressGroup($('#trend-periods'), 'period', (period) => {
      trendPeriod = period;
      renderTrend();
    });
  },
  load,
};

function setupSteps() {
  return [
    { done: analysableDatasets().length > 0, title: 'Import your sales records', detail: 'A spreadsheet export or pasted Mobile Money alerts.', href: '#data', action: 'Import' },
    { done: (state.inventory?.summary.product_count || 0) > 0, title: 'Add the products you stock', detail: 'Get low-stock alerts and a stock value.', href: '#inventory', action: 'Add products' },
    { done: state.setup.balances, title: 'Record your cash and bank balances', detail: 'Unlock a statement of financial position.', href: '#position', action: 'Record' },
    { done: state.setup.conversations, title: 'Ask Lance a question', detail: '“Which products made the most profit last month?”', href: '#lance', action: 'Ask' },
  ];
}

function renderSetup() {
  const target = $('#overview-setup');
  const steps = setupSteps();
  const complete = steps.filter((step) => step.done).length;
  const dismissKey = `ferlance-setup-dismissed:${state.business.id}`;
  let dismissed = false;
  try { dismissed = localStorage.getItem(dismissKey) === '1'; } catch { /* storage unavailable */ }
  if (complete === steps.length || (dismissed && complete > 0)) {
    target.replaceChildren();
    return;
  }
  mount(
    target,
    h(
      'section',
      { class: 'setup', 'aria-label': 'Setup guide' },
      h(
        'div',
        {},
        h('p', { class: 'eyebrow' }, 'Setup guide'),
        h('h2', {}, complete ? 'Keep going — your numbers get sharper with each step.' : `Welcome to Ferlance, ${state.business.name}.`),
        h('p', {}, 'Four short steps turn your records into a full picture of the business.'),
        h('div', { class: 'setup-progress', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': steps.length, 'aria-valuenow': complete }, h('i', { style: { width: `${(complete / steps.length) * 100}%` } })),
        h('p', { class: 'footnote', style: { marginTop: '8px' } }, `${complete} of ${steps.length} complete`),
        complete ? h('button', { class: 'btn btn-ghost btn-sm', type: 'button', style: { marginTop: '10px', marginLeft: '-10px' }, onclick: () => { try { localStorage.setItem(dismissKey, '1'); } catch { /* ignore */ } target.replaceChildren(); } }, 'Hide guide') : null,
      ),
      h(
        'ol',
        { class: 'setup-steps' },
        steps.map((step) => h(
          'li',
          { class: `setup-step${step.done ? ' done' : ''}` },
          h('span', { class: 'setup-check' }, step.done ? icon('check') : null),
          h('div', {}, h('strong', {}, step.title), h('p', {}, step.detail)),
          step.done ? null : h('a', { class: 'btn btn-secondary btn-sm', href: step.href }, step.action),
        )),
      ),
    ),
  );
}

function compareFoot(comparison, key, { invert = false } = {}) {
  if (!comparison?.available) return h('span', {}, comparison?.previous_period ? 'No earlier period to compare' : 'Choose a date range to compare');
  const metric = comparison.metrics[key];
  if (!metric || metric.change_pct === null) return h('span', {}, 'No comparable value');
  const previous = key === 'transactions' ? number(metric.previous) : money(metric.previous, { compact: true });
  return [delta(metric.change_pct, { invert }), h('span', {}, `vs ${previous}`)];
}

function renderKpis(result) {
  const isCost = result.profile?.domain === 'cost';
  const comparison = result.comparison;
  const cards = isCost
    ? [
      kpi({ label: 'Total cost', value: money(result.kpis.total_cost), foot: compareFoot(comparison, 'cost', { invert: true }), iconName: 'receipt' }),
      kpi({ label: 'Records', value: number(result.kpis.transactions), foot: compareFoot(comparison, 'transactions'), iconName: 'file' }),
      kpi({ label: 'Average cost', value: money(result.kpis.transactions ? result.kpis.total_cost / result.kpis.transactions : 0), foot: 'Per record', iconName: 'coins' }),
      kpi({ label: 'Largest cost item', value: result.kpis.top_product || '—', text: true, foot: 'By recorded cost', iconName: 'products' }),
    ]
    : [
      kpi({ label: 'Revenue', value: money(result.kpis.total_revenue), foot: compareFoot(comparison, 'revenue'), iconName: 'trending-up' }),
      result.profit.available
        ? kpi({ label: 'Profit after costs', value: money(result.profit.gross_profit), foot: [compareFoot(comparison, 'gross_profit'), h('span', {}, `· ${plainPercent(result.profit.revenue ? (result.profit.gross_profit / result.profit.revenue) * 100 : 0)} margin`)], iconName: 'coins' })
        : kpi({ label: 'Profit after costs', value: 'Needs costs', text: true, foot: 'Add a cost column to every record', iconName: 'coins' }),
      kpi({ label: 'Sales', value: number(result.kpis.transactions), foot: compareFoot(comparison, 'transactions'), iconName: 'receipt' }),
      kpi({ label: 'Average sale', value: money(result.kpis.average_sale), foot: compareFoot(comparison, 'average_sale'), iconName: 'users' }),
    ];
  mount($('#overview-kpis'), cards);
}

function renderTrend() {
  const result = latest.analytics;
  if (!result) return;
  const isCost = result.profile?.domain === 'cost';
  const series = (result.trend[isCost ? `cost_${trendPeriod}` : trendPeriod] || []).map((item) => ({ period: item.period, value: isCost ? item.cost : item.revenue, transactions: item.transactions }));
  const costSeries = !isCost ? result.trend[`cost_${trendPeriod}`] || [] : [];
  const line = costSeries.length ? new Map(costSeries.map((item) => [item.period, item.cost])) : null;
  $('#trend-title').textContent = isCost ? 'Cost trend' : line ? 'Revenue and cost' : 'Revenue trend';
  $('#trend-subtitle').textContent = `Grouped by ${PERIOD_LABEL[trendPeriod]} · ${plural(series.length, 'period')}`;
  renderBarChart($('#trend-chart'), series, { line, barLabel: isCost ? 'Cost' : 'Revenue', lineLabel: 'Cost' });
  mount(
    $('#trend-legend'),
    h('span', {}, h('i', { style: { background: 'var(--chart-revenue)' } }), isCost ? 'Cost' : 'Revenue'),
    line ? h('span', {}, h('i', { style: { background: 'var(--chart-cost)' } }), 'Recorded cost') : null,
  );
}

function renderAttention(result, insights) {
  const items = [];
  const lowStock = (state.inventory?.items || []).filter((item) => item.active && item.low_stock);
  lowStock.slice(0, 3).forEach((item) => items.push({ tone: 'warning', iconName: 'inventory', title: `${item.name} is low on stock`, detail: `${number(item.quantity_on_hand, 2)} ${item.unit} on hand · reorder at ${number(item.reorder_level, 2)}`, href: '#inventory' }));
  if (lowStock.length > 3) items.push({ tone: 'warning', iconName: 'inventory', title: `${lowStock.length - 3} more products are low on stock`, href: '#inventory' });
  (result.products?.rankings?.loss || []).slice(0, 2).forEach((item) => items.push({ tone: 'error', iconName: 'trending-down', title: `${item.product} sold below cost`, detail: `Loss of ${money(Math.abs(item.gross_profit))} on ${money(item.revenue)} revenue`, href: '#products' }));
  (insights?.insights || []).filter((item) => item.title === 'Product decline').slice(0, 2).forEach((item) => items.push({ tone: 'warning', iconName: 'trending-down', title: item.message, href: '#insights' }));
  if (insights?.revenue_change?.direction === 'down' && insights.revenue_change.percent !== null) {
    items.unshift({ tone: 'warning', iconName: 'trending-down', title: `Revenue fell ${Math.abs(insights.revenue_change.percent).toFixed(1)}% on the previous period`, detail: `${money(insights.revenue_change.current)} vs ${money(insights.revenue_change.previous)}`, href: '#insights' });
  }
  state.datasets.filter((item) => item.included && item.warnings.some((warning) => warning.includes('identical to'))).slice(0, 2).forEach((item) => items.push({ tone: 'warning', iconName: 'file', title: `${item.filename} may be a duplicate`, detail: 'Switch one copy off in Data imports to avoid double counting.', href: '#data' }));
  state.datasets.filter((item) => item.status === 'partial' && item.included).slice(0, 2).forEach((item) => items.push({ tone: 'info', iconName: 'file', title: `${plural(item.rejected_rows, 'row')} rejected in ${item.filename}`, detail: 'Every rejected row is listed with its reason.', href: '#data' }));
  if (!items.length) items.push({ tone: 'ok', iconName: 'check', title: 'Nothing needs attention right now', detail: 'No losses, declines, duplicate files or low stock detected.' });
  mount($('#attention-list'), items.slice(0, 6).map(attentionItem));
}

function renderRankings(result) {
  const isCost = result.profile?.domain === 'cost';
  const products = result.products?.available ? result.products.items.slice(0, 5) : [];
  $('#top-title').textContent = isCost ? 'Largest cost items' : 'Top products';
  mount($('#top-products'), result.products?.available
    ? rankList(products, {
      name: (item) => item.product,
      value: (item) => item.metric_value,
      total: isCost ? result.kpis.total_cost : result.kpis.total_revenue,
      sub: result.products.profit_available ? (item) => `${money(item.gross_profit, { compact: true })} profit · ${plainPercent(item.margin_pct)}` : null,
    })
    : [h('li', { class: 'empty-state' }, result.products?.reason || 'No product column found.')]);
  $('#customers-title').textContent = isCost ? 'Top suppliers' : 'Top customers';
  const customers = result.customers;
  $('#customers-subtitle').textContent = customers?.available ? `${plural(customers.number_of_customers, isCost ? 'supplier' : 'customer')} · ${number(customers.repeat_customers)} repeat` : 'Highest value relationships';
  mount($('#top-customers'), customers?.available
    ? rankList(customers.top_customers.slice(0, 5), { name: (item) => item.customer, value: (item) => item.metric_value, sub: (item) => plural(item.transactions, 'record') })
    : [h('li', { class: 'empty-state' }, customers?.reason || 'No customer column found.')]);
}

function renderStock() {
  const summary = state.inventory?.summary;
  if (!summary || !summary.product_count) {
    mount($('#overview-stock'), emptyState('No stock tracked yet', 'Add products in Inventory to get low-stock alerts.', h('a', { class: 'btn btn-secondary btn-sm', href: '#inventory' }, 'Set up inventory')));
    $('#overview-stock').style.display = 'block';
    return;
  }
  $('#overview-stock').style.display = '';
  mount(
    $('#overview-stock'),
    [['Products', number(summary.product_count)], ['Units on hand', number(summary.units_on_hand, 2)], ['Low stock', number(summary.low_stock_count)], ['Stock value', summary.inventory_value_complete ? money(summary.inventory_value) : 'Needs unit costs']]
      .map(([label, value]) => h('div', { class: 'mini-stat' }, h('span', {}, label), h('strong', {}, value))),
  );
}

function renderEmpty() {
  latest = { analytics: null, insights: null };
  const print = $('#print-financial');
  if (print) print.disabled = true;
  const allExcluded = analysableDatasets().length > 0;
  mount($('#overview-kpis'), ['Revenue', 'Profit after costs', 'Sales', 'Average sale'].map((label) => kpi({ label, value: '—', foot: allExcluded ? 'All files are switched off' : 'Import data to see this' })));
  mount($('#trend-chart'), allExcluded
    ? emptyState('Every file is switched off', 'Turn at least one file back on in Data imports to see your numbers.', h('a', { class: 'btn btn-primary btn-sm', href: '#data' }, 'Open data imports'))
    : emptyState('Your trend appears here', 'Import a sales file to see revenue over time.', h('a', { class: 'btn btn-primary btn-sm', href: '#data' }, icon('upload'), 'Import data')));
  mount($('#trend-legend'));
  renderAttention({ products: {} }, null);
  mount($('#top-products'), h('li', { class: 'empty-state' }, 'Products appear once you import sales.'));
  mount($('#top-customers'), h('li', { class: 'empty-state' }, 'Customers appear once you import sales.'));
  mount($('#overview-insights'), emptyState('No insights yet', 'Insights are calculated from your imported records.'));
  $('#overview-notes').hidden = true;
}

async function load() {
  renderSetup();
  renderStock();
  if (!scopeHasData()) {
    renderEmpty();
    return;
  }
  const id = ++requestId;
  mount($('#overview-kpis'), Array.from({ length: 4 }, () => h('div', { class: 'kpi' }, skeletonRows(2, 16))));
  const boundsBefore = JSON.stringify(resolveRange());
  const params = scopeParams();
  const [analytics, insights] = await Promise.all([
    request(businessPath(`/analytics?${params}`)),
    request(businessPath(`/insights?${params}`)).catch(() => null),
  ]);
  if (id !== requestId) return;
  state.bounds = analytics.available_period;
  if (JSON.stringify(resolveRange()) !== boundsBefore) {
    load();
    return;
  }
  latest = { analytics, insights };
  setCurrency(analytics.currency);
  const print = $('#print-financial');
  if (print) print.disabled = false;
  renderKpis(analytics);
  renderTrend();
  renderAttention(analytics, insights);
  renderRankings(analytics);
  mount($('#overview-insights'), (insights?.insights || []).slice(0, 3).map((item) => insightCard(item, { compact: true })));
  if (!insights?.insights?.length) mount($('#overview-insights'), emptyState('No insights for this period', 'Try a wider date range.'));
  const notes = analytics.warnings || [];
  $('#overview-notes').hidden = !notes.length;
  mount($('#overview-notes-list'), notes.map((note) => h('li', {}, note)));
  $$('#trend-periods [data-period]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.period === trendPeriod)));
}
