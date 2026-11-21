import { render, screen } from '@testing-library/react';
import { ResearchResults } from './Insights';

describe('ResearchResults source links', () => {
  it('renders http(s) links with rel and drops javascript: hrefs', () => {
    render(
      <ResearchResults
        result={{
          findings: [{ finding: 'Decline', product: 'Rice' }],
          sources: [
            { id: 1, product: 'Rice', title: 'Good', url: 'https://example.com/a' },
            { id: 2, product: 'Rice', title: 'Evil', url: 'javascript:alert(1)' },
          ],
        }}
      />,
    );
    const good = screen.getByText('[1] Good');
    expect(good.tagName).toBe('A');
    expect(good).toHaveAttribute('href', 'https://example.com/a');
    expect(good).toHaveAttribute('rel', 'noopener noreferrer');
    const evil = screen.getByText('[2] Evil');
    expect(evil.tagName).not.toBe('A');
    expect(evil).not.toHaveAttribute('href');
  });
});
