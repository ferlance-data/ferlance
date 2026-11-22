// Debt book: types, reminder messages and links (backend/debts.py shapes).

export type Direction = 'owed_to_us' | 'we_owe';
export type Bucket = 'not_due' | '1_30' | '31_60' | '61_90' | 'over_90';

export interface DebtPayment {
  id: string;
  amount: number;
  paid_on: string;
  method: string;
  from_momo: boolean;
  voided: boolean;
  /** Matched to a MoMo message whose import is left out of analysis: not counted until it is included again. */
  on_hold: boolean;
}

export interface Debt {
  id: string;
  direction: Direction;
  basis: string;
  description: string;
  party_name: string;
  phone: string;
  amount: number;
  paid: number;
  balance: number;
  currency: string;
  issued_on: string;
  due_on: string | null;
  age: Bucket | null;
  status: 'open' | 'settled' | 'voided';
  payments: DebtPayment[];
}

export interface DebtBook {
  today: string;
  business_name: string;
  currency: string;
  pay_to: string;
  totals: Record<Direction, { total: number; open: number; buckets: Record<Bucket, number> }>;
  debts: Debt[];
  parties: { id: string; kind: 'customer' | 'supplier'; name: string; phone: string }[];
}

export interface MomoMatch {
  momo_ref: string;
  debt_id: string;
  party_name: string;
  balance: number;
  amount: number;
  date: string;
  from: string;
  reason: string;
}

export const BUCKET_LABEL: Record<Bucket, string> = {
  not_due: 'Not due yet',
  '1_30': '1–30 days late',
  '31_60': '31–60 days late',
  '61_90': '61–90 days late',
  over_90: 'Over 90 days late',
};

export const METHOD_LABEL: Record<string, string> = {
  cash: 'Cash',
  momo_mtn: 'MTN MoMo',
  momo_telecel: 'Telecel Cash',
  momo_at: 'AT Money',
  momo_other: 'Mobile money',
  bank: 'Bank',
  momo_sms: 'MoMo message',
};

export function overdue(buckets: Record<Bucket, number>): number {
  return Math.round((buckets['1_30'] + buckets['31_60'] + buckets['61_90'] + buckets.over_90) * 100) / 100;
}

/** A Ghana number in international form for wa.me / sms: links, or '' if it doesn't look like a phone number. */
export function intlPhone(phone: string): string {
  let digits = phone.replace(/\D/g, '');
  if (digits.length === 10 && digits.startsWith('0')) digits = `233${digits.slice(1)}`;
  return digits.length >= 9 && digits.length <= 15 ? digits : '';
}

export type Language = 'en' | 'tw';

/**
 * A friendly reminder the owner sends from their own phone (nothing is sent automatically).
 * The Twi wording is a first draft and must be checked by a native speaker before wide use;
 * the owner can edit any message in WhatsApp or SMS before sending.
 */
export function reminderText(debt: Debt, book: Pick<DebtBook, 'business_name' | 'pay_to'>, amount: string, language: Language): string {
  const what = debt.description ? ` (${debt.description})` : '';
  if (language === 'tw') {
    const pay = book.pay_to ? ` Wobɛtumi de MoMo atua akɔ ${book.pay_to}.` : '';
    return `Ɛte sɛn ${debt.party_name}? Yɛfiri ${book.business_name}. Yɛrekae wo sɛ ${amount}${what} a wode yɛn ka no da so wɔ hɔ.${pay} Yɛda wo ase!`;
  }
  const pay = book.pay_to ? ` You can pay by MoMo to ${book.pay_to}.` : '';
  return `Hello ${debt.party_name}, this is ${book.business_name}. A friendly reminder that ${amount}${what} is still owing.${pay} Thank you!`;
}

export function whatsappLink(phone: string, text: string): string {
  const number = intlPhone(phone);
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`;
}

export function smsLink(phone: string, text: string): string {
  const number = intlPhone(phone);
  return `sms:${number ? `+${number}` : ''}?body=${encodeURIComponent(text)}`;
}
