import { describe, expect, it } from 'vitest';
import { movementSource } from './Inventory';

describe('movementSource', () => {
  it('names every way stock can change', () => {
    expect(movementSource('manual', 'Ama')).toBe('Ama');
    expect(movementSource('capture', null)).toBe('Scanned invoice');
    expect(movementSource('sales:abc', null)).toBe('Sales file');
    expect(movementSource('sales-reversal:abc', null)).toBe('Sales file left out');
    expect(movementSource('stocktake', null)).toBe('Stocktake import');
  });
});
