import { describe, expect, it } from 'vitest';
import { cashOnHand, salesToPlace, type BalanceBlock } from './books.logic';

const block: BalanceBlock = {
  currency: 'GHS',
  assets: [
    { code: '1000', name: 'Cash on hand', key: 'cash', amount: 95.1 },
    { code: '1010', name: 'MTN Mobile Money', key: 'momo_mtn', amount: 95.2 },
    { code: '1090', name: 'Sales receipts to allocate', key: 'receipts_clearing', amount: 50 },
    { code: '1200', name: 'Stock', key: 'inventory', amount: 700 },
  ],
  liabilities: [{ code: '2090', name: 'Payments to allocate', key: 'payments_clearing', amount: 230 }],
  equity: [],
  totals: { assets: 940.3, liabilities: 230, equity: 0 },
  balanced: false,
  to_allocate: [
    { code: '1090', name: 'Sales receipts to allocate', key: 'receipts_clearing', amount: 50 },
    { code: '2090', name: 'Payments to allocate', key: 'payments_clearing', amount: 230 },
  ],
};

describe('books helpers', () => {
  it('counts only cash, MoMo and bank as money on hand', () => {
    expect(cashOnHand(block)).toBe(190.3);
  });
  it('counts only sales still waiting for a payment account', () => {
    expect(salesToPlace(block)).toBe(50);
  });
});
