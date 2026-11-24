// Invoices, quotes and receipts: types and pure helpers (backend/invoices.py shapes).

export type DocKind = 'invoice' | 'quote' | 'receipt';
export type DocStatus = 'sent' | 'part_paid' | 'paid' | 'overdue' | 'quote' | 'converted' | 'void';

export interface DocSummary {
  id: string;
  kind: DocKind;
  number: string;
  customer_name: string;
  phone: string;
  issued_on: string;
  due_on: string | null;
  currency: string;
  notes: string;
  total: number;
  paid: number;
  balance: number;
  status: DocStatus;
  debt_id: string | null;
  voided: boolean;
}

export interface DraftLine {
  product_id: string;
  description: string;
  quantity: string;
  unit_price: string;
}

export const KIND_LABEL: Record<DocKind, string> = { invoice: 'Invoice', quote: 'Quote', receipt: 'Receipt' };

export const STATUS: Record<DocStatus, [string, '' | 'success' | 'warning' | 'error' | 'info']> = {
  sent: ['Not paid yet', 'info'],
  part_paid: ['Part paid', 'warning'],
  paid: ['Paid', 'success'],
  overdue: ['Overdue', 'error'],
  quote: ['Quote', ''],
  converted: ['Now an invoice', 'success'],
  void: ['Void', ''],
};

export const emptyLine = (): DraftLine => ({ product_id: '', description: '', quantity: '1', unit_price: '' });

/** Line total in pesewas, the way the server computes it (so the preview never disagrees). */
export function lineMinor(line: DraftLine): number {
  const quantity = Number(line.quantity);
  const price = Number(line.unit_price);
  if (!Number.isFinite(quantity) || !Number.isFinite(price) || quantity <= 0 || price < 0) return 0;
  return Math.round(quantity * price * 100);
}

export function draftTotal(lines: DraftLine[]): number {
  return lines.reduce((sum, line) => sum + lineMinor(line), 0) / 100;
}

/** The message that goes with a shared document. */
export function shareText(doc: Pick<DocSummary, 'kind' | 'number' | 'customer_name'>, business: string, total: string, payTo: string): string {
  const what = KIND_LABEL[doc.kind].toLowerCase();
  const pay = doc.kind !== 'receipt' && payTo ? ` You can pay by MoMo to ${payTo}.` : '';
  return `Hello ${doc.customer_name}, here is your ${what} ${doc.number} from ${business} for ${total}.${pay} Thank you!`;
}
