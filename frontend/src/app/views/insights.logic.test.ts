import { comparisonRows } from './insights.logic';

describe('comparisonRows', () => {
  it('skips null metrics and labels known keys', () => {
    const rows = comparisonRows({ revenue: { current: 5, change_pct: 2 }, cost: { current: null, change_pct: null }, odd: { current: 1, change_pct: null } });
    expect(rows.map((row) => row.label)).toEqual(['Revenue', 'odd']);
  });
});
