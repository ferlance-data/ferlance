// Pure sort / filter / derive logic for the Products table.

import type { ProductRow } from '../../lib/types';
import type { SortState } from '../components/ui';

export type ProductFilter = 'all' | 'profit' | 'loss';

/** Sortable value: names compare case-insensitively, missing numbers sink to the bottom. */
export function sortValue(item: ProductRow, key: string): string | number {
  if (key === 'product') return item.product.toLocaleLowerCase();
  const raw = (item as unknown as Record<string, unknown>)[key];
  return typeof raw === 'number' ? raw : Number.NEGATIVE_INFINITY;
}

/**
 * Next sort state when a header is clicked. A new column starts A→Z for names and
 * highest-first for numbers; clicking the active column again flips its direction.
 */
export function nextSort(current: SortState, key: string): SortState {
  if (current.key === key) return { key, dir: current.dir === 'asc' ? 'desc' : 'asc' };
  return { key, dir: key === 'product' ? 'asc' : 'desc' };
}

export function filterProducts(items: ProductRow[], query: string, filter: ProductFilter): ProductRow[] {
  const needle = query.trim().toLocaleLowerCase();
  let rows = items.filter((item) => item.product.toLocaleLowerCase().includes(needle));
  if (filter === 'profit') rows = rows.filter((item) => (item.gross_profit ?? 0) > 0);
  if (filter === 'loss') rows = rows.filter((item) => (item.gross_profit ?? 0) < 0);
  return rows;
}

export function sortProducts(rows: ProductRow[], sort: SortState): ProductRow[] {
  return [...rows].sort((a, b) => {
    const [x, y] = [sortValue(a, sort.key), sortValue(b, sort.key)];
    const order = typeof x === 'string' && typeof y === 'string' ? x.localeCompare(y) : Number(x) - Number(y);
    return sort.dir === 'asc' ? order : -order;
  });
}

/** Sum of positive metric values, the denominator for share bars. */
export function metricTotal(items: ProductRow[]): number {
  return items.reduce((sum, item) => sum + Math.max(item.metric_value, 0), 0);
}

export function shareOf(item: ProductRow, total: number): { percent: number; width: number } {
  const base = total || 1;
  return { percent: (item.metric_value / base) * 100, width: Math.max(1, (Math.max(item.metric_value, 0) / base) * 100) };
}

export function deriveProducts(items: ProductRow[], query: string, filter: ProductFilter, sort: SortState) {
  return { total: metricTotal(items), rows: sortProducts(filterProducts(items, query, filter), sort) };
}
