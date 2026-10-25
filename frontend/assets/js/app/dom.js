// DOM building, formatting, and small UI primitives. Everything renders through
// text nodes, so values from uploads can never inject markup.

import { icon } from './icons.js';

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

/** Hyperscript: h('div', { class: 'x', onclick: fn }, child, 'text', [more]) */
export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(node.style, value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else if (key in node && typeof value !== 'string') node[key] = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  append(node, children);
  return node;
}

function append(node, children) {
  children.flat(Infinity).forEach((child) => {
    if (child === null || child === undefined || child === false) return;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  });
}

export function mount(target, ...children) {
  target.replaceChildren();
  append(target, children);
  return target;
}

export { icon };

/* ---------- Formatting ---------- */
let currency = 'GHS';
export const setCurrency = (code) => { currency = code || 'GHS'; };

const moneyFormatters = new Map();
function moneyFormatter(code, compact) {
  const key = `${code}:${compact}`;
  if (!moneyFormatters.has(key)) {
    moneyFormatters.set(
      key,
      new Intl.NumberFormat(code === 'GHS' ? 'en-GH' : 'en-US', {
        style: 'currency',
        currency: code,
        currencyDisplay: 'narrowSymbol',
        notation: compact ? 'compact' : 'standard',
        minimumFractionDigits: compact ? 0 : 2,
        maximumFractionDigits: compact ? 1 : 2,
      }),
    );
  }
  return moneyFormatters.get(key);
}

export function money(value, { compact = false, code = currency } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  try {
    return moneyFormatter(code, compact).format(Number(value));
  } catch {
    return `${code} ${Number(value).toFixed(2)}`;
  }
}

export const number = (value, digits = 0) =>
  value === null || value === undefined ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });

export const percent = (value, digits = 1) =>
  value === null || value === undefined ? '—' : `${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(digits)}%`;

export const plainPercent = (value, digits = 1) =>
  value === null || value === undefined ? '—' : `${Number(value).toFixed(digits)}%`;

export function formatDate(value, options = { day: 'numeric', month: 'short', year: 'numeric' }) {
  if (!value) return '—';
  const date = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('en-GB', options);
}

export const formatDateTime = (value) =>
  value ? new Date(value).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';

export function isoDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export const plural = (count, word, many = `${word}s`) => `${number(count)} ${count === 1 ? word : many}`;

/* ---------- Components ---------- */
export function pill(text, tone = '', iconName = null) {
  return h('span', { class: `pill${tone ? ` pill-${tone}` : ''}` }, iconName ? icon(iconName) : null, text);
}

export function delta(change, { invert = false } = {}) {
  if (change === null || change === undefined) return null;
  const direction = change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
  const good = invert ? direction === 'down' : direction === 'up';
  const tone = direction === 'flat' ? 'flat' : good ? 'up' : 'down';
  return h('span', { class: `delta delta-${tone}` }, direction === 'up' ? '▲' : direction === 'down' ? '▼' : '•', ` ${Math.abs(change).toFixed(1)}%`);
}

export function kpi({ label, value, foot = null, text = false, iconName = null }) {
  return h(
    'div',
    { class: 'kpi' },
    h('span', { class: 'kpi-label' }, iconName ? icon(iconName) : null, label),
    h('span', { class: `kpi-value${text ? ' text' : ''}`, title: typeof value === 'string' ? value : undefined }, value),
    h('span', { class: 'kpi-foot' }, foot),
  );
}

export function emptyState(title, message, action = null) {
  return h('div', { class: 'empty-state' }, h('strong', {}, title), message ? h('span', {}, message) : null, action);
}

export function skeletonRows(count = 3, height = 18) {
  return Array.from({ length: count }, () => h('div', { class: 'skeleton', style: { height: `${height}px`, margin: '8px 0' } }));
}

/**
 * Data table. Columns: { label, value(row) -> node|string, num?: bool, sort?: key }.
 * Pass `sortState` ({ key, dir }) and `onSort(key)` to make headers sortable.
 */
export function table(columns, rows, { empty = 'Nothing to show yet.', sortState = null, onSort = null } = {}) {
  if (!rows.length) return emptyState(empty, null);
  const head = h(
    'tr',
    {},
    columns.map((column) => {
      const sorted = sortState && column.sort && sortState.key === column.sort;
      const th = h('th', { class: column.num ? 'num' : '', scope: 'col', 'aria-sort': sorted ? (sortState.dir === 'asc' ? 'ascending' : 'descending') : null });
      if (column.sort && onSort) {
        th.append(h('button', { type: 'button', onclick: () => onSort(column.sort) }, column.label, sorted ? (sortState.dir === 'asc' ? ' ↑' : ' ↓') : ''));
      } else {
        th.textContent = column.label;
      }
      return th;
    }),
  );
  const body = rows.map((row) => h('tr', {}, columns.map((column) => h('td', { class: column.num ? 'num' : '' }, column.value(row)))));
  return h('table', { class: 'table' }, h('thead', {}, head), h('tbody', {}, body));
}

export function setStatus(target, message, error = false) {
  const node = typeof target === 'string' ? $(target) : target;
  if (!node) return;
  node.textContent = message || '';
  node.classList.toggle('error', Boolean(error));
}

export function toast(message, { error = false } = {}) {
  const node = h('div', { class: `toast${error ? ' error' : ''}`, role: error ? 'alert' : 'status' }, icon(error ? 'alert' : 'check'), h('span', {}, message));
  $('#toasts').append(node);
  setTimeout(() => node.remove(), error ? 6500 : 3500);
}

export function notice(message, tone = 'warning', iconName = 'alert') {
  return h('div', { class: `notice notice-${tone}` }, icon(iconName), h('span', {}, message));
}

/** Wire a segmented tablist whose buttons carry data-tab and panels carry data-panel. */
export function bindTabs(tablist, container, onChange = null) {
  const buttons = $$('[data-tab]', tablist);
  buttons.forEach((button) => button.addEventListener('click', () => {
    buttons.forEach((other) => other.setAttribute('aria-selected', String(other === button)));
    $$('[data-panel]', container).forEach((panel) => { panel.hidden = panel.dataset.panel !== button.dataset.tab; });
    onChange?.(button.dataset.tab);
  }));
}

export function pressGroup(group, attribute, onChange) {
  const buttons = $$(`[data-${attribute}]`, group);
  buttons.forEach((button) => button.addEventListener('click', () => {
    buttons.forEach((other) => other.setAttribute('aria-pressed', String(other === button)));
    onChange(button.dataset[attribute.replace(/-([a-z])/g, (_, c) => c.toUpperCase())]);
  }));
}
