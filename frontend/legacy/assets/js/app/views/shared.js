// Rendering shared across views.

import { h, icon, money, number, pill, plainPercent } from '../dom.js';

const SEVERITY = {
  positive: ['success', 'Positive'],
  attention: ['warning', 'Needs attention'],
  info: ['info', 'Info'],
};
const TYPE_LABEL = { summary: 'Summary', comparison: 'Comparison', anomaly: 'Signal', recommendation: 'Focus' };
const MONEY_KEYS = new Set(['total', 'revenue', 'current', 'previous', 'average_sale', 'gross_profit', 'cost', 'metric_value']);
const HIDDEN_KEYS = new Set(['metric_label', 'metric_value', 'direction', 'currency', 'product']);

function evidenceValue(key, value) {
  if (typeof value === 'number' && MONEY_KEYS.has(key)) return money(value);
  if (key.endsWith('_pct') || key === 'percent') return value === null ? '—' : plainPercent(value, 2);
  if (typeof value === 'number') return number(value, 2);
  return String(value);
}

export function insightCard(item, { compact = false } = {}) {
  const [tone, label] = SEVERITY[item.severity] || SEVERITY.info;
  const evidence = Object.entries(item.supporting_metric || {})
    .filter(([key, value]) => value !== null && value !== undefined && typeof value !== 'object' && !HIDDEN_KEYS.has(key))
    .slice(0, compact ? 3 : 8)
    .map(([key, value]) => h('span', { class: 'evidence' }, h('small', {}, key.replaceAll('_', ' ')), h('strong', {}, evidenceValue(key, value))));
  return h(
    'article',
    { class: 'insight' },
    h('div', { class: 'insight-head' }, h('h3', {}, item.title), h('span', { style: { display: 'flex', gap: '6px' } }, pill(TYPE_LABEL[item.type] || item.type), pill(label, tone))),
    h('p', {}, item.message),
    evidence.length ? h('div', { class: 'insight-evidence' }, evidence) : null,
    !compact && item.limitations?.length ? h('p', { class: 'insight-note' }, item.limitations.join(' ')) : null,
  );
}

/** Ranked list with a share-of-total bar, as used for products and customers. */
export function rankList(items, { name, value, total, sub = null, empty = 'Nothing to rank yet.' }) {
  if (!items.length) return [h('li', { class: 'empty-state' }, empty)];
  const max = Math.max(...items.map((item) => Math.abs(value(item))), 1);
  return items.map((item, index) => h(
    'li',
    { class: 'rank-item' },
    h('span', { class: 'rank-index' }, String(index + 1).padStart(2, '0')),
    h('span', { class: 'rank-name' }, h('strong', { title: name(item) }, name(item)), h('span', { class: 'share-bar' }, h('i', { style: { width: `${Math.max(2, (Math.abs(value(item)) / max) * 100)}%` } }))),
    h('span', { class: 'rank-value' }, money(value(item)), h('small', {}, sub ? sub(item) : total ? `${((value(item) / total) * 100).toFixed(1)}% of total` : '')),
  ));
}

export function statusPill(dataset) {
  if (dataset.status === 'failed') return pill('Failed', 'error');
  if (dataset.status === 'partial') return pill(`${number(dataset.rejected_rows)} rejected`, 'warning');
  return pill('Processed', 'success');
}

export function attentionItem({ tone, iconName, title, href, detail }) {
  return h(
    'li',
    { class: `attention-item tone-${tone}` },
    h('span', { class: 'attention-icon' }, icon(iconName)),
    h('div', {}, href ? h('a', { href }, title) : h('strong', {}, title), detail ? h('p', {}, detail) : null),
  );
}
