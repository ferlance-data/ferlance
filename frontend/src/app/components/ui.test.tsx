import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DataTable, Delta, Segmented, type Column } from './ui';

interface Row {
  name: string;
  revenue: number;
}

const columns: Column<Row>[] = [
  { label: 'Product', value: (row) => row.name, sort: 'name' },
  { label: 'Revenue', value: (row) => row.revenue, num: true, sort: 'revenue' },
];

describe('DataTable', () => {
  it('shows the empty message when there are no rows', () => {
    render(<DataTable columns={columns} rows={[]} rowKey={(row) => row.name} empty="No products yet." />);
    expect(screen.getByText('No products yet.')).toBeInTheDocument();
  });

  it('marks the sorted column and reports header clicks', async () => {
    const onSort = vi.fn();
    render(
      <DataTable
        columns={columns}
        rows={[{ name: 'Rice', revenue: 10 }]}
        rowKey={(row) => row.name}
        sortState={{ key: 'revenue', dir: 'desc' }}
        onSort={onSort}
      />,
    );
    const revenueHeader = screen.getByRole('columnheader', { name: /Revenue/ });
    expect(revenueHeader).toHaveAttribute('aria-sort', 'descending');
    expect(revenueHeader).toHaveClass('num');
    expect(revenueHeader.textContent).toBe('Revenue ↓');
    await userEvent.click(screen.getByRole('button', { name: 'Product' }));
    expect(onSort).toHaveBeenCalledWith('name');
  });
});

describe('Delta', () => {
  it('colours rises as good unless inverted', () => {
    const { container, rerender } = render(<Delta change={12.34} />);
    expect(container.firstElementChild).toHaveClass('delta-up');
    expect(container.textContent).toBe('▲ 12.3%');
    rerender(<Delta change={12.34} invert />);
    expect(container.firstElementChild).toHaveClass('delta-down');
    rerender(<Delta change={null} />);
    expect(container.textContent).toBe('');
  });
});

describe('Segmented', () => {
  it('exposes pressed state for toggle groups and selected state for tabs', async () => {
    const onChange = vi.fn();
    const options = [
      { value: 'week', label: 'Week' },
      { value: 'month', label: 'Month' },
    ] as const;
    const { rerender } = render(<Segmented options={[...options]} value="week" onChange={onChange} label="Trend grouping" />);
    expect(screen.getByRole('button', { name: 'Week' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    expect(onChange).toHaveBeenCalledWith('month');
    rerender(<Segmented options={[...options]} value="month" onChange={onChange} label="Tabs" mode="tabs" />);
    expect(screen.getByRole('tab', { name: 'Month' })).toHaveAttribute('aria-selected', 'true');
  });
});
