// Insights: deterministic findings, the period comparison, and optional web research.

import { request } from '../api.js';
import { $, delta, emptyState, formatDate, h, money, mount, number, pill, setCurrency, setStatus, skeletonRows } from '../dom.js';
import { analysableDatasets, businessPath, scopeHasData, scopeParams, state } from '../state.js';
import { insightCard } from './shared.js';

let requestId = 0;
let researchConfigured = false;

export const view = {
  title: 'Insights',
  description: 'Findings calculated from your records — every number below can be traced back to an imported row.',
  scoped: true,
  init() {
    $('#research-run').addEventListener('click', runResearch);
  },
  load,
};

const LABELS = { revenue: 'Revenue', cost: 'Recorded cost', gross_profit: 'Profit after costs', transactions: 'Records', average_sale: 'Average sale' };

function renderComparison(comparison) {
  const target = $('#insights-comparison');
  if (!comparison?.available) {
    $('#insights-comparison-period').textContent = 'Against the previous period of equal length';
    mount(target, h('p', { class: 'body-sm muted' }, comparison?.reason || 'Choose a date range to compare.'));
    return;
  }
  $('#insights-comparison-period').textContent = `${formatDate(comparison.period.from)} – ${formatDate(comparison.period.to)} vs ${formatDate(comparison.previous_period.from)} – ${formatDate(comparison.previous_period.to)}`;
  mount(
    target,
    h('div', { class: 'comparison-rows' }, Object.entries(comparison.metrics)
      .filter(([, metric]) => metric.current !== null)
      .map(([key, metric]) => h(
        'div',
        { class: 'comparison-row' },
        h('span', {}, LABELS[key] || key),
        h('span', { class: 'num' }, key === 'transactions' ? number(metric.current) : money(metric.current)),
        delta(metric.change_pct, { invert: key === 'cost' }) || h('span', { class: 'muted body-sm' }, 'new'),
      ))),
  );
}

async function loadResearchStatus() {
  const result = await request(businessPath('/integrations/brave-search'));
  researchConfigured = result.configured;
  const tag = $('#research-pill');
  tag.replaceWith(result.configured ? Object.assign(pill('Connected', 'success'), { id: 'research-pill' }) : Object.assign(pill('Not connected'), { id: 'research-pill' }));
  $('#research-run').disabled = !result.configured || !analysableDatasets().length;
}

function renderResearch(result) {
  const findings = result.findings || [];
  const children = [];
  if (result.analysis_error) children.push(h('div', { class: 'notice notice-warning' }, `Automated analysis is unavailable: ${result.analysis_error}`));
  if (result.analysis) children.push(h('p', { class: 'body-sm', style: { whiteSpace: 'pre-wrap' } }, result.analysis));
  if (!findings.length) children.push(h('p', { class: 'body-sm muted' }, result.analysis || 'No losses or material declines were detected for this period.'));
  findings.forEach((finding) => {
    const sources = (result.sources || []).filter((source) => source.product === finding.product);
    children.push(h(
      'div',
      { class: 'research-finding' },
      h('h3', { class: 'card-title' }, `${finding.finding} · ${finding.product}`),
      sources.length
        ? sources.map((source) => h('div', { class: 'research-source' }, h('a', { href: source.url, target: '_blank', rel: 'noopener noreferrer' }, `[${source.id}] ${source.title}`), h('span', { class: 'muted' }, source.description), source.age ? h('small', { class: 'muted' }, source.age) : null))
        : h('p', { class: 'body-sm muted' }, 'No matching sources were returned.'),
    ));
  });
  (result.limitations || []).forEach((note) => children.push(h('p', { class: 'footnote' }, note)));
  mount($('#research-results'), h('div', { class: 'card' }, h('div', { class: 'card-header' }, h('div', {}, h('h2', { class: 'card-title' }, 'Market context'), h('p', { class: 'card-subtitle' }, 'Contextual leads, not proof of cause'))), h('div', { class: 'card-body research' }, children)));
}

async function runResearch() {
  const button = $('#research-run');
  button.disabled = true;
  setStatus('#research-status', 'Searching for seasonal, weather, festive and market context…');
  try {
    const result = await request(businessPath(`/performance-research?${scopeParams()}`), { method: 'POST' });
    renderResearch(result);
    setStatus('#research-status', `${number(result.findings?.length || 0)} finding(s) · ${number(result.sources?.length || 0)} source(s)`);
  } catch (error) {
    setStatus('#research-status', error.message, true);
  } finally {
    button.disabled = !researchConfigured;
  }
}

async function load() {
  loadResearchStatus().catch((error) => setStatus('#research-status', error.message, true));
  mount($('#research-results'));
  if (!scopeHasData()) {
    mount($('#insights-list'), emptyState('No insights yet', 'Insights are calculated once you import records.', h('a', { class: 'btn btn-primary btn-sm', href: '#data' }, 'Import data')));
    renderComparison(null);
    return;
  }
  const id = ++requestId;
  mount($('#insights-list'), h('div', { class: 'card card-body' }, skeletonRows(4)));
  const params = scopeParams();
  const [insights, analytics] = await Promise.all([request(businessPath(`/insights?${params}`)), request(businessPath(`/analytics?${params}`))]);
  if (id !== requestId) return;
  state.bounds = analytics.available_period;
  setCurrency(analytics.currency);
  mount($('#insights-list'), insights.insights.length ? insights.insights.map((item) => insightCard(item)) : emptyState('Nothing notable in this period', 'There are not enough records to compare. Try a wider date range.'));
  renderComparison(analytics.comparison);
}
