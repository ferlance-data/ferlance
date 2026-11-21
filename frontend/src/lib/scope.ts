// Scope: which files and which dates every analytical view reads.

import { isoDate } from './format';
import type { Dataset, Period } from './types';

export type RangePreset = 'all' | '7' | '30' | '90' | 'mtd' | 'qtd' | 'ytd' | '365' | 'custom';

export interface Scope {
  datasetId: string;
  range: RangePreset;
  from: string | null;
  to: string | null;
}

export const DEFAULT_SCOPE: Scope = { datasetId: 'all', range: 'all', from: null, to: null };

export const RANGE_OPTIONS: { value: RangePreset; label: string }[] = [
  { value: 'all', label: 'All time' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: 'mtd', label: 'Month to date' },
  { value: 'qtd', label: 'Quarter to date' },
  { value: 'ytd', label: 'Year to date' },
  { value: '365', label: 'Last 12 months' },
  { value: 'custom', label: 'Custom range…' },
];

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/**
 * Resolve a preset into concrete dates. Presets are anchored to the latest record
 * in scope rather than today, so historical uploads still show meaningful windows.
 */
export function resolveRange(scope: Scope, bounds: Period, today: Date = new Date()): Period {
  if (scope.range === 'all') return { from: null, to: null };
  if (scope.range === 'custom') return { from: scope.from, to: scope.to };
  const anchor = bounds.to ? new Date(`${bounds.to}T00:00:00`) : today;
  let start: Date;
  if (scope.range === 'mtd') start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  else if (scope.range === 'qtd') start = new Date(anchor.getFullYear(), Math.floor(anchor.getMonth() / 3) * 3, 1);
  else if (scope.range === 'ytd') start = new Date(anchor.getFullYear(), 0, 1);
  else start = addDays(anchor, -(Number(scope.range) - 1));
  return { from: isoDate(start), to: isoDate(anchor) };
}

/** Query string for scoped endpoints: dataset_id (unless "all"), from, to. */
export function scopeParams(scope: Scope, bounds: Period, { includeDataset = true } = {}): URLSearchParams {
  const params = new URLSearchParams();
  if (includeDataset && scope.datasetId && scope.datasetId !== 'all') params.set('dataset_id', scope.datasetId);
  const { from, to } = resolveRange(scope, bounds);
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  return params;
}

export const analysableDatasets = (datasets: Dataset[]): Dataset[] => datasets.filter((item) => item.status !== 'failed');
export const includedDatasets = (datasets: Dataset[]): Dataset[] => analysableDatasets(datasets).filter((item) => item.included);

export function scopeLabel(scope: Scope, datasets: Dataset[]): string {
  return datasets.find((item) => item.id === scope.datasetId)?.filename ?? 'All business data';
}

/** True when the scope has records to analyse (a chosen file, or at least one included file). */
export function scopeHasData(scope: Scope, datasets: Dataset[]): boolean {
  return scope.datasetId !== 'all'
    ? analysableDatasets(datasets).some((item) => item.id === scope.datasetId)
    : includedDatasets(datasets).length > 0;
}
