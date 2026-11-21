import type { InventoryItem } from '../../lib/types';
import { buildStocktakeTemplate, filterProducts, resolveSelectedProduct } from './inventory.logic';

const item = (id: string, name: string, active = true, sku: string | null = null): InventoryItem => ({
  id, name, sku, active, unit: 'unit', unit_cost: null, reorder_level: 0, quantity_on_hand: 0, stock_value: null, low_stock: false, created_at: '', updated_at: '',
});
const items = [item('1', 'Rice', true, 'R-1'), item('2', 'Beans', false), item('3', 'Salt')];

describe('inventory logic', () => {
  it('builds the stocktake template', () => {
    expect(buildStocktakeTemplate()).toBe('product,sku,unit,quantity_on_hand,unit_cost,reorder_level\n');
  });
  it('filters by name/sku and archived flag', () => {
    expect(filterProducts(items, '', false).map((i) => i.id)).toEqual(['1', '3']);
    expect(filterProducts(items, '', true)).toHaveLength(3);
    expect(filterProducts(items, ' r-1 ', false).map((i) => i.id)).toEqual(['1']);
    expect(filterProducts(items, 'beans', false)).toEqual([]);
  });
  it('resolves the selected product', () => {
    expect(resolveSelectedProduct(items, '3')).toBe('3');
    expect(resolveSelectedProduct(items, '2')).toBe('1');
    expect(resolveSelectedProduct([], '')).toBe('');
  });
});
