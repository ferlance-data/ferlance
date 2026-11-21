import { describe, expect, it } from 'vitest';
import { DEFAULT_SCOPE, resolveRange, scopeBounds, scopeHasData, scopeLabel, scopeParams, type Scope } from './scope';
import type { Dataset } from './types';

const bounds = { from: '2026-01-05', to: '2026-05-20' };
const scope = (patch: Partial<Scope>): Scope => ({ ...DEFAULT_SCOPE, ...patch });

const dataset = (patch: Partial<Dataset>): Dataset => ({
  id: 'd1',
  filename: 'sales.csv',
  extension: 'csv',
  status: 'processed',
  source_rows: 1,
  accepted_rows: 1,
  rejected_rows: 0,
  warnings: [],
  errors: [],
  created_at: '2026-01-01',
  included: true,
  ...patch,
});

describe('resolveRange', () => {
  it('returns open dates for all time and the chosen dates for custom', () => {
    expect(resolveRange(scope({ range: 'all' }), bounds)).toEqual({ from: null, to: null });
    expect(resolveRange(scope({ range: 'custom', from: '2026-02-01', to: '2026-02-10' }), bounds)).toEqual({ from: '2026-02-01', to: '2026-02-10' });
  });

  it('anchors presets to the latest record, not today', () => {
    expect(resolveRange(scope({ range: '7' }), bounds)).toEqual({ from: '2026-05-14', to: '2026-05-20' });
    expect(resolveRange(scope({ range: '30' }), bounds)).toEqual({ from: '2026-04-21', to: '2026-05-20' });
    expect(resolveRange(scope({ range: 'mtd' }), bounds)).toEqual({ from: '2026-05-01', to: '2026-05-20' });
    expect(resolveRange(scope({ range: 'qtd' }), bounds)).toEqual({ from: '2026-04-01', to: '2026-05-20' });
    expect(resolveRange(scope({ range: 'ytd' }), bounds)).toEqual({ from: '2026-01-01', to: '2026-05-20' });
  });

  it('falls back to today when no records bound the scope yet', () => {
    expect(resolveRange(scope({ range: '7' }), { from: null, to: null }, new Date(2026, 10, 21))).toEqual({ from: '2026-11-15', to: '2026-11-21' });
  });
});

describe('scopeParams', () => {
  it('omits dataset_id for all data and includes resolved dates', () => {
    expect(scopeParams(scope({ range: 'mtd' }), bounds).toString()).toBe('from=2026-05-01&to=2026-05-20');
    expect(scopeParams(scope({ datasetId: 'd9' }), bounds).toString()).toBe('dataset_id=d9');
    expect(scopeParams(scope({ datasetId: 'd9' }), bounds, { includeDataset: false }).toString()).toBe('');
  });
});

describe('scope labels and data checks', () => {
  const datasets = [dataset({ id: 'a', filename: 'a.csv' }), dataset({ id: 'b', filename: 'b.csv', included: false }), dataset({ id: 'c', status: 'failed' })];

  it('names the chosen file', () => {
    expect(scopeLabel(scope({ datasetId: 'b' }), datasets)).toBe('b.csv');
    expect(scopeLabel(scope({}), datasets)).toBe('All business data');
  });

  it('needs an included analysable file for all data, or an analysable chosen file', () => {
    expect(scopeHasData(scope({}), datasets)).toBe(true);
    expect(scopeHasData(scope({}), [datasets[1] as Dataset])).toBe(false);
    expect(scopeHasData(scope({ datasetId: 'b' }), datasets)).toBe(true);
    expect(scopeHasData(scope({ datasetId: 'c' }), datasets)).toBe(false);
  });
});

describe('scopeBounds', () => {
  const files = [
    dataset({ id: 'a', period: { from: '2026-01-05', to: '2026-03-31' } }),
    dataset({ id: 'b', period: { from: '2025-11-01', to: '2026-02-10' } }),
    dataset({ id: 'x', included: false, period: { from: '2024-01-01', to: '2026-12-31' } }),
    dataset({ id: 'f', status: 'failed', period: { from: null, to: null } }),
  ];

  it('spans every included file for all data', () => {
    expect(scopeBounds(scope({}), files)).toEqual({ from: '2025-11-01', to: '2026-03-31' });
  });

  it('uses only the chosen file, even when it is excluded from business-wide views', () => {
    expect(scopeBounds(scope({ datasetId: 'b' }), files)).toEqual({ from: '2025-11-01', to: '2026-02-10' });
    expect(scopeBounds(scope({ datasetId: 'x' }), files)).toEqual({ from: '2024-01-01', to: '2026-12-31' });
  });

  it('is open when files have no dated records or no stored span', () => {
    expect(scopeBounds(scope({ datasetId: 'f' }), files)).toEqual({ from: null, to: null });
    expect(scopeBounds(scope({}), [dataset({})])).toEqual({ from: null, to: null });
  });

  it('switching file re-anchors presets without waiting for a response', () => {
    const last30 = (id: string) => scopeParams(scope({ datasetId: id, range: '30' }), scopeBounds(scope({ datasetId: id }), files)).toString();
    expect(last30('a')).toBe('dataset_id=a&from=2026-03-02&to=2026-03-31');
    expect(last30('b')).toBe('dataset_id=b&from=2026-01-12&to=2026-02-10');
  });
});
