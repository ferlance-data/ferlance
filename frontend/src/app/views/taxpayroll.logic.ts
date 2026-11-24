// Tax & payroll: types (backend/tax.py and backend/payroll.py shapes).

export interface TaxRule {
  id: string;
  key: string;
  from: string;
  to: string | null;
  label: string;
  notes: string;
  sources: { title: string; url: string }[];
  checked: { checked_by: string | null; checked_at: string } | null;
}

export interface TaxSummary {
  from: string;
  to: string;
  vat: { name: string; amount: number }[];
  vat_total: number;
  wht: { kind: string; amount: number }[];
  payroll: { month: string; paye: number; ssnit_employee: number; ssnit_employer: number }[];
  unchecked_rules: string[];
  note: string;
}

export interface Employee {
  id: string;
  name: string;
  ssnit_number: string;
  tin: string;
  basic: number;
  allowances: number;
  active: boolean;
}

export interface PayrollRun {
  id: string;
  month: string;
  status: 'draft' | 'posted' | 'void';
  paid_from: string | null;
  paid_on: string | null;
  staff: number;
  gross: number;
  net: number;
  paye: number;
  ssnit: number;
}

export interface RunDetail {
  id: string;
  month: string;
  status: PayrollRun['status'];
  lines: { id: string; employee_id: string; name: string; basic: number; allowances: number; gross: number; ssnit_employee: number; ssnit_employer: number; chargeable: number; paye: number; net: number; rules: string[] }[];
  totals: Record<string, number>;
  unchecked_rules: string[];
}

export const RULE_KEY_LABEL: Record<string, string> = {
  vat: 'VAT and levies',
  paye_monthly: 'PAYE (monthly)',
  ssnit: 'SSNIT',
  wht: 'Withholding tax',
};
