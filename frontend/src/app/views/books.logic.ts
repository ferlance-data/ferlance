// Types and small pure helpers for the Books page (backend/ledger.py report shapes).

export interface LedgerLine {
  code: string;
  name: string;
  key: string | null;
  amount: number;
}

export interface BalanceBlock {
  currency: string;
  assets: LedgerLine[];
  liabilities: LedgerLine[];
  equity: LedgerLine[];
  totals: { assets: number; liabilities: number; equity: number };
  balanced: boolean;
  to_allocate: LedgerLine[];
}

export interface BooksSummary {
  settings: { books_start: string | null; lock_date: string | null };
  currency: string;
  lock_history: { before_date: string | null; after_date: string | null; created_at: string; user_email: string | null }[];
  profit_and_loss: {
    from: string;
    to: string;
    currencies: { currency: string; income: LedgerLine[]; expenses: LedgerLine[]; total_income: number; total_expenses: number; gross_profit: number; net_profit: number }[];
  };
  balance_sheet: { as_of: string; currencies: BalanceBlock[] };
  cash_flow: { from: string; to: string; note: string; currencies: { currency: string; lines: Record<string, number>; net: number }[] };
  differences: { analytics_revenue: number; ledger_sales: number; explained: { reason: string; amount: number }[]; unexplained: number };
  issues: string[];
}

/** Accounts that hold money the business can spend now: cash, MoMo wallets and bank. */
export const CASH_KEYS = ['cash', 'momo_mtn', 'momo_telecel', 'momo_at', 'momo_other', 'bank'];

const round = (value: number) => Math.round(value * 100) / 100;

export function cashOnHand(block: BalanceBlock): number {
  return round(block.assets.filter((line) => line.key && CASH_KEYS.includes(line.key)).reduce((sum, line) => sum + line.amount, 0));
}

/** Sales whose payment account (cash, MoMo or bank) is not known yet. */
export function salesToPlace(block: BalanceBlock): number {
  return round(block.to_allocate.filter((line) => line.key === 'receipts_clearing').reduce((sum, line) => sum + line.amount, 0));
}
