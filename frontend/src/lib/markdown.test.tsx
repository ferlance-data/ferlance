import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Markdown } from './markdown';

describe('Markdown', () => {
  it('renders headings, lists, tables and inline emphasis', () => {
    const { container } = render(
      <Markdown source={'## Top products\n\n- **Rice** led\n- *Beans* next\n\n1. one\n2. two\n\n| Item | Revenue |\n|---|---|\n| Rice | `GHS 10` |\n\nPlain\ncontinued'} />,
    );
    expect(container.querySelector('h3')?.textContent).toBe('Top products');
    expect(container.querySelectorAll('ul li')).toHaveLength(2);
    expect(container.querySelector('ul strong')?.textContent).toBe('Rice');
    expect(container.querySelector('ul em')?.textContent).toBe('Beans');
    expect(container.querySelectorAll('ol li')).toHaveLength(2);
    expect(container.querySelector('.table-wrap table.table th')?.textContent).toBe('Item');
    expect(container.querySelector('td code')?.textContent).toBe('GHS 10');
    expect(container.querySelector('p')?.textContent).toBe('Plain continued');
  });

  it('never turns model output into markup', () => {
    const { container } = render(<Markdown source={'<img src=x onerror=alert(1)> **<script>bad()</script>**'} />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(container.querySelector('strong')?.textContent).toBe('<script>bad()</script>');
  });
});
