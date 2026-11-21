// Printable reports. Each builder fills #print-report, then the browser prints it.

import { $, formatDate, formatDateTime, h, money, number, plainPercent } from './dom.js';
import { state } from './state.js';

const POSITION_LABELS = {
  cash: 'Cash on hand',
  bank: 'Cash at bank',
  receivables: 'Accounts receivable',
  inventory: 'Inventory at recorded cost',
  fixed_assets: 'Fixed assets',
  other_assets: 'Other assets',
  payables: 'Accounts payable',
  loans: 'Loans and borrowings',
  other_liabilities: 'Other liabilities',
  owner_capital: 'Owner capital',
  retained_earnings: 'Retained earnings / accumulated loss',
  other_equity: 'Other equity',
};
export { POSITION_LABELS };

function section(title, headers, rows, note = null) {
  return h(
    'section',
    {},
    h('h2', {}, title),
    rows.length
      ? h('table', {}, h('thead', {}, h('tr', {}, headers.map((label) => h('th', {}, label)))), h('tbody', {}, rows.map((row) => h('tr', {}, row.map((value) => h('td', {}, value))))))
      : h('p', { class: 'note' }, 'No data for this section.'),
    note ? h('p', { class: 'note' }, note) : null,
  );
}

function header(kind, title, lines) {
  return h('header', {}, h('p', {}, `FERLANCE · ${kind}`), h('h1', {}, title), lines.map((line) => h('p', {}, line)));
}

function print(children) {
  const report = $('#print-report');
  report.replaceChildren(...children);
  report.hidden = false;
  document.body.classList.add('printing');
  const done = () => {
    document.body.classList.remove('printing');
    report.hidden = true;
    window.removeEventListener('afterprint', done);
  };
  window.addEventListener('afterprint', done);
  window.print();
}

export function printFinancialReport(analytics, insights) {
  if (!analytics) return;
  const isCost = analytics.profile?.domain === 'cost';
  const profit = analytics.profit;
  const comparison = analytics.comparison;
  const period = `${formatDate(analytics.period.from)} – ${formatDate(analytics.period.to)}`;
  const rows = [
    ['Revenue', money(analytics.revenue.total)],
    ['Recorded costs', money(analytics.kpis.total_cost)],
    ['Profit after recorded costs', profit.available ? money(profit.gross_profit) : `Unavailable — ${profit.reason}`],
    ['Return on recorded costs', profit.available && profit.cost > 0 ? plainPercent((profit.gross_profit / profit.cost) * 100, 2) : 'Unavailable'],
    ['Average sale', money(analytics.revenue.average_sale)],
    ['Records', number(analytics.revenue.transactions)],
  ];
  const comparisonRows = comparison?.available
    ? Object.entries(comparison.metrics).map(([key, metric]) => [key.replaceAll('_', ' '), metric.current === null ? '—' : key === 'transactions' ? number(metric.current) : money(metric.current), metric.previous === null ? '—' : key === 'transactions' ? number(metric.previous) : money(metric.previous), metric.change_pct === null ? '—' : plainPercent(metric.change_pct)])
    : [];
  const products = analytics.products?.available ? analytics.products.items : [];
  const customers = analytics.customers?.available ? analytics.customers.top_customers : [];
  print([
    header('FINANCIAL REPORT', state.business.name, [
      `Data: ${analytics.dataset?.filename || 'All business data'} · Period: ${period}`,
      `Prepared ${formatDateTime(new Date())} by ${state.user.email}`,
    ]),
    h('section', {}, h('h2', {}, 'Summary'), h('p', {}, analytics.summary)),
    section('Financial summary', ['Measure', 'Value'], rows, 'Profit uses only the costs recorded in your imports. It is not a statutory income statement: overheads, tax, financing and currency conversion are not included.'),
    comparison?.available ? section(`Compared with ${formatDate(comparison.previous_period.from)} – ${formatDate(comparison.previous_period.to)}`, ['Measure', 'This period', 'Previous period', 'Change'], comparisonRows) : null,
    section('Item performance', ['Item', 'Revenue', 'Cost', 'Profit / loss', 'Margin', 'Units', 'Records'], products.map((item) => [item.product, money(item.revenue), item.cost === undefined ? '—' : money(item.cost), item.gross_profit === undefined ? '—' : money(item.gross_profit), item.margin_pct === undefined ? '—' : plainPercent(item.margin_pct), item.units_sold ?? '—', number(item.transactions)])),
    section(isCost ? 'Suppliers' : 'Customers', [isCost ? 'Supplier' : 'Customer', isCost ? 'Cost' : 'Revenue', 'Records'], customers.map((item) => [item.customer, money(item.metric_value), number(item.transactions)])),
    section('Insights', ['Insight', 'Finding'], (insights?.insights || []).map((item) => [item.title, item.message])),
    (analytics.warnings || []).length ? h('section', {}, h('h2', {}, 'Data notes'), h('ul', {}, analytics.warnings.map((note) => h('li', {}, note)))) : null,
    h('p', { class: 'note' }, 'Prepared from accepted records in Ferlance. Verify source data and consult a qualified accountant before using this report for statutory or tax purposes.'),
  ].filter(Boolean));
}

