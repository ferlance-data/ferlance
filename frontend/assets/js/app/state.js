// Workspace state shared by every view, plus the scope (which files and which dates).

import { isoDate } from './dom.js';

const listeners = new Set();

export const state = {
  user: null,
  business: null,
  datasets: [],
  inventory: null,
  scope: { datasetId: 'all', range: 'all', from: null, to: null },
  bounds: { from: null, to: null },
};

export const businessPath = (suffix = '') => `/api/businesses/${state.business.id}${suffix}`;

export const analysableDatasets = () => state.datasets.filter((item) => item.status !== 'failed');
export const includedDatasets = () => analysableDatasets().filter((item) => item.included);

export function onScopeChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setScope(patch) {
  Object.assign(state.scope, patch);
  listeners.forEach((listener) => listener(state.scope));
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/**
 * Resolve a preset into concrete dates. Presets are anchored to the latest record
 * in scope rather than today, so historical uploads still show meaningful windows.
 */
export function resolveRange(scope = state.scope, bounds = state.bounds) {
  if (scope.range === 'all') return { from: null, to: null };
  if (scope.range === 'custom') return { from: scope.from, to: scope.to };
  const anchor = bounds.to ? new Date(`${bounds.to}T00:00:00`) : new Date();
  let start;
  if (scope.range === 'mtd') start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  else if (scope.range === 'qtd') start = new Date(anchor.getFullYear(), Math.floor(anchor.getMonth() / 3) * 3, 1);
  else if (scope.range === 'ytd') start = new Date(anchor.getFullYear(), 0, 1);
  else start = addDays(anchor, -(Number(scope.range) - 1));
  return { from: isoDate(start), to: isoDate(anchor) };
}

export function scopeParams({ includeDataset = true } = {}) {
  const params = new URLSearchParams();
  if (includeDataset && state.scope.datasetId && state.scope.datasetId !== 'all') params.set('dataset_id', state.scope.datasetId);
  const { from, to } = resolveRange();
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  return params;
}

export function scopeLabel() {
  const dataset = state.datasets.find((item) => item.id === state.scope.datasetId);
  return dataset ? dataset.filename : 'All business data';
}

/** True when the current scope has records to analyse (a chosen file, or at least one included file). */
export const scopeHasData = () => (state.scope.datasetId !== 'all' ? analysableDatasets().some((item) => item.id === state.scope.datasetId) : includedDatasets().length > 0);
