// Reconcile: types and labels (backend/statements.py shapes).

export type Field = 'date' | 'description' | 'reference' | 'amount' | 'credit' | 'debit' | 'fee' | 'balance_after' | 'balance_before' | 'type';

export interface Preview {
  header_row: number;
  columns: string[];
  sample: string[][];
  mapping: Record<Field, number | null>;
  confident: boolean;
}

export interface Overview {
  accounts: { account: string; label: string; lines: number; first: string; last: string }[];
  imports: { account: string; filename: string; new_lines: number; duplicate_lines: number; checks: string[]; created_at: string }[];
  choices: Record<string, string>;
}

export interface Candidate {
  id: string;
  date: string;
  amount: number;
  label: string;
}

export interface StatementLine {
  id: string;
  date: string;
  description: string;
  reference: string;
  amount: number;
  fee: number;
  fee_booked: boolean;
  balance_after: number | null;
  status: 'matched' | 'suggested' | 'unmatched' | 'booked';
  booking: string | null;
  matched_to: Candidate | null;
  suggestions: Candidate[];
}

export interface Reconciliation {
  account: string;
  label: string;
  books_start: string | null;
  lines: StatementLine[];
  only_in_books?: Candidate[];
  summary: {
    first: string;
    last: string;
    statement_opening: number | null;
    statement_closing: number | null;
    books_opening: number;
    books_closing: number;
    difference: number | null;
    explained: { reason: string; amount: number }[];
    unexplained?: number;
    unmatched_lines: number;
  } | null;
}

export const FIELD_LABEL: Record<Field, string> = {
  date: 'Date',
  description: 'Description or name',
  reference: 'Transaction ID',
  amount: 'Amount',
  credit: 'Money in',
  debit: 'Money out',
  fee: 'Fee or levy',
  balance_after: 'Balance after',
  balance_before: 'Balance before',
  type: 'Transaction type',
};

export const BOOKING_LABEL: Record<string, string> = {
  sale_recorded: 'A sale already imported (payment method was unknown)',
  new_sale: 'A new sale',
  other_income: 'Other income',
  payment_recorded: 'A payment already recorded (method was unknown)',
  expense: 'Spending',
  owner: 'Owner put in or took out',
  transfer: 'Moved between my own accounts',
  debt_payment: 'A debt payment',
};

export const EXPENSE_KINDS: Record<string, string> = {
  rent: 'Rent',
  transport: 'Transport and fuel',
  airtime: 'Data and airtime',
  utilities: 'Electricity and water',
  wages: 'Wages',
  charges: 'MoMo and bank charges',
  uncategorised: 'Something else',
};

export const OTHER_ACCOUNTS: Record<string, string> = {
  cash: 'Cash',
  bank: 'Bank',
  momo_mtn: 'MTN Mobile Money',
  momo_telecel: 'Telecel Cash',
  momo_at: 'AT Money',
};

/** Money in can't be spending, and money out can't be a sale: only offer what fits the direction. */
export function categoriesFor(inflow: boolean): string[] {
  return inflow ? ['sale_recorded', 'new_sale', 'debt_payment', 'transfer', 'owner', 'other_income'] : ['payment_recorded', 'expense', 'debt_payment', 'transfer', 'owner'];
}
