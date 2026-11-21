import { comparisonRows, sourcesFor } from './insights.logic';

describe('sourcesFor', () => {
  const result = {
    sources: [
      { id: 1, product: 'Rice', title: 'Ok', url: 'https://example.com/a' },
      { id: 2, product: 'Rice', title: 'Bad', url: 'javascript:alert(1)' },
      { id: 3, product: 'Rice', title: 'Missing' },
      { id: 4, product: 'Beans', title: 'Other', url: 'https://example.com/b' },
    ],
  };
  it('keeps safe links and drops unsafe or missing ones', () => {
    const rows = sourcesFor(result, 'Rice');
    expect(rows.map((row) => row.href)).toEqual(['https://example.com/a', undefined, undefined]);
  });
  it('filters by product', () => {
    expect(sourcesFor(result, 'Beans')).toHaveLength(1);
    expect(sourcesFor({}, 'Beans')).toEqual([]);
  });
});

describe('comparisonRows', () => {
  it('skips null metrics and labels known keys', () => {
    const rows = comparisonRows({ revenue: { current: 5, change_pct: 2 }, cost: { current: null, change_pct: null }, odd: { current: 1, change_pct: null } });
    expect(rows.map((row) => row.label)).toEqual(['Revenue', 'odd']);
  });
});
