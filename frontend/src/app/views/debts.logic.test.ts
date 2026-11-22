import { describe, expect, it } from 'vitest';
import { intlPhone, overdue, reminderText, smsLink, whatsappLink, type Debt } from './debts.logic';

const debt: Debt = {
  id: 'd1',
  direction: 'owed_to_us',
  basis: 'new_sale',
  description: '2 bags rice',
  party_name: 'Akosua',
  phone: '024 412 3456',
  amount: 200,
  paid: 80,
  balance: 120,
  currency: 'GHS',
  issued_on: '2026-10-02',
  due_on: '2026-10-09',
  age: '31_60',
  status: 'open',
  payments: [],
};
const book = { business_name: 'Ama Provisions', pay_to: 'MTN 0244 000 000 (Ama)' };

describe('debt reminders', () => {
  it('turns Ghana numbers into international form', () => {
    expect(intlPhone('024 412 3456')).toBe('233244123456');
    expect(intlPhone('+233 20 123 4567')).toBe('233201234567');
    expect(intlPhone('call me')).toBe('');
  });
  it('writes a reminder with the amount and where to pay', () => {
    const text = reminderText(debt, book, 'GH₵120.00', 'en');
    expect(text).toContain('Akosua');
    expect(text).toContain('GH₵120.00 (2 bags rice)');
    expect(text).toContain('MTN 0244 000 000 (Ama)');
    expect(reminderText(debt, { ...book, pay_to: '' }, 'GH₵120.00', 'en')).not.toContain('MoMo');
    expect(reminderText(debt, book, 'GH₵120.00', 'tw')).toContain('Yɛda wo ase');
  });
  it('builds WhatsApp and SMS links with the text encoded', () => {
    expect(whatsappLink('024 412 3456', 'Hi & bye')).toBe('https://wa.me/233244123456?text=Hi%20%26%20bye');
    expect(smsLink('024 412 3456', 'Hi')).toBe('sms:+233244123456?body=Hi');
    expect(smsLink('', 'Hi')).toBe('sms:?body=Hi');
  });
  it('adds up what is late', () => {
    expect(overdue({ not_due: 50, '1_30': 10.1, '31_60': 20.2, '61_90': 0, over_90: 5 })).toBe(35.3);
  });
});
