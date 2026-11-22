import { describe, expect, it } from 'vitest';
import { initialDecision, type CaptureLine } from './ScanInvoice';

const line = (patch: Partial<CaptureLine>): CaptureLine => ({
  name: 'Paracetamol', sku: null, quantity: 10, unit: null, unit_cost: 8.5, line_total: 85, expiry: null, confidence: 0.9, notes: [], match: null, ...patch,
});

describe('initialDecision', () => {
  it('adds to an exact match, creates when nothing matches', () => {
    expect(initialDecision(line({ match: { product_id: 'p1', name: 'Paracetamol', kind: 'exact' } }))).toMatchObject({ action: 'add', product_id: 'p1', quantity: '10', unit_cost: '8.5' });
    expect(initialDecision(line({}))).toMatchObject({ action: 'create', product_id: '', name: 'Paracetamol' });
  });
  it('never preselects a merely similar product', () => {
    expect(initialDecision(line({ match: { product_id: 'p2', name: 'Paracetamol 500', kind: 'similar' } }))).toMatchObject({ action: 'add', product_id: '' });
  });
  it('leaves unknown numbers blank for the owner to fill', () => {
    expect(initialDecision(line({ quantity: null, unit_cost: null }))).toMatchObject({ quantity: '', unit_cost: '' });
  });
});
