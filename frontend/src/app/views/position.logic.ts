// Pure helpers for the Financial position view.

export type PositionGroup = 'Assets' | 'Liabilities' | 'Equity';
export const POSITION_GROUPS: PositionGroup[] = ['Assets', 'Liabilities', 'Equity'];

export const CATEGORY_GROUPS: Record<string, PositionGroup> = {
  cash: 'Assets', bank: 'Assets', receivables: 'Assets', inventory: 'Assets', fixed_assets: 'Assets', other_assets: 'Assets',
  payables: 'Liabilities', loans: 'Liabilities', other_liabilities: 'Liabilities',
  owner_capital: 'Equity', retained_earnings: 'Equity', other_equity: 'Equity',
};

/** Category options grouped for `<optgroup>`s, in label-table order within each group. */
export function categoryOptionGroups(labels: Record<string, string>): { group: PositionGroup; options: { value: string; label: string }[] }[] {
  return POSITION_GROUPS.map((group) => ({
    group,
    options: Object.entries(labels).filter(([key]) => CATEGORY_GROUPS[key] === group).map(([value, label]) => ({ value, label })),
  }));
}

/** Equity balances may be negative (accumulated losses); assets and liabilities may not. */
export function minimumBalance(category: string): string | undefined {
  return CATEGORY_GROUPS[category] === 'Equity' ? undefined : '0';
}