export function printInventoryReport(inventory, movements) {
  const summary = inventory.summary;
  print([
    header('INVENTORY', 'Inventory report', [`${state.business.name} · Prepared ${formatDateTime(new Date())} by ${state.user.email}`]),
    section('Stock overview', ['Measure', 'Value'], [
      ['Active products', number(summary.product_count)],
      ['Units on hand', number(summary.units_on_hand, 3)],
      ['At or below reorder level', number(summary.low_stock_count)],
      ['Stock value', summary.inventory_value_complete ? money(summary.inventory_value) : 'Unavailable — some stock has no unit cost'],
    ]),
    section('Products', ['Product', 'SKU', 'On hand', 'Unit', 'Unit cost', 'Status'], inventory.items.map((item) => [item.name, item.sku || '—', number(item.quantity_on_hand, 3), item.unit, item.unit_cost === null ? 'Not set' : money(item.unit_cost), !item.active ? 'Archived' : item.low_stock ? 'Low stock' : 'In stock'])),
    section('Recent movements', ['Date', 'Product', 'Type', 'Change', 'Note'], movements.map((item) => [formatDateTime(item.created_at), item.product_name, item.movement_type, `${item.quantity_delta > 0 ? '+' : ''}${number(item.quantity_delta, 3)} ${item.unit}`, item.note || '—'])),
    h('p', { class: 'note' }, 'Quantities reflect recorded opening stock, purchases, sales, adjustments and stocktakes only. Verify physical counts before relying on this report.'),
  ]);
}

export function printPositionReport(result) {
  const groupRows = (items) => items.map((item) => [item.account_name, POSITION_LABELS[item.category] || item.category, money(item.amount), formatDate(item.as_of_date)]);
  const totals = result.totals;
  print([
    header('FINANCIAL POSITION', 'Statement of financial position', [`${state.business.name} · As of ${formatDate(result.as_of_date)}`, `Prepared ${formatDateTime(new Date())} by ${state.user.email}`]),
    section('Assets', ['Account', 'Category', 'Balance', 'Balance date'], groupRows(result.assets)),
    section('Liabilities', ['Account', 'Category', 'Balance', 'Balance date'], groupRows(result.liabilities)),
    section('Equity', ['Account', 'Category', 'Balance', 'Balance date'], groupRows(result.equity)),
    section('Totals', ['Measure', 'Value'], [
      ['Total assets', money(totals.assets)],
      ['Total liabilities', money(totals.liabilities)],
      ['Total equity', money(totals.equity)],
      ['Assets − liabilities − equity', money(totals.balance_difference)],
      ['Completeness', totals.complete ? 'Every category has a balance' : `Partial — missing ${result.missing_categories.map((item) => item.label).join(', ')}`],
      ['Accounting equation', totals.balanced ? 'Balances' : 'Not verified as balanced'],
    ]),
    h('p', { class: 'note' }, 'Each account uses its latest balance on or before the report date. Missing balances are not assumed to be zero. This operational statement is not a substitute for accountant-reviewed financial statements.'),
  ]);
}
