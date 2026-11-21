import { POSITION_LABELS } from '../../lib/reports';
import { categoryOptionGroups, CATEGORY_GROUPS, minimumBalance } from './position.logic';

describe('position logic', () => {
  it('groups every labelled category in order', () => {
    const groups = categoryOptionGroups(POSITION_LABELS);
    expect(groups.map((g) => g.group)).toEqual(['Assets', 'Liabilities', 'Equity']);
    expect(groups[0]?.options.map((o) => o.value)).toEqual(['cash', 'bank', 'receivables', 'inventory', 'fixed_assets', 'other_assets']);
    expect(groups.flatMap((g) => g.options)).toHaveLength(Object.keys(POSITION_LABELS).length);
    expect(Object.keys(POSITION_LABELS).every((key) => key in CATEGORY_GROUPS)).toBe(true);
  });
  it('only allows negative equity', () => {
    expect(minimumBalance('owner_capital')).toBeUndefined();
    expect(minimumBalance('cash')).toBe('0');
  });
});
