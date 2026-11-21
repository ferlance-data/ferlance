// Products: the full ranked catalogue of items found in imports (replaces the old
// "catalogue" page and the top/worst modal with one searchable, sortable table).

import { request } from '../api.js';
import { $, emptyState, h, money, mount, number, plainPercent, pressGroup, setCurrency, skeletonRows, table } from '../dom.js';
import { analysableDatasets, businessPath, scopeHasData, scopeParams, state } from '../state.js';

let analytics = null;
let sort = { key: 'revenue', dir: 'desc' };
let filter = 'all';
let requestId = 0;

export const view = {
  title: 'Products',
  description: 'Every product or service in your records, ranked by what it earns and what it costs.',
  scoped: true,
  init() {
    $('#products-search').addEventListener('input', render);
    pressGroup($('#products-filter'), 'filter', (value) => {
      filter = value;
      render();
    });
  },
  load,
};

const value = (item, key) => {
  if (key === 'product') return item.product.toLocaleLowerCase();
  const raw = item[key];
  return raw === undefined || raw === null ? Number.NEGATIVE_INFINITY : raw;
};

function setSort(key) {
  sort = { key, dir: sort.key === key && sort.dir === 'desc' ? 'asc' : key === 'product' ? 'asc' : 'desc' };
  render();
}

function render() {
  const target = $('#products-table');
  if (!analytics) return;
  const products = analytics.products;
  if (!products?.available) {
    mount(target, emptyState('No products found', products?.reason || 'Add a product, item or service column to your imports.'));
    $('#products-count').textContent = '';
    return;
  }
  const query = $('#products-search').value.trim().toLocaleLowerCase();
  const total = products.items.reduce((sum, item) => sum + Math.max(item.metric_value, 0), 0);
  let rows = products.items.filter((item) => item.product.toLocaleLowerCase().includes(query));
  if (filter === 'profit') rows = rows.filter((item) => (item.gross_profit ?? 0) > 0);
  if (filter === 'loss') rows = rows.filter((item) => (item.gross_profit ?? 0) < 0);
  rows.sort((a, b) => {
    const [x, y] = [value(a, sort.key), value(b, sort.key)];
    const order = typeof x === 'string' ? x.localeCompare(y) : x - y;
    return sort.dir === 'asc' ? order : -order;
  });
  $('#products-count').textContent = `${number(rows.length)} of ${number(products.items.length)}`;
  const profitable = products.profit_available;
  const columns = [
    {
      label: 'Product',
      sort: 'product',
      value: (item) => h('div', { class: 'rank-name' }, h('strong', {}, item.product), h('span', { class: 'share-bar', title: `${((item.metric_value / (total || 1)) * 100).toFixed(1)}% of total` }, h('i', { style: { width: `${Math.max(1, (Math.max(item.metric_value, 0) / (total || 1)) * 100)}%` } }))),
    },
    { label: products.metric_label, num: true, sort: 'metric_value', value: (item) => money(item.metric_value) },
    profitable ? { label: 'Cost', num: true, sort: 'cost', value: (item) => money(item.cost) } : null,
    profitable ? { label: 'Profit / loss', num: true, sort: 'gross_profit', value: (item) => h('span', { class: item.gross_profit < 0 ? 'negative' : '' }, money(item.gross_profit)) } : null,
    profitable ? { label: 'Margin', num: true, sort: 'margin_pct', value: (item) => plainPercent(item.margin_pct) } : null,
    profitable ? { label: 'ROI', num: true, sort: 'roi_pct', value: (item) => plainPercent(item.roi_pct) } : null,
    products.quantity_available ? { label: 'Units', num: true, sort: 'units_sold', value: (item) => number(item.units_sold, 2) } : null,
    { label: 'Records', num: true, sort: 'transactions', value: (item) => number(item.transactions) },
  ].filter(Boolean);
  mount(target, table(columns, rows, { empty: query || filter !== 'all' ? 'No products match.' : 'No products in this period.', sortState: sort, onSort: setSort }));
  if (!profitable && analytics.profile?.domain !== 'cost') {
    target.append(h('p', { class: 'footnote', style: { padding: '10px 14px' } }, 'Profit, margin and ROI appear when every product record includes a cost or unit cost.'));
  }
}

async function load() {
  if (!scopeHasData()) {
    analytics = null;
    mount($('#products-table'), emptyState('No products yet', 'Import a sales file with a product column.', h('a', { class: 'btn btn-primary btn-sm', href: '#data' }, 'Import data')));
    return;
  }
  const id = ++requestId;
  mount($('#products-table'), h('div', { style: { padding: '8px 14px' } }, skeletonRows(6)));
  const result = await request(businessPath(`/analytics?${scopeParams()}`));
  if (id !== requestId) return;
  analytics = result;
  state.bounds = result.available_period;
  setCurrency(result.currency);
  render();
}
