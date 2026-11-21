import { describe, expect, it } from 'vitest';
import type { ProductRow } from '../../lib/types';
import { deriveProducts, filterProducts, metricTotal, nextSort, shareOf, sortProducts } from './products.logic';

const row = (product: string, metric_value: number, gross_profit?: number): ProductRow => ({
  product,
  revenue: metric_value,
  transactions: 1,
  metric_label: 'Revenue',
  metric_value,
  gross_profit,
});
const items = [row('Beans', 50, 10), row('apple', 100, -5), row('Corn', 25)];

describe('products logic', () => {
  it('filters by query case-insensitively', () => {
    expect(filterProducts(items, '  AP ', 'all').map((i) => i.product)).toEqual(['apple']);
  });
  it('filters profitable and losing; missing profit counts as zero', () => {
    expect(filterProducts(items, '', 'profit').map((i) => i.product)).toEqual(['Beans']);
    expect(filterProducts(items, '', 'loss').map((i) => i.product)).toEqual(['apple']);
  });
  it('sorts by name ignoring case, and by number with missing last when descending', () => {
    expect(sortProducts(items, { key: 'product', dir: 'asc' }).map((i) => i.product)).toEqual(['apple', 'Beans', 'Corn']);
    expect(sortProducts(items, { key: 'gross_profit', dir: 'desc' }).map((i) => i.product)).toEqual(['Beans', 'apple', 'Corn']);
    expect(sortProducts(items, { key: 'metric_value', dir: 'desc' }).map((i) => i.product)).toEqual(['apple', 'Beans', 'Corn']);
  });
  it('does not mutate input', () => {
    const copy = [...items];
    sortProducts(items, { key: 'metric_value', dir: 'asc' });
    expect(items).toEqual(copy);
  });
  it('toggles sort direction', () => {
    expect(nextSort({ key: 'revenue', dir: 'desc' }, 'revenue')).toEqual({ key: 'revenue', dir: 'asc' });
    expect(nextSort({ key: 'revenue', dir: 'asc' }, 'revenue')).toEqual({ key: 'revenue', dir: 'desc' });
    expect(nextSort({ key: 'revenue', dir: 'desc' }, 'product')).toEqual({ key: 'product', dir: 'asc' });
    expect(nextSort({ key: 'product', dir: 'asc' }, 'product')).toEqual({ key: 'product', dir: 'desc' });
    expect(nextSort({ key: 'product', dir: 'desc' }, 'product')).toEqual({ key: 'product', dir: 'asc' });
    expect(sortProducts(items, { key: 'product', dir: 'desc' }).map((i) => i.product)).toEqual(['Corn', 'Beans', 'apple']);
  });
  it('computes share with a floor of 1% bar width and guards zero totals', () => {
    expect(metricTotal([row('a', 10), row('b', -4)])).toBe(10);
    expect(shareOf(row('a', 50), 200)).toEqual({ percent: 25, width: 25 });
    expect(shareOf(row('a', -5), 100).width).toBe(1);
    expect(shareOf(row('a', 0), 0)).toEqual({ percent: 0, width: 1 });
  });
  it('derives rows and total', () => {
    const result = deriveProducts(items, '', 'all', { key: 'metric_value', dir: 'desc' });
    expect(result.total).toBe(175);
    expect(result.rows[0]?.product).toBe('apple');
  });
});
