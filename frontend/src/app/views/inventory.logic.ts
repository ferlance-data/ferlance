// Pure helpers for the Inventory view.

import type { InventoryItem } from '../../lib/types';

export const STOCKTAKE_TEMPLATE_HEADER = 'product,sku,unit,quantity_on_hand,unit_cost,reorder_level';
export const STOCKTAKE_TEMPLATE_FILENAME = 'inventory-stocktake-template.csv';

/** Header-only CSV the stocktake import accepts. */
export function buildStocktakeTemplate(): string {
  return `${STOCKTAKE_TEMPLATE_HEADER}\n`;
}

/** Products matching the search box (name or SKU), hiding archived ones unless asked. */
export function filterProducts(items: InventoryItem[], query: string, showArchived: boolean): InventoryItem[] {
  const needle = query.trim().toLocaleLowerCase();
  return items.filter((item) => (showArchived || item.active) && `${item.name} ${item.sku || ''}`.toLocaleLowerCase().includes(needle));
}

/** Product select value: keep the previous choice while it is still active, else the first active product. */
export function resolveSelectedProduct(items: InventoryItem[], previous: string): string {
  const active = items.filter((item) => item.active);
  return active.some((item) => item.id === previous) ? previous : (active[0]?.id ?? '');
}
