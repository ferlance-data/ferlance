import { describe, expect, it } from 'vitest';
import { BOOKING_LABEL, categoriesFor } from './reconcile.logic';

describe('reconcile categories', () => {
  it('offers only what fits the direction of the money', () => {
    expect(categoriesFor(true)).toContain('sale_recorded');
    expect(categoriesFor(true)).not.toContain('expense');
    expect(categoriesFor(false)).toContain('expense');
    expect(categoriesFor(false)).not.toContain('new_sale');
  });
  it('labels every category', () => {
    for (const key of [...categoriesFor(true), ...categoriesFor(false)]) expect(BOOKING_LABEL[key]).toBeTruthy();
  });
});
