import { describe, expect, it } from 'vitest';
import { draftTotal, emptyLine, lineMinor, shareText } from './invoices.logic';

describe('invoice drafts', () => {
  it('totals lines in pesewas without float drift', () => {
    expect(lineMinor({ ...emptyLine(), quantity: '3', unit_price: '0.1' })).toBe(30);
    expect(draftTotal([
      { ...emptyLine(), quantity: '4', unit_price: '95' },
      { ...emptyLine(), quantity: '6', unit_price: '48' },
      { ...emptyLine(), quantity: '1', unit_price: '20' },
    ])).toBe(688);
  });
  it('ignores incomplete or invalid lines', () => {
    expect(lineMinor({ ...emptyLine(), quantity: '', unit_price: '5' })).toBe(0);
    expect(lineMinor({ ...emptyLine(), quantity: '2', unit_price: '-1' })).toBe(0);
  });
  it('writes a share message with where to pay, except on receipts', () => {
    const invoice = shareText({ kind: 'invoice', number: 'INV-0001', customer_name: 'Akosua' }, 'Ama Provisions', 'GH₵688.00', 'MTN 024');
    expect(invoice).toContain('invoice INV-0001');
    expect(invoice).toContain('MTN 024');
    expect(shareText({ kind: 'receipt', number: 'RCT-0001', customer_name: 'Akosua' }, 'Ama Provisions', 'GH₵5.00', 'MTN 024')).not.toContain('MoMo');
  });
});
